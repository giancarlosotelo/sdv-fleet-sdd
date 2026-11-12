from collections.abc import Awaitable, Callable
from typing import Protocol

from fleet.transport import TransportUnavailable

MessageHandler = Callable[[bytes], Awaitable[None]]


class PubSub(Protocol):
    async def publish(self, topic: str, data: bytes) -> None: ...
    async def subscribe(self, topic: str, handler: MessageHandler) -> None: ...


class StandInPubSub:
    """In-memory Pub/Sub; set `up = False` to simulate an unreachable service."""

    def __init__(self) -> None:
        self.up = True
        self._subs: dict[str, list[MessageHandler]] = {}

    async def publish(self, topic: str, data: bytes) -> None:
        if not self.up:
            raise TransportUnavailable("stand-in pubsub is down")
        for handler in self._subs.get(topic, []):
            await handler(data)

    async def subscribe(self, topic: str, handler: MessageHandler) -> None:
        self._subs.setdefault(topic, []).append(handler)
