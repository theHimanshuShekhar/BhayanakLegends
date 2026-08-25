import logging
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

EXEMPT_PATHS: set[str] = set()
request_log = logging.getLogger("bhayanak_legends.requests")


def _host_matches_expected(host: str, expected_port: int) -> bool:
    if not host or any(char.isspace() or ord(char) < 32 for char in host):
        return False
    if host.startswith("["):
        closing = host.find("]")
        if closing < 0:
            return False
        hostname = host[1:closing]
        suffix = host[closing + 1 :]
        if hostname != "::1":
            return False
        if not suffix:
            return True
        if not suffix.startswith(":"):
            return False
        port = suffix[1:]
    else:
        if host.count(":") > 1:
            return False
        if ":" in host:
            hostname, port = host.rsplit(":", 1)
        else:
            hostname, port = host, None
        if hostname.lower() not in {"localhost", "127.0.0.1"}:
            return False
        if "@" in hostname or "[" in hostname or "]" in hostname:
            return False
    if port is None:
        return True
    return port.isdigit() and 1 <= int(port) <= 65535 and int(port) == expected_port


def _request_host_is_valid(request: Request) -> bool:
    values = [
        value
        for name, value in request.scope.get("headers", [])
        if name.lower() == b"host"
    ]
    if len(values) != 1:
        return False
    try:
        host = values[0].decode("ascii")
    except UnicodeDecodeError:
        return False
    config = getattr(request.app.state, "config", None)
    expected_port = getattr(request.app.state, "listener_port", None)
    if not isinstance(expected_port, int) or expected_port <= 0:
        expected_port = getattr(config, "port", 0)
    return isinstance(expected_port, int) and expected_port > 0 and _host_matches_expected(
        host, expected_port
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        finally:
            request_log.info("request %s %s", request.method, request.url.path)


class HostValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not _request_host_is_valid(request):
            return JSONResponse({"detail": "invalid host"}, status_code=400)
        return await call_next(request)


class TokenAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self.token = token
        self.token_bytes = token.encode("utf-8")

    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        provided = request.headers.get("X-BL-Token")
        if not provided and request.url.path == "/events":
            provided = request.query_params.get("token")
        if not provided or not secrets.compare_digest(
            provided.encode("utf-8"), self.token_bytes
        ):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)
