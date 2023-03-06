import asyncio
from logging import getLogger
import websockets

from websockets.legacy.server import WebSocketServerProtocol, serve

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
        :param keep_alive_timeout: Time after which the server cancels the
           handler task (independently of it's internal state)
        """

        if read_timeout:
            logger.warning(
                "read_timeout is not used anymore because cleanup is triggered "
                "immediately on connection loss"
            )

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

    async def websocket_handler(self, websocket: WebSocketServerProtocol, path) -> None:
        """Return handler for a single websocket connection."""

        logger.info("Client %s connected", websocket.remote_address)
        handler = await self.handler_class.create(self.redis, websocket)
        self.handlers[websocket.remote_address] = handler
        handler_listen_task = asyncio.create_task(
            asyncio.wait_for(handler.listen(), self.keep_alive_timeout)
        )
        wait_closed_task = asyncio.create_task(websocket.wait_closed())
        await asyncio.wait(
            {
                handler_listen_task,
                wait_closed_task,
            },
            return_when="FIRST_COMPLETED",
        )
        try:
            del self.handlers[websocket.remote_address]
            handler_listen_task.cancel()
            await handler.close()
            try:
                await handler_listen_task
            except (asyncio.CancelledError, asyncio.TimeoutError) as e:
                logger.debug(
                    "Closing connection for %s: %s", websocket.remote_address, e
                )
            wait_closed_task.cancel()
            try:
                await wait_closed_task
            except asyncio.CancelledError:
                logger.warning(
                    "Websocket connection for %s seems to be open after cleanup",
                    websocket.remote_address,
                )
        finally:
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
                    # Coution: without a timeout `get_message` yields
                    # immidiatly without waiting for a message.
                    ignore_subscribe_messages=True,
                    timeout=60,
                )
                if message is not None:
                    channel_name = message["channel"] or message["pattern"]

                    for handler in self.handlers.values():
                        if channel_name in handler.subscriptions:
                            handler.queue.put_nowait(
                                Message(source=channel_name, content=message["data"])
                            )

    async def serve(
        self,
        host,
        port,
        channel_names=(),
        channel_patterns=(),
        **websockets_serve_kwargs
    ):
        """Listen for websocket connections and manage redis subscriptions."""

        async with serve(
            ws_handler=self.websocket_handler,
            host=host,
            port=port,
            **websockets_serve_kwargs,
        ):
            logger.info("Listening on %s:%s...", host, port)
            await self.redis_reader(channel_names, channel_patterns)

    def listen(self, host, port, channel_names=(), channel_patterns=(), loop=None):
        logger.warning("`listen` is deprecated, use `serve` instead")
        serve_coro = self.serve(host, port, channel_names, channel_patterns)
        if loop:
            loop.run_until_complete(serve_coro)
        else:
            asyncio.run(serve_coro)
