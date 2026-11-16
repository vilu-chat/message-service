import uuid

from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db


class Conversation(db.Model):
    __tablename__ = "conversations"
    __table_args__ = (db.CheckConstraint("type IN ('direct', 'group')", name="type"),)

    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    type = db.Column(db.String(10), nullable=False)
    title = db.Column(db.String(100), nullable=True)
    direct_key = db.Column(db.String(80), unique=True, nullable=True)
    created_by = db.Column(db.Uuid, nullable=False)  # Keycloak sub, no FK
    last_seq = db.Column(db.BigInteger, default=0, server_default="0", nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), onupdate=db.func.now(), nullable=False,)

    members = db.relationship("ConversationMember", back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True,)


class ConversationMember(db.Model):
    __tablename__ = "conversation_members"
    __table_args__ = (
        db.CheckConstraint("role IN ('member', 'admin')", name="role"),
        db.Index("ix_conversation_members_user_id", "user_id"),
    )

    conversation_id = db.Column(db.Uuid,db.ForeignKey("conversations.id", ondelete="CASCADE"),primary_key=True,)
    user_id = db.Column(db.Uuid, primary_key=True)  # Keycloak sub, no FK
    role = db.Column(db.String(10), default="member", server_default="member", nullable=False)
    joined_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    left_at = db.Column(db.DateTime(timezone=True), nullable=True)
    muted_until = db.Column(db.DateTime(timezone=True), nullable=True)
    last_read_seq = db.Column(db.BigInteger, default=0, server_default="0", nullable=False)

    conversation = db.relationship("Conversation", back_populates="members")


class Message(db.Model):
    __tablename__ = "messages"
    __table_args__ = (
        db.UniqueConstraint("conversation_id", "seq", name="uq_messages_conversation_id_seq"),
        db.UniqueConstraint("sender_id", "client_msg_id", name="uq_messages_sender_id_client_msg_id"),
        db.CheckConstraint("kind IN ('text', 'image', 'file', 'system')", name="kind"),
        db.CheckConstraint("char_length(body) <= 4000", name="body_length"),
    )

    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id = db.Column(db.Uuid, db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False,)
    seq = db.Column(db.BigInteger, nullable=False)
    sender_id = db.Column(db.Uuid, nullable=False)  # Keycloak sub, no FK
    client_msg_id = db.Column(db.Uuid, nullable=False)
    kind = db.Column(db.String(10), default="text", server_default="text", nullable=False)
    body = db.Column(db.Text, nullable=True)
    reply_to_id = db.Column(db.Uuid, db.ForeignKey("messages.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    edited_at = db.Column(db.DateTime(timezone=True), nullable=True)
    deleted_at = db.Column(db.DateTime(timezone=True), nullable=True)


class OutboxEvent(db.Model):  # same shape in both services
    __tablename__ = "outbox_events"
    __table_args__ = (
        # Partial index for the relay: only rows that still have to be published.
        db.Index("ix_outbox_unpublished", "id", postgresql_where=db.text("published_at IS NULL")),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    aggregate_id = db.Column(db.Uuid, nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    payload = db.Column(JSONB, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    published_at = db.Column(db.DateTime(timezone=True), nullable=True)
