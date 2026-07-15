"""Queue helpers used by the Atlas pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Iterator


@dataclass(frozen=True)
class QueueItem:
    """A queued resume path."""

    path: Path


class ResumePathQueue:
    """Small wrapper around a thread-safe queue of PDF paths."""

    _sentinel = object()

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: Queue[object] = Queue(maxsize=maxsize)

    def put(self, path: Path) -> None:
        self._queue.put(QueueItem(path))

    def close(self) -> None:
        self._queue.put(self._sentinel)

    def __iter__(self) -> Iterator[Path]:
        while True:
            item = self._queue.get()
            if item is self._sentinel:
                break
            if isinstance(item, QueueItem):
                yield item.path

    def get(self, timeout: float | None = None) -> Path:
        """Block until a queued path is available or the queue is closed."""

        item = self._queue.get(timeout=timeout)
        if item is self._sentinel:
            raise Empty
        if not isinstance(item, QueueItem):
            raise Empty
        return item.path

    def get_nowait(self) -> Path:
        """Expose a non-blocking retrieval helper for watch-mode tests."""

        return self.get(timeout=0)
