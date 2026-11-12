import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Protocol

OnChange = Callable[[dict[str, Any]], Awaitable[None]]


class UnknownSignal(KeyError):
    pass


class TwinUnavailable(ConnectionError):
    """The databroker can't be reached; adapters raise this instead of client-specific errors."""


class Twin(Protocol):
    """A van's digital twin: the Kuksa Databroker or its in-memory stand-in."""

    async def set(self, values: dict[str, Any]) -> None: ...
    async def get(self, paths: list[str]) -> dict[str, Any]: ...
    async def subscribe(self, paths: list[str], on_change: OnChange) -> None: ...


class InMemoryTwin:
    """Stand-in for the Kuksa Databroker: rejects unknown paths and notifies subscribers."""

    def __init__(self, known: Iterable[str]):
        self._known = set(known)
        self._values: dict[str, Any] = {}
        self._subscribers: list[tuple[set[str], OnChange]] = []

    def _check(self, paths: Iterable[str]) -> None:
        unknown = sorted(set(paths) - self._known)
        if unknown:
            raise UnknownSignal(f"unknown VSS path(s): {', '.join(unknown)}")

    async def set(self, values: dict[str, Any]) -> None:
        self._check(values)
        self._values.update(values)
        for path, value in values.items():  # one update per signal, like the Kuksa Databroker
            for paths, on_change in self._subscribers:
                if path in paths:
                    await on_change({path: value})

    async def get(self, paths: list[str]) -> dict[str, Any]:
        self._check(paths)
        return {p: self._values.get(p) for p in paths}

    async def subscribe(self, paths: list[str], on_change: OnChange) -> None:
        self._check(paths)
        self._subscribers.append((set(paths), on_change))
        await asyncio.sleep(0)
