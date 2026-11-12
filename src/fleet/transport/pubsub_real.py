import asyncio
import os
import uuid

from google.api_core import exceptions
from google.cloud import pubsub_v1

from fleet.transport import TransportUnavailable
from fleet.transport.pubsub import MessageHandler

PROJECT = "fleet-local"
DEFAULT_EMULATOR = "127.0.0.1:8085"


class RealPubSub:
    """Google Pub/Sub client; in V1 it talks to the emulator from deploy/compose.yaml."""

    def __init__(self, project: str = PROJECT):
        os.environ.setdefault("PUBSUB_EMULATOR_HOST", DEFAULT_EMULATOR)
        self._project = project
        self._publisher = pubsub_v1.PublisherClient(
            batch_settings=pubsub_v1.types.BatchSettings(max_messages=1)
        )
        self._subscriber = pubsub_v1.SubscriberClient()
        self._topics: set[str] = set()
        self._pulls: list = []
        self._tasks: list[asyncio.Task] = []

    def _topic(self, topic: str) -> str:
        path = self._publisher.topic_path(self._project, topic)
        if path not in self._topics:
            try:
                self._publisher.create_topic(name=path, timeout=5)
            except exceptions.AlreadyExists:
                pass
            except exceptions.GoogleAPICallError as ex:
                raise TransportUnavailable(f"pubsub: {ex}") from ex
            self._topics.add(path)
        return path

    async def publish(self, topic: str, data: bytes) -> None:
        try:
            await asyncio.wrap_future(self._publisher.publish(self._topic(topic), data))
        except exceptions.GoogleAPICallError as ex:
            raise TransportUnavailable(f"pubsub publish: {ex}") from ex

    async def subscribe(self, topic: str, handler: MessageHandler) -> None:
        topic_path = self._topic(topic)
        sub_path = self._subscriber.subscription_path(
            self._project, f"{topic}-{uuid.uuid4().hex[:8]}"
        )
        self._subscriber.create_subscription(name=sub_path, topic=topic_path, timeout=5)
        loop, queue = asyncio.get_running_loop(), asyncio.Queue()

        def on_message(message) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, message.data)
            message.ack()

        async def drain() -> None:
            while True:
                await handler(await queue.get())

        self._tasks.append(asyncio.create_task(drain()))
        self._pulls.append(self._subscriber.subscribe(sub_path, callback=on_message))

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        for pull in self._pulls:
            pull.cancel()
