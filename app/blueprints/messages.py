from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint

from app.auth import require_auth, require_member
from app.schemas import (
    MessageCreateSchema,
    MessageHistoryArgsSchema,
    MessagePageSchema,
    MessageSchema,
)
from app.services import message_service

blp = Blueprint(
    "messages", __name__, url_prefix="/api/v1/conversations", description="Messages"
)

SECURITY = [{"bearerAuth": []}]


@blp.route("/<uuid:conversation_id>/messages")
class Messages(MethodView):
    @require_auth
    @require_member
    @blp.doc(security=SECURITY)
    @blp.arguments(MessageHistoryArgsSchema, location="query")
    @blp.response(200, MessagePageSchema)
    def get(self, args, conversation_id):
        """History and sync: after_seq, before_seq (not both) and limit."""
        return message_service.history(g.membership, **args)

    @require_auth
    @require_member
    @blp.doc(security=SECURITY)
    @blp.arguments(MessageCreateSchema)
    @blp.response(201, MessageSchema)
    def post(self, data, conversation_id):
        """Send a message. Idempotent on client_msg_id (201 when created, 200 when it already existed)."""
        message, created = message_service.send(g.membership, data)
        return message, 201 if created else 200
