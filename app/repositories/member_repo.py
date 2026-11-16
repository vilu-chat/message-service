import uuid

from sqlalchemy import func, select, update

from app.extensions import db
from app.models import ConversationMember


def get_active(conversation_id: uuid.UUID, user_id: uuid.UUID) -> ConversationMember | None:
    return db.session.scalar(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id,
            ConversationMember.left_at.is_(None),
        )
    )


def list_active(conversation_id: uuid.UUID) -> list[ConversationMember]:
    return list(
        db.session.scalars(
            select(ConversationMember)
            .where(
                ConversationMember.conversation_id == conversation_id,
                ConversationMember.left_at.is_(None),
            )
            .order_by(ConversationMember.joined_at, ConversationMember.user_id)
        )
    )


def add_all(members: list[ConversationMember]) -> None:
    db.session.add_all(members)
    db.session.flush()


def advance_read(conversation_id: uuid.UUID, user_id: uuid.UUID, seq: int) -> int:
    """Atomically move last_read_seq forward (never back) and return the stored value."""
    result = db.session.execute(
        update(ConversationMember)
        .where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id,
        )
        .values(last_read_seq=func.greatest(ConversationMember.last_read_seq, seq))
        .returning(ConversationMember.last_read_seq)
        .execution_options(synchronize_session=False)
    )
    return result.scalar_one()
