import json
import asyncio
import logging
from typing import Optional, Callable

import redis.asyncio as aioredis
from app.config import REDIS_URL, REDIS_CHANNELS

logger = logging.getLogger(__name__)


class RedisPubSub:
    def __init__(self):
        self._pub: Optional[aioredis.Redis] = None
        self._sub: Optional[aioredis.Redis] = None
        self._pubsub: Optional[aioredis.client.PubSub] = None
        self._handlers: dict[str, list[Callable]] = {}
        self._listener_task: Optional[asyncio.Task] = None

    async def connect(self):
        self._pub = aioredis.from_url(REDIS_URL, decode_responses=True)
        self._sub = aioredis.from_url(REDIS_URL, decode_responses=True)
        self._pubsub = self._sub.pubsub()
        for channel_name in REDIS_CHANNELS.values():
            await self._pubsub.subscribe(channel_name)
        self._listener_task = asyncio.create_task(self._listen())

    async def disconnect(self):
        if self._listener_task:
            self._listener_task.cancel()
        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()
        if self._pub:
            await self._pub.close()
        if self._sub:
            await self._sub.close()

    async def publish(self, channel_key: str, data: dict):
        if not self._pub:
            return
        channel_name = REDIS_CHANNELS.get(channel_key, channel_key)
        await self._pub.publish(channel_name, json.dumps(data, default=str))

    def register_handler(self, channel_key: str, handler: Callable):
        channel_name = REDIS_CHANNELS.get(channel_key, channel_key)
        if channel_name not in self._handlers:
            self._handlers[channel_name] = []
        self._handlers[channel_name].append(handler)

    async def _listen(self):
        if not self._pubsub:
            return
        while True:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message["type"] == "message":
                    channel = message["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode()
                    handlers = self._handlers.get(channel, [])
                    try:
                        data = json.loads(message["data"])
                    except (json.JSONDecodeError, TypeError):
                        data = {}
                    for handler in handlers:
                        try:
                            result = handler(data)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.error(f"Redis handler error on {channel}: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Redis listener error: {e}")
                await asyncio.sleep(1)


redis_pubsub = RedisPubSub()
