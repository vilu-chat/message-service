from app.errors import InvalidRequestError
from app.extensions import db
from app.models import ConversationMember
from app.repositories import conversation_repo, member_repo


def mark_read(membership: ConversationMember, seq: int) -> int:
    """Move the caller's read position forward; an older seq leaves it unchanged."""
    conversation = conversation_repo.get(membership.conversation_id)
    if seq > conversation.last_seq:
        raise InvalidRequestError("seq is beyond the last message of the conversation.")
    last_read_seq = member_repo.advance_read(membership.conversation_id, membership.user_id, seq)
    db.session.commit()
    return last_read_seq
