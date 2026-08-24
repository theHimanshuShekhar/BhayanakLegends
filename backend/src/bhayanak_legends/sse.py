import asyncio
import json
import time


class Hub:
    """Fan-out SSE hub: each subscriber gets its own bounded queue."""

    def __init__(self) -> None:
        self._subscribers: dict[int, asyncio.Queue] = {}
        self._next_id = 0

    def subscribe(self) -> asyncio.Queue:
        self._next_id += 1
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers[self._next_id] = q
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers = {
            i: queue for i, queue in self._subscribers.items() if queue is not q
        }

    async def publish(self, type_: str, data) -> None:
        envelope = json.dumps(
            {"type": type_, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "data": data}
        )
        for q in list(self._subscribers.values()):
            try:
                q.put_nowait(envelope)
            except asyncio.QueueFull:
                pass
