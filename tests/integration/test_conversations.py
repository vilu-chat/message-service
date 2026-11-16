import uuid

from tests.conftest import ANNA, BOB, CECILIA

BASE = "/api/v1/conversations"


def test_direct_is_idempotent_and_symmetric(client, as_user):
    first = client.post(f"{BASE}/direct", json={"user_id": str(BOB)}, headers=as_user(ANNA))
    again = client.post(f"{BASE}/direct", json={"user_id": str(BOB)}, headers=as_user(ANNA))
    reverse = client.post(f"{BASE}/direct", json={"user_id": str(ANNA)}, headers=as_user(BOB))

    assert first.status_code == 201
    assert again.status_code == 200
    assert reverse.status_code == 200
    assert first.get_json()["id"] == again.get_json()["id"] == reverse.get_json()["id"]

    body = first.get_json()
    assert body["type"] == "direct"
    assert {m["user_id"] for m in body["members"]} == {str(ANNA), str(BOB)}


def test_direct_with_yourself_is_rejected(client, as_user):
    response = client.post(f"{BASE}/direct", json={"user_id": str(ANNA)}, headers=as_user(ANNA))
    assert response.status_code == 400
    assert response.get_json()["status"] == "Bad Request"


def test_direct_requires_a_uuid(client, as_user):
    response = client.post(f"{BASE}/direct", json={"user_id": "nope"}, headers=as_user(ANNA))
    assert response.status_code == 422


def test_create_group(client, as_user):
    response = client.post(
        BASE,
        json={"title": "Team", "member_ids": [str(BOB), str(CECILIA), str(BOB), str(ANNA)]},
        headers=as_user(ANNA),
    )
    assert response.status_code == 201
    body = response.get_json()
    assert body["type"] == "group"
    assert body["title"] == "Team"
    assert body["created_by"] == str(ANNA)
    roles = {m["user_id"]: m["role"] for m in body["members"]}
    assert roles == {str(ANNA): "admin", str(BOB): "member", str(CECILIA): "member"}


def test_group_validation(client, as_user):
    assert client.post(BASE, json={"member_ids": [str(BOB)]}, headers=as_user(ANNA)).status_code == 422
    assert client.post(BASE, json={"title": "x", "member_ids": []}, headers=as_user(ANNA)).status_code == 422


def test_get_conversation_details(client, as_user, make_group):
    group = make_group()
    response = client.get(f"{BASE}/{group['id']}", headers=as_user(BOB))
    assert response.status_code == 200
    assert response.get_json()["id"] == group["id"]
    assert len(response.get_json()["members"]) == 3


def items(client, as_user, user, query=""):
    response = client.get(f"{BASE}{query}", headers=as_user(user))
    assert response.status_code == 200
    return response.get_json()["items"]


def test_list_has_last_message_and_unread_count(client, as_user, make_group, send):
    group = make_group(owner=ANNA, members=(BOB,))
    empty = items(client, as_user, BOB)
    assert empty[0]["last_message"] is None
    assert empty[0]["unread_count"] == 0

    send(group["id"], ANNA, "one")
    send(group["id"], ANNA, "two")

    bob = items(client, as_user, BOB)
    assert len(bob) == 1
    assert bob[0]["last_seq"] == 2
    assert bob[0]["last_message"]["body"] == "two"
    assert bob[0]["last_message"]["seq"] == 2
    assert bob[0]["unread_count"] == 2
    assert items(client, as_user, ANNA)[0]["unread_count"] == 0  # own messages are not unread

    client.put(f"{BASE}/{group['id']}/read", json={"seq": 1}, headers=as_user(BOB))
    assert items(client, as_user, BOB)[0]["unread_count"] == 1


def test_sending_marks_own_message_read_and_raises_recipients_unread(client, as_user, make_group, send):
    cid = make_group(owner=ANNA, members=(BOB, CECILIA))["id"]
    send(cid, ANNA, "one")
    send(cid, ANNA, "two")
    assert [items(client, as_user, u)[0]["unread_count"] for u in (ANNA, BOB, CECILIA)] == [0, 2, 2]

    send(cid, BOB, "reply")  # sending also covers everything before it
    assert [items(client, as_user, u)[0]["unread_count"] for u in (ANNA, BOB, CECILIA)] == [1, 0, 3]


def test_read_position_set_by_send_never_moves_backwards(app, client, as_user, make_group, send):
    from sqlalchemy import select

    from app.extensions import db
    from app.models import ConversationMember

    cid = make_group(owner=ANNA, members=(BOB,))["id"]
    for _ in range(3):
        send(cid, ANNA)
    client.put(f"{BASE}/{cid}/read", json={"seq": 3}, headers=as_user(BOB))
    send(cid, ANNA)  # seq 4: Anna moves to 4, Bob stays at 3

    with app.app_context():
        positions = {
            m.user_id: m.last_read_seq for m in db.session.scalars(select(ConversationMember))
        }
    assert positions == {ANNA: 4, BOB: 3}


def test_list_is_newest_activity_first_and_only_mine(client, as_user, make_group, send):
    older = make_group(owner=ANNA, members=(BOB,), title="older")
    newer = make_group(owner=ANNA, members=(BOB,), title="newer")
    make_group(owner=CECILIA, members=(BOB,), title="not anna's")

    assert [c["title"] for c in items(client, as_user, ANNA)] == ["newer", "older"]

    send(older["id"], ANNA, "bump")
    assert [c["title"] for c in items(client, as_user, ANNA)] == ["older", "newer"]
    assert newer["id"] not in [c["id"] for c in items(client, as_user, CECILIA)]
