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


def preview_for(
    conversation_ids: list[uuid.UUID], exclude_user_id: uuid.UUID, limit: int = 4
) -> dict[uuid.UUID, tuple[int, list[uuid.UUID]]]:
    """Per conversation: (active member count incl. the caller, up to `limit` other members' IDs).

    One query for the whole page. Conversations where the caller is the only active member have no
    entry; callers treat that as (1, []).
    """
    if not conversation_ids:
        return {}

    ranked = (
        select(
            ConversationMember.conversation_id,
            ConversationMember.user_id,
            func.count().over(partition_by=ConversationMember.conversation_id).label("total"),
            func.row_number()
            .over(
                partition_by=ConversationMember.conversation_id,
                # The caller sorts last, so the first `limit` rows are other members.
                order_by=(
                    ConversationMember.user_id == exclude_user_id,
                    ConversationMember.joined_at,
                    ConversationMember.user_id,
                ),
            )
            .label("rn"),
        )
        .where(
            ConversationMember.conversation_id.in_(conversation_ids),
            ConversationMember.left_at.is_(None),
        )
        .subquery()
    )
    rows = db.session.execute(
        select(ranked.c.conversation_id, ranked.c.user_id, ranked.c.total)
        .where(ranked.c.rn <= limit, ranked.c.user_id != exclude_user_id)
        .order_by(ranked.c.conversation_id, ranked.c.rn)
    )

    out: dict[uuid.UUID, tuple[int, list[uuid.UUID]]] = {}
    for conversation_id, user_id, total in rows:
        _, ids = out.setdefault(conversation_id, (total, []))
        ids.append(user_id)
    return out


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
