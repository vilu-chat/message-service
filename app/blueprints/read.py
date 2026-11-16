from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint

from app.auth import require_auth, require_member
from app.schemas import ReadPositionSchema, ReadUpdateSchema
from app.services import membership_service

blp = Blueprint(
    "read", __name__, url_prefix="/api/v1/conversations", description="Read positions"
)


@blp.route("/<uuid:conversation_id>/read")
class Read(MethodView):
    @require_auth
    @require_member
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.arguments(ReadUpdateSchema)
    @blp.response(200, ReadPositionSchema)
    def put(self, data, conversation_id):
        """Set last_read_seq. It only moves forward."""
        return {"last_read_seq": membership_service.mark_read(g.membership, data["seq"])}
