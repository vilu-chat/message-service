import uuid
from datetime import datetime

from sqlalchemy import select, tuple_, update

from app.extensions import db
from app.models import Conversation, ConversationMember


def get(conversation_id: uuid.UUID) -> Conversation | None:
    return db.session.get(Conversation, conversation_id)


def get_by_direct_key(direct_key: str) -> Conversation | None:
    return db.session.scalar(select(Conversation).where(Conversation.direct_key == direct_key))


def add(conversation: Conversation) -> Conversation:
    db.session.add(conversation)
    db.session.flush()
    return conversation


def next_seq(conversation_id) -> int:
    result = db.session.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(last_seq=Conversation.last_seq + 1)
        .returning(Conversation.last_seq)
    )
    return result.scalar_one()


def list_for_user(
    user_id: uuid.UUID, limit: int, after: tuple[datetime, uuid.UUID] | None = None
) -> list[tuple[Conversation, ConversationMember]]:
    """The user's active conversations with their membership row, ordered by (updated_at, id) descending.

    `after` is the (updated_at, id) of the last item of the previous page (keyset pagination).
    """
    query = (
        select(Conversation, ConversationMember)
        .join(ConversationMember, ConversationMember.conversation_id == Conversation.id)
        .where(ConversationMember.user_id == user_id, ConversationMember.left_at.is_(None))
    )
    if after is not None:
        query = query.where(tuple_(Conversation.updated_at, Conversation.id) < tuple_(*after))
    rows = db.session.execute(query.order_by(Conversation.updated_at.desc(), Conversation.id.desc()).limit(limit))
    return [(conversation, member) for conversation, member in rows]
