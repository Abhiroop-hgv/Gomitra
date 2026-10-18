"""Domain errors. Services raise these; only the API layer turns them into HTTP responses (see api/app.py).

Keeping HTTP out of the services means the business logic can be tested and reused without a web framework.
"""


class AppError(Exception):
    status = 500

    def __init__(self, detail):
        super().__init__(detail)
        self.detail = detail


class BadRequest(AppError):
    status = 400


class Forbidden(AppError):
    status = 403


class NotFound(AppError):
    status = 404


class TooLarge(AppError):
    status = 413


class UnsupportedMedia(AppError):
    status = 415


class Unprocessable(AppError):
    status = 422


class UpstreamError(AppError):
    """A model, Gemini or another Google service failed or answered with an error."""
    status = 502
