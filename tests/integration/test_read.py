from tests.conftest import ANNA, BOB

BASE = "/api/v1/conversations"


def put_read(client, as_user, cid, seq, user=BOB):
    return client.put(f"{BASE}/{cid}/read", json={"seq": seq}, headers=as_user(user))


def test_read_position_only_moves_forward(client, as_user, make_group, send):
    cid = make_group(owner=ANNA, members=(BOB,))["id"]
    for _ in range(5):
        send(cid, ANNA)

    assert put_read(client, as_user, cid, 3).get_json() == {"last_read_seq": 3}
    assert put_read(client, as_user, cid, 1).get_json() == {"last_read_seq": 3}  # not backwards
    assert put_read(client, as_user, cid, 3).get_json() == {"last_read_seq": 3}
    assert put_read(client, as_user, cid, 5).get_json() == {"last_read_seq": 5}
    assert put_read(client, as_user, cid, 0).get_json() == {"last_read_seq": 5}


def test_read_position_is_per_member(client, as_user, make_group, send):
    cid = make_group(owner=ANNA, members=(BOB,))["id"]
    send(cid, ANNA)
    assert client.get(BASE, headers=as_user(BOB)).get_json()["items"][0]["unread_count"] == 1
    put_read(client, as_user, cid, 1, user=BOB)
    assert client.get(BASE, headers=as_user(BOB)).get_json()["items"][0]["unread_count"] == 0
    assert client.get(BASE, headers=as_user(ANNA)).get_json()["items"][0]["unread_count"] == 0


def test_read_beyond_last_seq_is_rejected(client, as_user, make_group, send):
    cid = make_group(owner=ANNA, members=(BOB,))["id"]
    send(cid, ANNA)
    response = put_read(client, as_user, cid, 2)
    assert response.status_code == 400
    assert put_read(client, as_user, cid, 1).get_json() == {"last_read_seq": 1}


def test_read_validation(client, as_user, make_group):
    cid = make_group(owner=ANNA, members=(BOB,))["id"]
    assert client.put(f"{BASE}/{cid}/read", json={}, headers=as_user(BOB)).status_code == 422
    assert put_read(client, as_user, cid, -1).status_code == 422
