import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import load_dotenv
from flask_migrate import downgrade, upgrade
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import text

load_dotenv()

ISSUER = "http://localhost:8081/realms/chat"
AUDIENCE = "chat-api"
KID = "test-key"


def _test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.exit("TEST_DATABASE_URL is not set (see .env.example)", returncode=2)
    # The reset fixture truncates tables, so refuse anything that is not a test database.
    if not url.rsplit("/", 1)[-1].split("?")[0].endswith("_test"):
        pytest.exit("TEST_DATABASE_URL must point at a database whose name ends in _test", returncode=2)
    return url


@pytest.fixture(scope="session")
def app():
    # Hermetic config: tests never use whatever is in .env or the shell.
    os.environ["SQLALCHEMY_DATABASE_URI"] = _test_database_url()
    os.environ["KEYCLOAK_ISSUER"] = ISSUER
    os.environ["KEYCLOAK_JWKS_URL"] = "http://jwks.invalid/certs"  # never fetched, see jwks_patch
    os.environ["KEYCLOAK_AUDIENCE"] = AUDIENCE

    from app import create_app

    app = create_app()
    with app.app_context():
        downgrade(revision="base")  # start from an empty schema, which also exercises downgrade
        upgrade()
    yield app


@pytest.fixture(autouse=True)
def reset_data(app):
    yield
    from app.extensions import db

    with app.app_context():
        db.session.execute(text("TRUNCATE TABLE conversations, outbox_events RESTART IDENTITY CASCADE"))
        db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def jwks_patch(monkeypatch, rsa_key):
    """The JWKS lookup returns the test public key instead of calling the network."""
    jwk = RSAAlgorithm.to_jwk(rsa_key.public_key(), as_dict=True)
    jwk.update(kid=KID, use="sig", alg="RS256")
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [jwk]})


@pytest.fixture
def make_token(rsa_key):
    def _make(*, key=None, headers=None, expires_in=300, **overrides):
        now = datetime.now(timezone.utc)
        claims = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": str(uuid.uuid4()),
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
            "name": "Anna Andersson",
            "preferred_username": "anna",
            "email": "anna@example.test",
            "realm_access": {"roles": ["user"]},
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(
            claims, key or rsa_key, algorithm="RS256", headers={"kid": KID, **(headers or {})}
        )

    return _make


@pytest.fixture
def auth_header(make_token):
    def _header(**kwargs):
        return {"Authorization": f"Bearer {make_token(**kwargs)}"}

    return _header


# Fixed user IDs (Keycloak sub values) for readable tests.
ANNA = uuid.UUID("0b1f6a4e-5c1d-4e8a-9a57-3f2d8c1a0001")
BOB = uuid.UUID("0b1f6a4e-5c1d-4e8a-9a57-3f2d8c1a0002")
CECILIA = uuid.UUID("0b1f6a4e-5c1d-4e8a-9a57-3f2d8c1a0003")
DAVE = uuid.UUID("0b1f6a4e-5c1d-4e8a-9a57-3f2d8c1a0004")  # never a member of anything


@pytest.fixture
def as_user(auth_header):
    """Headers for a given user: as_user(ANNA)."""

    def _headers(user_id):
        return auth_header(sub=str(user_id))

    return _headers


@pytest.fixture
def make_group(client, as_user):
    def _make(owner=ANNA, members=(BOB, CECILIA), title="Team"):
        response = client.post(
            "/api/v1/conversations",
            json={"title": title, "member_ids": [str(m) for m in members]},
            headers=as_user(owner),
        )
        assert response.status_code == 201
        return response.get_json()

    return _make


@pytest.fixture
def send(client, as_user):
    """send(conversation_id, user, body="hi", client_msg_id=None) -> response"""

    def _send(conversation_id, user=ANNA, body="hi", client_msg_id=None):
        return client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"client_msg_id": str(client_msg_id or uuid.uuid4()), "body": body},
            headers=as_user(user),
        )

    return _send
