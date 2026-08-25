import re
import asyncio
import json
import time

from fastapi import APIRouter, Request
from starlette.responses import StreamingResponse



_SAFE_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+~-]*\Z")


def _safe_version(value: object, fallback: str | None) -> str | None:
    if isinstance(value, str) and _SAFE_VERSION.fullmatch(value):
        return value
    return fallback


def _safe_pack_updated(envelope: str) -> str:
    try:
        message = json.loads(envelope)
    except (TypeError, ValueError):
        return envelope
    if not isinstance(message, dict) or message.get("type") != "pack.updated":
        return envelope
    data = message.get("data")
    if not isinstance(data, dict):
        data = {}
    safe_data: dict[str, object] = {}
    schema_version = data.get("schema_version")
    if isinstance(schema_version, int) and not isinstance(schema_version, bool):
        safe_data["schema_version"] = schema_version
    pack_version = _safe_version(data.get("pack_version"), None)
    if pack_version is not None:
        safe_data["pack_version"] = pack_version
    return json.dumps(
        {
            "type": "pack.updated",
            "ts": message.get("ts") if isinstance(message.get("ts"), str) else "",
            "data": safe_data,
        }
    )


def _safe_hello(app_version: str, pack_version: str | None) -> str:
    return json.dumps(
        {
            "type": "hello",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "data": {
                "app_version": _safe_version(app_version, "unknown"),
                "pack_version": _safe_version(pack_version, None),
            },
        }
    )


def event_stream(hub, queue: asyncio.Queue, app_version: str, pack_version: str | None = None):
    """Async generator yielding SSE frames; unsubscribes on cancellation."""
    hello = _safe_hello(app_version, pack_version)

    async def gen():
        yield f"data: {hello}\n\n"
        try:
            while True:
                try:
                    envelope = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {_safe_pack_updated(envelope)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            hub.unsubscribe(queue)

    return gen()


def build_events_router() -> APIRouter:
    router = APIRouter()

    @router.get("/events")
    async def events(request: Request):
        hub = request.app.state.hub
        queue = hub.subscribe()
        return StreamingResponse(
            event_stream(
                hub,
                queue,
                request.app.state.app_version,
                request.app.state.pack_version,
            ),
            media_type="text/event-stream",
        )

    return router
