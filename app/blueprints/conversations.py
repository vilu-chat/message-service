from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint

from app.auth import require_auth, require_member
from app.schemas import (
    ConversationSchema,
    ConversationListArgsSchema,
    ConversationPageSchema,
    DirectCreateSchema,
    GroupCreateSchema,
)
from app.services import conversation_service

blp = Blueprint(
    "conversations", __name__, url_prefix="/api/v1/conversations", description="Conversations"
)

SECURITY = [{"bearerAuth": []}]


@blp.route("")
class Conversations(MethodView):
    @require_auth
    @blp.doc(security=SECURITY)
    @blp.arguments(ConversationListArgsSchema, location="query")
    @blp.response(200, ConversationPageSchema)
    def get(self, args):
        """My conversations with last message and unread count, newest activity first (cursor pagination)."""
        return conversation_service.list_mine(g.current_user_id, args["limit"], args.get("cursor"))

    @require_auth
    @blp.doc(security=SECURITY)
    @blp.arguments(GroupCreateSchema)
    @blp.response(201, ConversationSchema)
    def post(self, data):
        """Create a group; the caller becomes its admin."""
        return conversation_service.create_group(g.current_user_id, data["title"], data["member_ids"])


@blp.route("/direct")
class Direct(MethodView):
    @require_auth
    @blp.doc(security=SECURITY)
    @blp.arguments(DirectCreateSchema)
    @blp.response(200, ConversationSchema)
    def post(self, data):
        """Get or create the direct conversation with a user (201 when created, 200 when it existed)."""
        conversation, created = conversation_service.get_or_create_direct(
            g.current_user_id, data["user_id"]
        )
        return conversation, 201 if created else 200


@blp.route("/<uuid:conversation_id>")
class ConversationDetail(MethodView):
    @require_auth
    @require_member
    @blp.doc(security=SECURITY)
    @blp.response(200, ConversationSchema)
    def get(self, conversation_id):
        return conversation_service.get_details(conversation_id)
