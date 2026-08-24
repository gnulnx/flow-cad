"""Provider boundary for persistent workbench chat.

Providers emit semantic progress events. They never write thread storage or
receive unrestricted access to the project runtime.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Iterator, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    kind: str
    content: str = ""
    details: Mapping[str, object] | None = None


class ProviderCancellation:
    """Cooperative cancellation shared by provider and job adapters."""

    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)


class ChatProvider(Protocol):
    """A provider streams compact user-visible events for one durable turn."""

    name: str

    def stream_turn(
        self,
        *,
        thread_id: str,
        turn_id: str,
        prompt: str,
        context: Mapping[str, object],
        cancellation: ProviderCancellation,
    ) -> Iterator[ProviderEvent]:
        ...
