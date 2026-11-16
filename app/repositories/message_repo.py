import uuid

from sqlalchemy import select, tuple_

from app.extensions import db
from app.models import Message


def add(message: Message) -> Message:
    db.session.add(message)
    db.session.flush()
    return message


def get_by_client_msg_id(sender_id: uuid.UUID, client_msg_id: uuid.UUID) -> Message | None:
    return db.session.scalar(
        select(Message).where(Message.sender_id == sender_id, Message.client_msg_id == client_msg_id)
    )


def after(conversation_id: uuid.UUID, after_seq: int, limit: int) -> list[Message]:
    """Messages with seq > after_seq, oldest first."""
    return list(
        db.session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.seq > after_seq)
            .order_by(Message.seq)
            .limit(limit)
        )
    )


def before(conversation_id: uuid.UUID, before_seq: int | None, limit: int) -> list[Message]:
    """The newest messages below before_seq (or the newest overall), newest first."""
    query = select(Message).where(Message.conversation_id == conversation_id)
    if before_seq is not None:
        query = query.where(Message.seq < before_seq)
    return list(db.session.scalars(query.order_by(Message.seq.desc()).limit(limit)))


def get_many(conversation_seq_pairs: list[tuple[uuid.UUID, int]]) -> list[Message]:
    """Fetch messages by (conversation_id, seq), served by the UNIQUE (conversation_id, seq) index."""
    if not conversation_seq_pairs:
        return []
    return list(
        db.session.scalars(
            select(Message).where(
                tuple_(Message.conversation_id, Message.seq).in_(conversation_seq_pairs)
            )
        )
    )
