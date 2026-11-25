from tests.conftest import ANNA

BASE = "/api/v1/conversations"


def seqs(response):
    return [m["seq"] for m in response.get_json()["items"]]


def setup_history(make_group, send, n=10):
    group = make_group()
    for i in range(1, n + 1):
        assert send(group["id"], body=f"m{i}").status_code == 201
    return group["id"]


def test_default_returns_latest_oldest_first(client, as_user, make_group, send):
    cid = setup_history(make_group, send)
    response = client.get(f"{BASE}/{cid}/messages?limit=4", headers=as_user(ANNA))
    assert seqs(response) == [7, 8, 9, 10]
    assert response.get_json()["has_more"] is True


def test_after_seq_pages_forward(client, as_user, make_group, send):
    cid = setup_history(make_group, send)
    url = f"{BASE}/{cid}/messages"
    first = client.get(f"{url}?after_seq=0&limit=4", headers=as_user(ANNA))
    assert seqs(first) == [1, 2, 3, 4] and first.get_json()["has_more"] is True

    second = client.get(f"{url}?after_seq=4&limit=4", headers=as_user(ANNA))
    assert seqs(second) == [5, 6, 7, 8] and second.get_json()["has_more"] is True

    last = client.get(f"{url}?after_seq=8&limit=4", headers=as_user(ANNA))
    assert seqs(last) == [9, 10] and last.get_json()["has_more"] is False

    nothing = client.get(f"{url}?after_seq=10", headers=as_user(ANNA))
    assert seqs(nothing) == [] and nothing.get_json()["has_more"] is False


def test_before_seq_pages_backward_oldest_first_within_page(client, as_user, make_group, send):
    cid = setup_history(make_group, send)
    url = f"{BASE}/{cid}/messages"
    page = client.get(f"{url}?before_seq=8&limit=3", headers=as_user(ANNA))
    assert seqs(page) == [5, 6, 7] and page.get_json()["has_more"] is True

    older = client.get(f"{url}?before_seq=5&limit=3", headers=as_user(ANNA))
    assert seqs(older) == [2, 3, 4] and older.get_json()["has_more"] is True

    oldest = client.get(f"{url}?before_seq=2&limit=3", headers=as_user(ANNA))
    assert seqs(oldest) == [1] and oldest.get_json()["has_more"] is False


def test_exact_fit_has_no_more(client, as_user, make_group, send):
    cid = setup_history(make_group, send, n=3)
    response = client.get(f"{BASE}/{cid}/messages?limit=3", headers=as_user(ANNA))
    assert seqs(response) == [1, 2, 3]
    assert response.get_json()["has_more"] is False


def test_limit_and_param_validation(client, as_user, make_group, send):
    cid = setup_history(make_group, send, n=1)
    url = f"{BASE}/{cid}/messages"
    for query in ("limit=0", "limit=101", "after_seq=-1", "before_seq=0", "after_seq=1&before_seq=5", "limit=x"):
        assert client.get(f"{url}?{query}", headers=as_user(ANNA)).status_code == 422, query
    assert client.get(f"{url}?limit=100", headers=as_user(ANNA)).status_code == 200
