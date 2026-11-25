from http import HTTPStatus

from flask import jsonify


class DomainError(Exception):
    """Raised by services; mapped to flask-smorest's error format (code, status, message)."""

    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidRequestError(DomainError):
    status_code = 400


class ConflictError(DomainError):
    status_code = 409


def register_error_handlers(app) -> None:
    @app.errorhandler(DomainError)
    def handle_domain_error(error: DomainError):
        status = HTTPStatus(error.status_code)
        body = {"code": status.value, "status": status.phrase, "message": error.message}
        return jsonify(body), status.value
