import base64
import json

import pytest
from sqlalchemy import update

from app.extensions import db
from app.models import Conversation
from tests.conftest import ANNA, BOB

BASE = "/api/v1/conversations"


def get_page(client, as_user, query=""):
    response = client.get(f"{BASE}{query}", headers=as_user(ANNA))
    assert response.status_code == 200
    return response.get_json()


def walk(client, as_user, limit):
    """Follow next_cursor to the end; returns the list of pages."""
    pages, cursor = [], None
    while True:
        query = f"?limit={limit}" + (f"&cursor={cursor}" if cursor else "")
        page = get_page(client, as_user, query)
        pages.append(page)
        cursor = page["next_cursor"]
        if cursor is None:
            return pages
        assert len(pages) < 50, "pagination does not terminate"


def test_response_shape_and_defaults(client, as_user, make_group):
    make_group(owner=ANNA, members=(BOB,))
    page = get_page(client, as_user)
    assert set(page) == {"items", "next_cursor"}
    assert len(page["items"]) == 1
    assert page["next_cursor"] is None


def test_more_conversations_than_one_page(client, as_user, make_group):
    ids_oldest_first = [make_group(owner=ANNA, members=(BOB,), title=f"g{i}")["id"] for i in range(7)]

    pages = walk(client, as_user, limit=3)

    assert [len(p["items"]) for p in pages] == [3, 3, 1]
    assert [p["next_cursor"] is not None for p in pages] == [True, True, False]
    seen = [c["id"] for p in pages for c in p["items"]]
    assert seen == list(reversed(ids_oldest_first))  # newest first, no duplicates, no gaps
    assert get_page(client, as_user, "?limit=7")["next_cursor"] is None  # an exact fit has no next page


def test_pages_match_the_unpaginated_order(client, as_user, make_group, send):
    groups = [make_group(owner=ANNA, members=(BOB,), title=f"g{i}")["id"] for i in range(6)]
    send(groups[1], ANNA)  # activity reorders the list
    send(groups[4], BOB)

    everything = [c["id"] for c in get_page(client, as_user, "?limit=100")["items"]]
    paged = [c["id"] for p in walk(client, as_user, limit=2) for c in p["items"]]
    assert paged == everything
    assert everything[:2] == [groups[4], groups[1]]


def test_identical_updated_at_is_ordered_by_id_without_duplicates_or_gaps(app, client, as_user, make_group):
    groups = [make_group(owner=ANNA, members=(BOB,))["id"] for _ in range(7)]
    with app.app_context():
        db.session.execute(update(Conversation).values(updated_at=db.func.now()))
        db.session.commit()

    pages = walk(client, as_user, limit=2)
    seen = [c["id"] for p in pages for c in p["items"]]
    assert len(seen) == len(set(seen)) == 7
    assert set(seen) == set(groups)
    assert seen == sorted(seen, reverse=True)  # (updated_at desc, id desc) with equal updated_at


def test_items_keep_last_message_and_unread_count_on_every_page(client, as_user, make_group, send):
    groups = [make_group(owner=BOB, members=(ANNA,))["id"] for _ in range(4)]
    for g in groups:
        send(g, BOB, "hello")
    for page in walk(client, as_user, limit=3):
        for item in page["items"]:
            assert item["unread_count"] == 1
            assert item["last_message"]["body"] == "hello"


@pytest.mark.parametrize("limit", ["0", "101", "x", "-1"])
def test_limit_validation(client, as_user, limit):
    assert client.get(f"{BASE}?limit={limit}", headers=as_user(ANNA)).status_code == 422


def b64(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode()


@pytest.mark.parametrize(
    "cursor",
    [
        "garbage",
        "!!!!",
        b64("not a list"),
        b64([]),
        b64(["not-a-date", "0b1f6a4e-5c1d-4e8a-9a57-3f2d8c1a0001"]),
        b64(["2026-01-01T00:00:00+00:00", "not-a-uuid"]),
        b64(["2026-01-01T00:00:00", "0b1f6a4e-5c1d-4e8a-9a57-3f2d8c1a0001"]),  # no timezone
        b64([1, 2]),
    ],
)
def test_invalid_cursor_returns_400(client, as_user, cursor):
    response = client.get(f"{BASE}?cursor={cursor}", headers=as_user(ANNA))
    assert response.status_code == 400
    assert response.get_json()["status"] == "Bad Request"
