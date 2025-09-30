"""
In-memory event bus for server-sent events.

The `EventBus` class implements a publish/subscribe pattern using
`queue.Queue` objects for per-listener message buffering.  It supports
multiple concurrent subscribers and ensures that messages are delivered
non-blocking to all listeners.  Consumers can iterate over the generator
returned by `sse_stream()` to stream events to HTTP clients via the
Server-Sent Events (SSE) protocol.

"""

import threading
import json
import time
from queue import Queue, Empty
from typing import Dict, Optional, Set, Generator

class EventBus:
    """Publish/subscribe bus for application events."""

    def __init__(self) -> None:
        self._listeners: Set[Queue] = set()
        self._lock = threading.Lock()

    def add_listener(self) -> Queue:
        """Register a new listener and return its queue."""
        q: Queue = Queue()
        with self._lock:
            self._listeners.add(q)
        return q

    def remove_listener(self, q: Queue) -> None:
        """Remove a listener from the bus."""
        with self._lock:
            self._listeners.discard(q)

    def emit(self, event_type: str, message: str, meta: Optional[Dict[str, str]] = None) -> None:
        """Emit an event to all registered listeners."""
        payload = {
            "type": event_type,
            "message": message,
            "meta": meta or {},
            "ts": time.time(),
        }
        dead = []
        with self._lock:
            listeners = list(self._listeners)
        for q in listeners:
            try:
                q.put_nowait(payload)
            except Exception:
                dead.append(q)
        if dead:
            with self._lock:
                for q in dead:
                    self._listeners.discard(q)

    def sse_stream(self, q: Queue) -> Generator[str, None, None]:
        """
        Return a generator that yields SSE-formatted strings from the given
        listener queue.  The generator handles heartbeats and removes the
        listener when the generator exits.
        """
        yield "retry: 2000\n\n"
        try:
            while True:
                try:
                    evt = q.get(timeout=25)
                except Empty:
                    yield "event: ping\ndata: {}\n\n"
                    continue
                yield f"data: {json.dumps(evt)}\n\n"
        finally:
            self.remove_listener(q)