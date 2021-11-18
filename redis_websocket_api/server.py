import asyncio
from logging import getLogger

from websockets import serve

from redis_websocket_api.handler import WebsocketHandler, WebsocketHandlerBase
from redis_websocket_api.protocol import Message

logger = getLogger(__name__)


class WebsocketServer:

    """Provide websocket proxy to public redis channels and hashes.

    In addition to passing through data this server supports some geo
    operations, see the WebsocketHandler and protocol.CommandsMixin for
    details.
    """

    handler_class = WebsocketHandler

    def __init__(
        self, redis, read_timeout=None, keep_alive_timeout=None, handler_class=None
    ):
        """Set default values for new WebsocketHandlers.

        :param redis: aioredis.client.Redis instance
        :param read_timeout: Timeout, after which the websocket connection is
           checked and kept if still open (does not cancel an open connection)
        :param keep_alive_timeout: Time after which the server cancels the
           handler task (independently of it's internal state)
        """

        self.read_timeout = read_timeout
        self.keep_alive_timeout = keep_alive_timeout
        self.handlers = {}
        self.redis = redis
        if handler_class is not None:
            if issubclass(handler_class, WebsocketHandlerBase):
                self.handler_class = handler_class
            else:
                raise TypeError(
                    "handler_class has to be a subclass of WebsocketHandlerBase"
                )

    async def websocket_handler(self, websocket, path):
        """Return handler for a single websocket connection."""

        logger.info("Client %s connected", websocket.remote_address)
        handler = await self.handler_class.create(
            self.redis, websocket, read_timeout=self.read_timeout,
        )
        self.handlers[websocket.remote_address] = handler
        try:
            await asyncio.wait_for(handler.listen(), self.keep_alive_timeout)
        finally:
            del self.handlers[websocket.remote_address]
            await handler.close()
            logger.info("Client %s removed", websocket.remote_address)

    async def redis_subscribe(self, p, channel_names=(), channel_patterns=()):
        """Subscribe to channels by channel_names and/or channel_patterns."""

        if not (channel_names or channel_patterns):
            raise ValueError("Got nothing to subscribe to")

        for name in channel_names:
            await p.subscribe(name)

        for pattern in channel_patterns:
            await p.psubscribe(pattern)

    async def redis_reader(self, channel_names=(), channel_patterns=()):
        """Pass messages from subscribed channels to handlers."""

        psub = self.redis.pubsub()

        async with psub as p:
            await self.redis_subscribe(p, channel_names, channel_patterns)
            while True:
                message = await p.get_message(
                    ignore_subscribe_messages=True, timeout=60,
                )
                if message is not None:
                    channel_name = message["channel"] or message["pattern"]

                    for handler in self.handlers.values():
                        if channel_name in handler.subscriptions:
                            handler.queue.put_nowait(
                                Message(source=channel_name, content=message["data"])
                            )

        psub.close()

    def listen(self, host, port, channel_names=(), channel_patterns=(), loop=None):
        """Listen for websocket connections and manage redis subscriptions."""

        loop = loop or asyncio.get_event_loop()
        start_server = serve(self.websocket_handler, host, port)
        loop.run_until_complete(start_server)
        logger.info("Listening on %s:%s...", host, port)
        loop.run_until_complete(self.redis_reader(channel_names, channel_patterns))


if __name__ == "__main__":
    import aioredis

    class PublishEverythingHandler(WebsocketHandler):
        def channel_is_allowed(self, channel_name):
            return True

    redis = aioredis.from_url("redis:///", encoding="utf-8", decode_responses=True)
    WebsocketServer(redis).listen("localhost", "8765", channel_patterns=["[a-z]*"])
