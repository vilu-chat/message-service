import uuid

import pytest
from sqlalchemy import update

from app.extensions import db
from app.models import ConversationMember
from tests.conftest import ANNA, BOB, DAVE

BASE = "/api/v1/conversations"


def conversation_endpoints(cid):
    msg = {"client_msg_id": str(uuid.uuid4()), "body": "hi"}
    return [
        ("get", f"{BASE}/{cid}", None),
        ("get", f"{BASE}/{cid}/messages", None),
        ("post", f"{BASE}/{cid}/messages", msg),
        ("put", f"{BASE}/{cid}/read", {"seq": 0}),
    ]


def call(client, method, url, body, headers):
    return getattr(client, method)(url, json=body, headers=headers)


@pytest.mark.parametrize("index", range(4))
def test_non_member_gets_404_on_every_conversation_endpoint(client, as_user, make_group, index):
    group = make_group(owner=ANNA, members=(BOB,))
    method, url, body = conversation_endpoints(group["id"])[index]
    response = call(client, method, url, body, as_user(DAVE))
    assert response.status_code == 404


def test_404_is_identical_for_unknown_and_foreign_conversations(client, as_user, make_group):
    group = make_group(owner=ANNA, members=(BOB,))
    foreign = client.get(f"{BASE}/{group['id']}", headers=as_user(DAVE))
    unknown = client.get(f"{BASE}/{uuid.uuid4()}", headers=as_user(DAVE))
    assert foreign.status_code == unknown.status_code == 404
    assert foreign.get_json() == unknown.get_json()


def test_member_who_left_gets_404(app, client, as_user, make_group):
    group = make_group(owner=ANNA, members=(BOB,))
    with app.app_context():
        db.session.execute(
            update(ConversationMember)
            .where(ConversationMember.user_id == BOB)
            .values(left_at=db.func.now())
        )
        db.session.commit()
    assert client.get(f"{BASE}/{group['id']}", headers=as_user(BOB)).status_code == 404
    assert client.get(f"{BASE}/{group['id']}", headers=as_user(ANNA)).status_code == 200
    assert client.get(BASE, headers=as_user(BOB)).get_json()["items"] == []
