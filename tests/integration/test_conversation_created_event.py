from sqlalchemy import select

from app.extensions import db
from app.models import OutboxEvent
from tests.conftest import ANNA, BOB, CECILIA

BASE = "/api/v1/conversations"


def events(app, event_type="conversation.created"):
    with app.app_context():
        return list(
            db.session.scalars(
                select(OutboxEvent).where(OutboxEvent.event_type == event_type).order_by(OutboxEvent.id)
            )
        )


def test_group_create_writes_one_event(app, client, as_user):
    response = client.post(
        BASE, json={"title": "Team", "member_ids": [str(BOB), str(CECILIA)]}, headers=as_user(ANNA)
    )
    group = response.get_json()

    (event,) = events(app)
    assert str(event.aggregate_id) == group["id"]
    assert event.published_at is None
    assert set(event.payload) == {"conversation_id", "type", "title", "created_by", "member_user_ids"}
    assert event.payload["conversation_id"] == group["id"]
    assert event.payload["type"] == "group"
    assert event.payload["title"] == "Team"
    assert event.payload["created_by"] == str(ANNA)
    assert set(event.payload["member_user_ids"]) == {str(ANNA), str(BOB), str(CECILIA)}
    assert len(event.payload["member_user_ids"]) == 3


def test_direct_create_writes_one_event_and_repeats_write_none(app, client, as_user):
    first = client.post(f"{BASE}/direct", json={"user_id": str(BOB)}, headers=as_user(ANNA))
    client.post(f"{BASE}/direct", json={"user_id": str(BOB)}, headers=as_user(ANNA))
    client.post(f"{BASE}/direct", json={"user_id": str(ANNA)}, headers=as_user(BOB))

    (event,) = events(app)
    assert str(event.aggregate_id) == first.get_json()["id"]
    assert event.payload["type"] == "direct"
    assert event.payload["title"] is None
    assert event.payload["created_by"] == str(ANNA)
    assert set(event.payload["member_user_ids"]) == {str(ANNA), str(BOB)}


def test_rejected_requests_write_no_event(app, client, as_user):
    client.post(f"{BASE}/direct", json={"user_id": str(ANNA)}, headers=as_user(ANNA))  # yourself
    client.post(BASE, json={"title": "", "member_ids": [str(BOB)]}, headers=as_user(ANNA))  # invalid
    assert events(app) == []


def test_sending_does_not_write_conversation_events(app, client, as_user, make_group, send):
    cid = make_group()["id"]
    send(cid, ANNA)
    assert len(events(app)) == 1
    assert len(events(app, "message.created")) == 1
