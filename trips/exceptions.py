"""Consistent, user-friendly API error responses."""
from rest_framework.response import Response
from rest_framework.views import exception_handler


class PlanningError(Exception):
    """Raised when a trip cannot be planned (bad location, routing failure...)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class GeocodingError(PlanningError):
    pass


class RoutingError(PlanningError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message, status_code=status_code)


def api_exception_handler(exc, context):
    if isinstance(exc, PlanningError):
        return Response({"detail": exc.message}, status=exc.status_code)
    return exception_handler(exc, context)
