import asyncio
from logging import getLogger

from websockets import serve
from aioredis.pubsub import Receiver

from .handler import WebsocketHandler
from .protocol import Message

logger = getLogger(__name__)


class WebsocketServer:

    """Provide websocket proxy to public redis channels and hashes.

    In addition to passing through data this server supports some geo
    operations, see the WebsocketHandler and protocol.CommandsMixin for
    details.
    """

    handler_class = WebsocketHandler

    def __init__(self, redis, subscriber, read_timeout=None, keep_alive_timeout=None):
        """Set default values for new WebsocketHandlers.

        :param redis: aioredis.StrictRedis instance
        :param subscriber: aioredis.StrictRedis instance
        :param read_timeout: Timeout, after which the websocket connection is
           checked and kept if still open (does not cancel an open connection)
        :param keep_alive_timeout: Time after which the server cancels the
           handler task (independently of it's internal state)
        """

        self.read_timeout = read_timeout
        self.keep_alive_timeout = keep_alive_timeout
        self.receiver = Receiver()
        self.handlers = {}
        self.redis = redis
        self.subscriber = subscriber

    async def websocket_handler(self, websocket, path):
        """Return handler for a single websocket connection."""

        logger.info("Client %s connected", websocket.remote_address)
        handler = await self.handler_class.create(
            self.redis,
            websocket,
            set(map(bytes.decode, self.receiver.channels.keys())),
            set(map(bytes.decode, self.receiver.patterns.keys())),
            read_timeout=self.read_timeout,
        )
        self.handlers[websocket.remote_address] = handler
        try:
            await asyncio.wait_for(handler.listen(), self.keep_alive_timeout)
        finally:
            del self.handlers[websocket.remote_address]
            await handler.close()
            logger.info("Client %s removed", websocket.remote_address)

    async def redis_subscribe(self, channel_names=None, channel_patterns=None):
        """Subscribe to channels by channel_names and/or channel_patterns."""

        if not (channel_names or channel_patterns):
            raise ValueError("Got nothing to subscribe to")

        if channel_names:
            await self.subscriber.subscribe(
                *(self.receiver.channel(name) for name in channel_names)
            )

        if channel_patterns:
            await self.subscriber.psubscribe(
                *(self.receiver.pattern(pattern) for pattern in channel_patterns)
            )

    async def redis_reader(self):
        """Pass messages from subscribed channels to handlers."""

        async for channel, msg in self.receiver.iter(encoding="utf-8"):
            if channel.is_pattern:
                channel_name, msg = msg[0].decode(), msg[1]
            else:
                channel_name = channel.name.decode()

            for handler in self.handlers.values():
                if channel_name in handler.subscriptions:
                    handler.queue.put_nowait(Message(source=channel_name, content=msg))

    def listen(self, host, port, channel_names=None, channel_patterns=None, loop=None):
        """Listen for websocket connections and manage redis subscriptions."""

        loop = loop or asyncio.get_event_loop()
        start_server = serve(self.websocket_handler, host, port)
        loop.run_until_complete(self.redis_subscribe(channel_names, channel_patterns))
        loop.run_until_complete(start_server)
        logger.info("Listening on %s:%s...", host, port)
        loop.run_until_complete(self.redis_reader())
