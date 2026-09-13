from rest_framework.exceptions import NotAuthenticated
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    """Session auth has no auth challenge, so DRF renders NotAuthenticated as
    403. The SPA needs to tell "sign in again" from "not allowed"; 401 says
    the first, 403 the second."""
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(exc, NotAuthenticated):
        response.status_code = 401
    return response
