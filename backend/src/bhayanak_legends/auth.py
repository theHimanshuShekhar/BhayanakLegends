import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

EXEMPT_PATHS = {"/health"}


class TokenAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        provided = request.headers.get("X-BL-Token")
        if not provided and request.url.path == "/events":
            provided = request.query_params.get("token")

        if not provided or not secrets.compare_digest(provided, self.token):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)
