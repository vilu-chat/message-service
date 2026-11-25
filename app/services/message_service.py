from sqlalchemy.exc import IntegrityError

from app.errors import ConflictError
from app.extensions import db
from app.models import ConversationMember, Message, OutboxEvent
from app.repositories import conversation_repo, member_repo, message_repo, outbox_repo
from app.schemas import MessageCreatedDataSchema


def _already_sent(existing: Message, conversation_id) -> tuple[Message, bool]:
    # UNIQUE (sender_id, client_msg_id) spans all conversations, so a reused id is a client bug.
    if existing.conversation_id != conversation_id:
        raise ConflictError("client_msg_id was already used for a message in another conversation.")
    return existing, False


def send(membership: ConversationMember, data: dict) -> tuple[Message, bool]:
    """Send a text message. Returns (message, created); created is False for a retried client_msg_id.

    One transaction: bump last_seq, insert the message, advance the sender's read position,
    insert the outbox row, commit.
    """
    conversation_id = membership.conversation_id
    sender_id = membership.user_id
    client_msg_id = data["client_msg_id"]

    existing = message_repo.get_by_client_msg_id(sender_id, client_msg_id)
    if existing is not None:
        return _already_sent(existing, conversation_id)

    try:
        seq = conversation_repo.next_seq(conversation_id)
        message = message_repo.add(
            Message(
                conversation_id=conversation_id,
                seq=seq,
                sender_id=sender_id,
                client_msg_id=client_msg_id,
                kind=data["kind"],
                body=data["body"],
            )
        )
        # The sender has obviously seen everything up to their own message.
        member_repo.advance_read(conversation_id, sender_id, seq)
        recipient_ids = [m.user_id for m in member_repo.list_active(conversation_id)]
        payload = MessageCreatedDataSchema().dump(
            {"message": message, "recipient_user_ids": recipient_ids}
        )
        outbox_repo.add(
            OutboxEvent(aggregate_id=conversation_id, event_type="message.created", payload=payload)
        )
        db.session.commit()
    except IntegrityError:
        # A concurrent retry of the same client_msg_id won. Rolling back also undoes our seq bump.
        db.session.rollback()
        existing = message_repo.get_by_client_msg_id(sender_id, client_msg_id)
        if existing is None:
            raise
        return _already_sent(existing, conversation_id)
    return message, True


def history(membership: ConversationMember, after_seq=None, before_seq=None, limit=50) -> dict:
    """A page of messages, oldest first within the page."""
    conversation_id = membership.conversation_id
    if after_seq is not None:
        rows = message_repo.after(conversation_id, after_seq, limit + 1)
        return {"items": rows[:limit], "has_more": len(rows) > limit}

    rows = message_repo.before(conversation_id, before_seq, limit + 1)
    return {"items": list(reversed(rows[:limit])), "has_more": len(rows) > limit}
