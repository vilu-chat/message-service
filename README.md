# message-service

Flask service that owns conversations, membership, messages and read positions (see `../design.md`).
First slice: direct and group conversations, sending and reading text messages, read positions,
and the `message.created` outbox row. Layers: Blueprint → service (owns the commit) → repository.

## Run with Docker (from `vilu-chat/`)

```bash
cp .env.example .env                      # once; set passwords (URL-safe)
docker compose up -d --build --wait message-service auth-stub
```

Starts Postgres, the auth stub (port 8081) and this service (port 8002). With `RUN_MIGRATIONS=true`
(set in compose only) the container runs `flask --app app db upgrade` before gunicorn. In Kubernetes
leave it unset and run the migration as a Job or init container.

```bash
tok() { curl -s -X POST localhost:8081/realms/chat/protocol/openid-connect/token -d username=$1 \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])'; }
BOB=0b1f6a4e-5c1d-4e8a-9a57-3f2d8c1a0002
curl -s -X POST localhost:8002/api/v1/conversations/direct -H "Authorization: Bearer $(tok anna)" \
  -H 'Content-Type: application/json' -d "{\"user_id\": \"$BOB\"}"
```

Swagger UI: <http://localhost:8002/docs> (assets load from a CDN). Health: `/healthz`, `/readyz`.

## Endpoints (all under `/api/v1/conversations`, bearer token required)

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/direct` | `{user_id}`; 201 when created, 200 when it already existed |
| POST | `` | Create a group: `{title, member_ids}`; the caller becomes admin |
| GET | `` | My conversations with `last_message` and `unread_count`, newest activity first. Query: `limit` (default 30, max 100), `cursor`. Returns `{items, next_cursor}`. Each item also has `last_read_seq` (the caller's), `member_count` (active members, caller included) and `member_preview_ids` (up to 4 other active members, oldest join first; for a direct chat, the peer) |
| GET | `/{id}` | Details and active members |
| POST | `/{id}/messages` | `{client_msg_id, body}`; 201 when created, 200 when `client_msg_id` was already sent |
| GET | `/{id}/messages` | `after_seq` or `before_seq` (not both), `limit` (default 50, max 100); oldest first, with `has_more` |
| PUT | `/{id}/read` | `{seq}`; `last_read_seq` only moves forward |

Everything under `/{id}` returns 404 to callers who are not active members, whether or not the conversation exists.

Sending a message also sets the sender's `last_read_seq` to the new `seq` (never backwards), so a sender's own messages are never unread for them.

A new conversation (group create, or a direct create that did not exist yet) writes a `conversation.created` outbox row with
`aggregate_id` = the conversation ID and payload `ConversationCreatedDataSchema`:
`{conversation_id, type, title, created_by, member_user_ids}`.

The `message.created` outbox row has `aggregate_id` = the conversation ID and, as payload, `MessageCreatedDataSchema`:
`{"message": {...}, "recipient_user_ids": [all active members, including the sender]}`.

## Known limitations

- **User IDs are not validated.** `POST /direct` and group creation accept any UUID. The Message Service
  does not call the User Service, so a conversation can contain a user that does not exist.
- No member add/remove, renaming, editing or deleting messages, attachments, relay or consumers yet.

## Run outside Docker (Python 3.12)

```bash
docker compose up -d --wait postgres auth-stub     # from vilu-chat/
cd message-service
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                               # database on localhost:5432
flask --app app db upgrade
flask --app app run --port 8002
```

## Tests

Need the Postgres container and the `message_service_test` database (created by the parent init script).
`TEST_DATABASE_URL` comes from `.env` and its database name must end in `_test`, because data is truncated
between tests. Migrations run (downgrade to base, then upgrade) at session start. The auth stub is not needed:
tests sign tokens with a generated RSA key and the JWKS lookup returns its public key.

```bash
pytest
```

## Configuration (environment variables)

| Variable | Purpose |
| --- | --- |
| `SQLALCHEMY_DATABASE_URI` | Database URL (role `message_svc`, database `message_service`) |
| `KEYCLOAK_ISSUER` | Compared as a string with the token's `iss` |
| `KEYCLOAK_JWKS_URL` | Where the signing keys are fetched |
| `KEYCLOAK_AUDIENCE` | Expected `aud` |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | Optional, per worker; default 3 and 2 |
| `RUN_MIGRATIONS` | `true` runs `flask db upgrade` at container start (compose only) |
| `TEST_DATABASE_URL` | Tests only |
