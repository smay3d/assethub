"""AppLog: small, UI-friendly application log.

Stage 7.6.1:
  - Provide ctx.log.{info,warn,error}(msg) for consistent summary reporting.
  - Keep this module Qt-free (tests must remain stable without QApplication).

Design:
  - Keeps the last N formatted lines in memory.
  - Optional sink callback receives each formatted line (for UI display).
  - Thread-safe; safe to call from any thread.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Callable, Deque, List, Optional


@dataclass(frozen=True)
class LogLine:
    timestamp: str
    level: str
    message: str

    def format(self) -> str:
        # Fixed width level keeps scanning easy.
        return f"{self.timestamp} {self.level:<5} {self.message}"


class AppLog:
    """In-memory application log with an optional live sink."""

    def __init__(self, *, max_lines: int = 800) -> None:
        self._max_lines = int(max_lines)
        self._lock = RLock()
        self._lines: Deque[str] = deque(maxlen=self._max_lines)
        self._sink: Optional[Callable[[str], None]] = None

    @property
    def max_lines(self) -> int:
        return self._max_lines

    # -----------------
    # Public API
    # -----------------

    def set_sink(self, sink: Optional[Callable[[str], None]]) -> None:
        """Set a callback to receive each formatted line.

        The sink must be thread-safe. UI layers typically pass a Qt signal emitter.
        """
        with self._lock:
            self._sink = sink

    def snapshot_lines(self) -> List[str]:
        with self._lock:
            return list(self._lines)

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def warn(self, message: str) -> None:
        self._write("WARN", message)

    def error(self, message: str) -> None:
        self._write("ERROR", message)

    # -----------------
    # Internals
    # -----------------

    @staticmethod
    def _timestamp_now() -> str:
        # Local time, concise.
        return datetime.now().strftime("%H:%M:%S")

    def _write(self, level: str, message: str) -> None:
        line = LogLine(timestamp=self._timestamp_now(), level=level, message=str(message)).format()

        # Store under lock, invoke sink outside lock.
        sink: Optional[Callable[[str], None]]
        with self._lock:
            self._lines.append(line)
            sink = self._sink

        if sink is not None:
            try:
                sink(line)
            except Exception:
                # Logging must never crash the app.
                return
