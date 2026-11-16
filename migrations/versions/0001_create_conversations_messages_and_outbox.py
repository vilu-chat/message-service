"""create conversations messages and outbox

Reviewed by hand against design.md, "Message Service: database" (no attachments table yet).

Revision ID: 0001
Revises: 
Create Date: 2026-11-16 17:56:09.764215

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('conversations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('type', sa.String(length=10), nullable=False),
    sa.Column('title', sa.String(length=100), nullable=True),
    sa.Column('direct_key', sa.String(length=80), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('last_seq', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("type IN ('direct', 'group')", name=op.f('ck_conversations_type')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations')),
    sa.UniqueConstraint('direct_key', name=op.f('uq_conversations_direct_key'))
    )
    op.create_table('outbox_events',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('aggregate_id', sa.Uuid(), nullable=False),
    sa.Column('event_type', sa.String(length=50), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_outbox_events'))
    )
    op.create_index('ix_outbox_unpublished', 'outbox_events', ['id'], postgresql_where=sa.text('published_at IS NULL'))
    op.create_table('conversation_members',
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.String(length=10), server_default='member', nullable=False),
    sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('left_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('muted_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_read_seq', sa.BigInteger(), server_default='0', nullable=False),
    sa.CheckConstraint("role IN ('member', 'admin')", name=op.f('ck_conversation_members_role')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_conversation_members_conversation_id_conversations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('conversation_id', 'user_id', name=op.f('pk_conversation_members'))
    )
    op.create_index('ix_conversation_members_user_id', 'conversation_members', ['user_id'])
    op.create_table('messages',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('seq', sa.BigInteger(), nullable=False),
    sa.Column('sender_id', sa.Uuid(), nullable=False),
    sa.Column('client_msg_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=10), server_default='text', nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('reply_to_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("kind IN ('text', 'image', 'file', 'system')", name=op.f('ck_messages_kind')),
    sa.CheckConstraint('char_length(body) <= 4000', name=op.f('ck_messages_body_length')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reply_to_id'], ['messages.id'], name=op.f('fk_messages_reply_to_id_messages')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages')),
    sa.UniqueConstraint('conversation_id', 'seq', name=op.f('uq_messages_conversation_id_seq')),
    sa.UniqueConstraint('sender_id', 'client_msg_id', name=op.f('uq_messages_sender_id_client_msg_id'))
    )


def downgrade():
    op.drop_table('messages')
    op.drop_index('ix_conversation_members_user_id', table_name='conversation_members')
    op.drop_table('conversation_members')
    op.drop_index('ix_outbox_unpublished', table_name='outbox_events', postgresql_where=sa.text('published_at IS NULL'))
    op.drop_table('outbox_events')
    op.drop_table('conversations')
