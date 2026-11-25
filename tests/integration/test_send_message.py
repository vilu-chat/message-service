import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from app.extensions import db
from app.models import Message, OutboxEvent
from tests.conftest import ANNA, BOB, CECILIA

BASE = "/api/v1/conversations"


def outbox_rows(app):
    """The message.created rows (group creation also writes a conversation.created row)."""
    with app.app_context():
        return list(
            db.session.scalars(
                select(OutboxEvent).where(OutboxEvent.event_type == "message.created").order_by(OutboxEvent.id)
            )
        )


def count(app, model):
    with app.app_context():
        return db.session.scalar(select(func.count()).select_from(model))


def test_send_returns_message_with_sender_from_token(client, as_user, make_group):
    group = make_group()
    cmid = uuid.uuid4()
    response = client.post(
        f"{BASE}/{group['id']}/messages",
        json={"client_msg_id": str(cmid), "body": "hello", "sender_id": str(CECILIA)},  # ignored
        headers=as_user(ANNA),
    )
    # sender_id is not part of the input schema, so it is rejected rather than silently trusted
    assert response.status_code == 422

    response = client.post(
        f"{BASE}/{group['id']}/messages",
        json={"client_msg_id": str(cmid), "body": "hello"},
        headers=as_user(ANNA),
    )
    assert response.status_code == 201
    body = response.get_json()
    assert body["seq"] == 1
    assert body["sender_id"] == str(ANNA)
    assert body["conversation_id"] == group["id"]
    assert body["client_msg_id"] == str(cmid)
    assert body["kind"] == "text"
    assert body["body"] == "hello"


def test_same_client_msg_id_gives_one_message_and_one_outbox_row(app, client, as_user, make_group):
    group = make_group()
    payload = {"client_msg_id": str(uuid.uuid4()), "body": "once"}
    url = f"{BASE}/{group['id']}/messages"

    first = client.post(url, json=payload, headers=as_user(ANNA))
    second = client.post(url, json=payload, headers=as_user(ANNA))

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.get_json() == first.get_json()
    assert count(app, Message) == 1
    assert len(outbox_rows(app)) == 1
    # the retry did not burn a sequence number
    third = client.post(url, json={"client_msg_id": str(uuid.uuid4()), "body": "next"}, headers=as_user(ANNA))
    assert third.get_json()["seq"] == 2


def test_client_msg_id_is_per_sender(client, as_user, make_group):
    group = make_group()
    shared = str(uuid.uuid4())
    url = f"{BASE}/{group['id']}/messages"
    a = client.post(url, json={"client_msg_id": shared, "body": "a"}, headers=as_user(ANNA))
    b = client.post(url, json={"client_msg_id": shared, "body": "b"}, headers=as_user(BOB))
    assert a.status_code == b.status_code == 201
    assert (a.get_json()["seq"], b.get_json()["seq"]) == (1, 2)


def test_client_msg_id_reused_in_another_conversation_is_a_conflict(client, as_user, make_group):
    one = make_group(title="one")
    two = make_group(title="two")
    shared = str(uuid.uuid4())
    ok = client.post(f"{BASE}/{one['id']}/messages", json={"client_msg_id": shared, "body": "x"}, headers=as_user(ANNA))
    clash = client.post(f"{BASE}/{two['id']}/messages", json={"client_msg_id": shared, "body": "x"}, headers=as_user(ANNA))
    assert ok.status_code == 201
    assert clash.status_code == 409
    assert clash.get_json()["status"] == "Conflict"


def test_outbox_payload_has_message_and_recipients(app, client, as_user, make_group):
    group = make_group(owner=ANNA, members=(BOB, CECILIA))
    response = client.post(
        f"{BASE}/{group['id']}/messages",
        json={"client_msg_id": str(uuid.uuid4()), "body": "hello all"},
        headers=as_user(ANNA),
    )
    message = response.get_json()

    (event,) = outbox_rows(app)
    assert event.event_type == "message.created"
    assert str(event.aggregate_id) == group["id"]
    assert event.published_at is None
    assert set(event.payload) == {"message", "recipient_user_ids"}
    assert set(event.payload["recipient_user_ids"]) == {str(ANNA), str(BOB), str(CECILIA)}
    assert len(event.payload["recipient_user_ids"]) == 3
    assert event.payload["message"] == message


def test_outbox_recipients_exclude_members_who_left(app, client, as_user, make_group):
    from sqlalchemy import update

    from app.models import ConversationMember

    group = make_group(owner=ANNA, members=(BOB, CECILIA))
    with app.app_context():
        db.session.execute(
            update(ConversationMember).where(ConversationMember.user_id == CECILIA).values(left_at=db.func.now())
        )
        db.session.commit()
    client.post(
        f"{BASE}/{group['id']}/messages",
        json={"client_msg_id": str(uuid.uuid4()), "body": "hi"},
        headers=as_user(ANNA),
    )
    (event,) = outbox_rows(app)
    assert set(event.payload["recipient_user_ids"]) == {str(ANNA), str(BOB)}


def test_message_validation(client, as_user, make_group):
    group = make_group()
    url = f"{BASE}/{group['id']}/messages"
    cmid = str(uuid.uuid4())
    for bad in (
        {"body": "no client id"},
        {"client_msg_id": "nope", "body": "x"},
        {"client_msg_id": cmid},
        {"client_msg_id": cmid, "body": ""},
        {"client_msg_id": cmid, "body": "   "},
        {"client_msg_id": cmid, "body": "x" * 4001},
        {"client_msg_id": cmid, "body": "x", "kind": "image"},
    ):
        assert client.post(url, json=bad, headers=as_user(ANNA)).status_code == 422, bad
    assert client.post(url, json={"client_msg_id": cmid, "body": "x" * 4000}, headers=as_user(ANNA)).status_code == 201


def test_concurrent_sends_get_unique_consecutive_seq(app, as_user, make_group):
    group = make_group(owner=ANNA, members=(BOB,))
    url = f"{BASE}/{group['id']}/messages"
    senders = [ANNA, BOB]
    requests = [
        (as_user(senders[i % 2]), {"client_msg_id": str(uuid.uuid4()), "body": f"m{i}"}) for i in range(20)
    ]
    barrier = threading.Barrier(20)

    def worker(item):
        headers, payload = item
        client = app.test_client()  # each thread has its own request, app context and db session
        barrier.wait()
        return client.post(url, json=payload, headers=headers)

    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(worker, requests))

    assert [r.status_code for r in responses] == [201] * 20
    assert sorted(r.get_json()["seq"] for r in responses) == list(range(1, 21))
    assert len(outbox_rows(app)) == 20

    with app.app_context():
        from app.models import Conversation

        assert db.session.scalar(select(Conversation.last_seq)) == 20
