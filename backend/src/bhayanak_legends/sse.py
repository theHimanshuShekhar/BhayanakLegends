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
                if type_ != "sync.done":
                    # Progress is coalescible under pressure; /sync/status is
                    # the reconnect baseline, so dropping it is safe.
                    continue
                self._force_terminal(q, envelope)

    def _force_terminal(self, q: asyncio.Queue, envelope: str) -> None:
        """Make room for a terminal frame by evicting superseded progress.

        Buffered ``sync.done`` frames are preserved: every subscriber active at
        publication receives exactly one terminal frame per run, never zero.
        """
        kept_done_frames: list[str] = []
        superseded_progress: list[str] = []
        while True:
            try:
                old = q.get_nowait()
            except asyncio.QueueEmpty:
                break
            if '"type": "sync.done"' in old:
                kept_done_frames.append(old)
            else:
                superseded_progress.append(old)
        # Re-queue every terminal frame, then the newest progress that fits,
        # leaving exactly one slot for the terminal envelope being delivered.
        for old in kept_done_frames:
            q.put_nowait(old)
        capacity_left = q.maxsize - len(kept_done_frames) - 1
        for old in superseded_progress[-max(0, capacity_left):]:
            q.put_nowait(old)
        q.put_nowait(envelope)

