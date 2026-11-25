from marshmallow import Schema, ValidationError, fields, validate, validates, validates_schema


class MessageCreateSchema(Schema):
    # Text messages only for now; image/file/attachments come with the attachment slice.
    client_msg_id = fields.UUID(required=True)
    kind = fields.String(load_default="text", validate=validate.OneOf(["text"]))
    body = fields.String(required=True, validate=validate.Length(min=1, max=4000))

    @validates("body")
    def body_not_blank(self, value, **kwargs):
        if not value.strip():
            raise ValidationError("A message needs a body.")


class MessageHistoryArgsSchema(Schema):
    after_seq = fields.Integer(validate=validate.Range(min=0))
    before_seq = fields.Integer(validate=validate.Range(min=1))
    limit = fields.Integer(load_default=50, validate=validate.Range(min=1, max=100))

    @validates_schema
    def one_direction(self, data, **kwargs):
        if "after_seq" in data and "before_seq" in data:
            raise ValidationError("Use either after_seq or before_seq, not both.")


class MessageSchema(Schema):
    id = fields.UUID(dump_only=True)
    conversation_id = fields.UUID(dump_only=True)
    seq = fields.Integer(dump_only=True)
    sender_id = fields.UUID(dump_only=True)
    client_msg_id = fields.UUID(dump_only=True)
    kind = fields.String(dump_only=True)
    body = fields.String(allow_none=True, dump_only=True)  # None when deleted
    reply_to_id = fields.UUID(allow_none=True, dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    edited_at = fields.DateTime(allow_none=True, dump_only=True)
    deleted_at = fields.DateTime(allow_none=True, dump_only=True)


class MessagePageSchema(Schema):
    items = fields.List(fields.Nested(MessageSchema), dump_only=True)
    has_more = fields.Boolean(dump_only=True)


class GroupCreateSchema(Schema):
    title = fields.String(required=True, validate=validate.Length(min=1, max=100))
    member_ids = fields.List(
        fields.UUID(), required=True, validate=validate.Length(min=1, max=99)
    )


class DirectCreateSchema(Schema):
    user_id = fields.UUID(required=True)


class ReadUpdateSchema(Schema):
    seq = fields.Integer(required=True, validate=validate.Range(min=0))


class ReadPositionSchema(Schema):
    last_read_seq = fields.Integer(dump_only=True)


class ConversationSummarySchema(Schema):
    id = fields.UUID(dump_only=True)
    type = fields.String(dump_only=True)
    title = fields.String(allow_none=True, dump_only=True)
    last_seq = fields.Integer(dump_only=True)
    unread_count = fields.Integer(dump_only=True)
    last_message = fields.Nested(MessageSchema, allow_none=True, dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    last_read_seq = fields.Integer(dump_only=True)  # the caller's read position
    member_count = fields.Integer(dump_only=True)  # active members, caller included
    # Up to 4 active members other than the caller, oldest join first: names a direct chat
    # (its only entry is the peer) and draws a group avatar without fetching the details.
    member_preview_ids = fields.List(fields.UUID(), dump_only=True)


class ConversationListArgsSchema(Schema):
    limit = fields.Integer(load_default=30, validate=validate.Range(min=1, max=100))
    cursor = fields.String()  # opaque; returned as next_cursor by the previous page


class ConversationPageSchema(Schema):
    items = fields.List(fields.Nested(ConversationSummarySchema), dump_only=True)
    next_cursor = fields.String(allow_none=True, dump_only=True)


class MemberSchema(Schema):
    user_id = fields.UUID(dump_only=True)
    role = fields.String(dump_only=True)
    joined_at = fields.DateTime(dump_only=True)


class ConversationSchema(Schema):
    # Details: the conversation and its active members
    id = fields.UUID(dump_only=True)
    type = fields.String(dump_only=True)
    title = fields.String(allow_none=True, dump_only=True)
    created_by = fields.UUID(dump_only=True)
    last_seq = fields.Integer(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    members = fields.List(fields.Nested(MemberSchema), dump_only=True)


# Events: the payload stored in outbox_events for message.created
class MessageCreatedDataSchema(Schema):
    message = fields.Nested(MessageSchema, required=True)
    recipient_user_ids = fields.List(fields.UUID(), required=True)  # active members


# Events: the payload stored in outbox_events for conversation.created
class ConversationCreatedDataSchema(Schema):
    conversation_id = fields.UUID(required=True)
    type = fields.String(required=True)
    title = fields.String(allow_none=True)
    created_by = fields.UUID(required=True)
    member_user_ids = fields.List(fields.UUID(), required=True)
