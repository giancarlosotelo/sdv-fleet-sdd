import asyncio
import contextlib
import logging
from typing import Any

import grpc
from kuksa_client.grpc import Datapoint, VSSClientError
from kuksa_client.grpc.aio import VSSClient

from fleet.vehicle.twin import OnChange, TwinUnavailable, UnknownSignal

log = logging.getLogger(__name__)


class KuksaTwin:
    """A van's twin in a real Kuksa Databroker (spec REQ-040)."""

    BASE_PORT = 55561  # van i in config order uses BASE_PORT + i (deploy/compose.yaml)

    def __init__(self, client: VSSClient):
        self._client = client
        self._tasks: list[asyncio.Task] = []

    @classmethod
    async def connect(cls, host: str = "127.0.0.1", port: int = BASE_PORT) -> "KuksaTwin":
        client = VSSClient(host, port)
        try:
            await client.connect()
        except (grpc.RpcError, VSSClientError) as ex:
            raise TwinUnavailable(f"databroker {host}:{port}: {ex}") from ex
        return cls(client)

    @staticmethod
    def _translate(ex: Exception) -> Exception:
        text = str(ex)
        if "not_found" in text.lower() or "NOT_FOUND" in text:
            return UnknownSignal(text)
        return TwinUnavailable(text)

    async def set(self, values: dict[str, Any]) -> None:
        try:
            await self._client.set_current_values({p: Datapoint(v) for p, v in values.items()})
        except (grpc.RpcError, VSSClientError) as ex:
            raise self._translate(ex) from ex

    async def get(self, paths: list[str]) -> dict[str, Any]:
        try:
            dps = await self._client.get_current_values(paths)
        except (grpc.RpcError, VSSClientError) as ex:
            raise self._translate(ex) from ex
        return {p: (dps[p].value if dps.get(p) is not None else None) for p in paths}

    async def subscribe(self, paths: list[str], on_change: OnChange) -> None:
        ready = asyncio.Event()

        async def pump() -> None:
            first = True
            async for updates in self._client.subscribe_current_values(paths):
                if first:  # the databroker opens with current values, not a change
                    first = False
                    ready.set()
                    continue
                await on_change({p: dp.value for p, dp in updates.items() if dp is not None})

        task = asyncio.create_task(pump())
        task.add_done_callback(self._log_failure)
        self._tasks.append(task)
        waiter = asyncio.create_task(ready.wait())
        done, _ = await asyncio.wait({task, waiter}, timeout=5, return_when=asyncio.FIRST_COMPLETED)
        waiter.cancel()
        if task in done:
            raise self._translate(task.exception() or RuntimeError("subscription ended"))

    @staticmethod
    def _log_failure(task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception():
            log.error("kuksa subscription stopped", exc_info=task.exception())

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        with contextlib.suppress(Exception):
            await self._client.disconnect()
