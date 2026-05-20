"""EventHub (non-Qt).

Stage 7.5.1:
  - Provide a lightweight publish/subscribe mechanism owned by AppContext.
  - Avoid Qt dependencies so unit tests remain stable on Windows.

Notes:
  - Handlers are invoked synchronously in the thread that calls `emit()`.
  - UI code should ensure emits happen on the UI thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar


T = TypeVar("T")


Handler = Callable[[T], None]


class Event(Generic[T]):
    """A simple typed event.

    Subscribers can register callables via `subscribe()` and remove them via
    the returned `unsubscribe()` function.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._lock = RLock()
        self._handlers: List[Handler[T]] = []

    @property
    def name(self) -> str:
        return self._name

    def subscribe(self, handler: Handler[T]) -> Callable[[], None]:
        with self._lock:
            self._handlers.append(handler)

        def _unsub() -> None:
            self.unsubscribe(handler)

        return _unsub

    def unsubscribe(self, handler: Handler[T]) -> None:
        with self._lock:
            self._handlers = [h for h in self._handlers if h is not handler]

    def emit(self, payload: T) -> None:
        # Copy handlers under lock, invoke outside lock.
        with self._lock:
            handlers = list(self._handlers)
        for h in handlers:
            try:
                h(payload)
            except Exception:
                # Events should never crash the app.
                continue


@dataclass(frozen=True)
class DbChanged:
    reason: str
    payload: Dict[str, Any]


@dataclass(frozen=True)
class ScanFinished:
    summary: Dict[str, Any]


@dataclass(frozen=True)
class HealthFinished:
    summary: Dict[str, Any]


@dataclass(frozen=True)
class ChecksumFinished:
    summary: Dict[str, Any]


class EventHub:
    """Central application event hub."""

    def __init__(self) -> None:
        self.db_changed: Event[DbChanged] = Event("db_changed")
        self.scan_finished: Event[ScanFinished] = Event("scan_finished")
        self.health_finished: Event[HealthFinished] = Event("health_finished")
        self.checksum_finished: Event[ChecksumFinished] = Event("checksum_finished")
