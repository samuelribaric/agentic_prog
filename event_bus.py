"""Thread-safe event bus for streaming node execution events to the web UI."""

from __future__ import annotations

import json
import queue
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Generator


class EventType(Enum):
    NODE_START = "node_start"
    NODE_END = "node_end"
    TOOL_RESULT = "tool_result"
    LLM_RESPONSE = "llm_response"
    REPORT = "report"
    ERROR = "error"
    DONE = "done"


@dataclass
class Event:
    type: EventType
    node: str
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        """Format as a Server-Sent Event string."""
        payload = {
            "type": self.type.value,
            "node": self.node,
            "data": self.data,
            "timestamp": self.timestamp,
        }
        return f"data: {json.dumps(payload)}\n\n"


# Module-level singleton queue
_queue: queue.Queue[Event] = queue.Queue()


def emit(event: Event) -> None:
    """Push an event onto the bus (called from background thread)."""
    _queue.put(event)


def consume(timeout: float = 2.0) -> Generator[Event, None, None]:
    """Yield events from the bus. Sends keepalives on timeout. Stops on DONE."""
    while True:
        try:
            event = _queue.get(timeout=timeout)
            yield event
            if event.type == EventType.DONE:
                return
        except queue.Empty:
            # Send keepalive comment to keep SSE connection alive
            yield None  # Caller handles None as keepalive


def clear() -> None:
    """Drain the queue before starting a new run."""
    while not _queue.empty():
        try:
            _queue.get_nowait()
        except queue.Empty:
            break
