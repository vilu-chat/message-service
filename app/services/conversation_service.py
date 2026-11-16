import base64
import binascii
import json
import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from app.errors import InvalidRequestError
from app.extensions import db
from app.models import Conversation, ConversationMember, OutboxEvent
from app.repositories import conversation_repo, member_repo, message_repo, outbox_repo
from app.schemas import ConversationCreatedDataSchema


def direct_key(user_a: uuid.UUID, user_b: uuid.UUID) -> str:
    """The two user IDs sorted and joined, so a pair never gets two direct conversations."""
    return ":".join(sorted((str(user_a), str(user_b))))


def _add_created_event(conversation: Conversation, member_user_ids: list[uuid.UUID]) -> None:
    payload = ConversationCreatedDataSchema().dump(
        {
            "conversation_id": conversation.id,
            "type": conversation.type,
            "title": conversation.title,
            "created_by": conversation.created_by,
            "member_user_ids": member_user_ids,
        }
    )
    outbox_repo.add(
        OutboxEvent(aggregate_id=conversation.id, event_type="conversation.created", payload=payload)
    )


def _encode_cursor(updated_at: datetime, conversation_id: uuid.UUID) -> str:
    raw = json.dumps([updated_at.isoformat(), str(conversation_id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        updated_at_text, id_text = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        updated_at = datetime.fromisoformat(updated_at_text)
        if updated_at.tzinfo is None:
            raise ValueError("naive timestamp")
        return updated_at, uuid.UUID(id_text)
    except (ValueError, TypeError, binascii.Error, UnicodeError):
        raise InvalidRequestError("Invalid cursor.") from None


def _details(conversation: Conversation) -> dict:
    return {
        "id": conversation.id,
        "type": conversation.type,
        "title": conversation.title,
        "created_by": conversation.created_by,
        "last_seq": conversation.last_seq,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "members": member_repo.list_active(conversation.id),
    }


def get_or_create_direct(user_id: uuid.UUID, other_user_id: uuid.UUID) -> tuple[dict, bool]:
    """Returns (conversation details, created). Does not check that other_user_id exists."""
    if user_id == other_user_id:
        raise InvalidRequestError("You cannot start a direct conversation with yourself.")

    key = direct_key(user_id, other_user_id)
    conversation = conversation_repo.get_by_direct_key(key)
    if conversation is not None:
        return _details(conversation), False

    try:
        conversation = conversation_repo.add(
            Conversation(type="direct", direct_key=key, created_by=user_id)
        )
        member_repo.add_all(
            [
                ConversationMember(conversation_id=conversation.id, user_id=user_id),
                ConversationMember(conversation_id=conversation.id, user_id=other_user_id),
            ]
        )
        _add_created_event(conversation, [user_id, other_user_id])
        db.session.commit()
    except IntegrityError:
        # The other participant created it at the same moment (UNIQUE direct_key).
        db.session.rollback()
        conversation = conversation_repo.get_by_direct_key(key)
        if conversation is None:
            raise
        return _details(conversation), False
    return _details(conversation), True


def create_group(user_id: uuid.UUID, title: str, member_ids: list[uuid.UUID]) -> dict:
    others = list(dict.fromkeys(m for m in member_ids if m != user_id))
    conversation = conversation_repo.add(Conversation(type="group", title=title, created_by=user_id))
    member_repo.add_all(
        [ConversationMember(conversation_id=conversation.id, user_id=user_id, role="admin")]
        + [ConversationMember(conversation_id=conversation.id, user_id=m) for m in others]
    )
    _add_created_event(conversation, [user_id, *others])
    db.session.commit()
    return _details(conversation)


def get_details(conversation_id: uuid.UUID) -> dict:
    return _details(conversation_repo.get(conversation_id))


def list_mine(user_id: uuid.UUID, limit: int, cursor: str | None = None) -> dict:
    after = _decode_cursor(cursor) if cursor else None
    rows = conversation_repo.list_for_user(user_id, limit + 1, after)
    has_more = len(rows) > limit
    rows = rows[:limit]

    last_messages = message_repo.get_many(
        [(conversation.id, conversation.last_seq) for conversation, _ in rows if conversation.last_seq > 0]
    )
    by_key = {(m.conversation_id, m.seq): m for m in last_messages}
    items = [
        {
            "id": conversation.id,
            "type": conversation.type,
            "title": conversation.title,
            "last_seq": conversation.last_seq,
            "unread_count": max(conversation.last_seq - member.last_read_seq, 0),
            "last_message": by_key.get((conversation.id, conversation.last_seq)),
            "updated_at": conversation.updated_at,
        }
        for conversation, member in rows
    ]
    last = rows[-1][0] if has_more else None
    return {
        "items": items,
        "next_cursor": _encode_cursor(last.updated_at, last.id) if last else None,
    }
