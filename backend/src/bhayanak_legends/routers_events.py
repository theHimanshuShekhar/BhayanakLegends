import asyncio
import json
import time

from fastapi import APIRouter, Request
from starlette.responses import StreamingResponse


def event_stream(hub, queue: asyncio.Queue, app_version: str):
    """Async generator yielding SSE frames; unsubscribes on cancellation."""
    hello = json.dumps(
        {
            "type": "hello",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "data": {"app_version": app_version},
        }
    )

    async def gen():
        yield f"data: {hello}\n\n"
        try:
            while True:
                try:
                    envelope = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {envelope}\n\n"
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
            event_stream(hub, queue, request.app.state.app_version),
            media_type="text/event-stream",
        )

    return router
