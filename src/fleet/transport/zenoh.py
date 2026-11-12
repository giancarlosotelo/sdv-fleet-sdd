from collections.abc import Awaitable, Callable
from typing import Protocol

from fleet.transport import TransportUnavailable

KeyHandler = Callable[[str, bytes], Awaitable[None]]


class Zenoh(Protocol):
    async def put(self, key: str, payload: bytes) -> None: ...
    async def subscribe(self, key_expr: str, handler: KeyHandler) -> None: ...


def key_matches(key_expr: str, key: str) -> bool:
    """Zenoh key expressions: `*` is one chunk, `**` is any number of chunks."""
    expr, chunks = key_expr.split("/"), key.split("/")
    if not expr:
        return not chunks
    if expr[0] == "**":
        rest = "/".join(expr[1:])
        return (
            any(key_matches(rest, "/".join(chunks[i:])) for i in range(len(chunks) + 1))
            if rest
            else True
        )
    if not chunks or chunks == [""]:
        return False
    if expr[0] != "*" and expr[0] != chunks[0]:
        return False
    if len(expr) == 1:
        return len(chunks) == 1
    return len(chunks) > 1 and key_matches("/".join(expr[1:]), "/".join(chunks[1:]))


class StandInZenoh:
    """In-memory Zenoh session; set `up = False` to simulate an unreachable router."""

    def __init__(self) -> None:
        self.up = True
        self._subs: list[tuple[str, KeyHandler]] = []

    async def put(self, key: str, payload: bytes) -> None:
        if not self.up:
            raise TransportUnavailable("stand-in zenoh is down")
        for key_expr, handler in self._subs:
            if key_matches(key_expr, key):
                await handler(key, payload)

    async def subscribe(self, key_expr: str, handler: KeyHandler) -> None:
        self._subs.append((key_expr, handler))
