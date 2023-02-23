from __future__ import annotations

import asyncio
from collections import OrderedDict
from logging import getLogger
from json import loads, dumps, JSONDecodeError
from datetime import datetime

from websockets.exceptions import ConnectionClosed

from .protocol import CommandsMixin, Message
from .exceptions import RemoteMessageHandlerError, InternalMessageHandlerError

logger = getLogger(__name__)


class WebsocketHandlerBase:
    """Define protocol for communication between web client and server."""

    allowed_commands = NotImplemented

    consumer_task: asyncio.Task  # for backwrds-compatibility, also in:
    tasks: dict[str, asyncio.Task]  # Self-made TaskGroup for old Python

    def __init__(self, redis, websocket, read_timeout=None):
        if read_timeout:
            logger.warning(
                "read_timeout is not used anymore because cleanup is trigered "
                "immidiatly on connection loss"
            )

        self.websocket = websocket
        self.redis = redis

        self.queue = asyncio.Queue()

        self.filters = OrderedDict()
        self.subscriptions = set()
        self.tasks = {}

    async def _websocket_reader(self):
        try:
            while True:
                await self.queue.put(
                    Message(source="websocket", content=await self.websocket.recv())
                )
        except ConnectionClosed:
            logger.debug(
                "Connection was closed by client %s", self.websocket.remote_address
            )

    def _apply_filters(self, message, exclude=()):
        """Return (passed, result)-tuple.

        Runs all filters in self.filters on the deserialized message and
        returns a boolean indicating whether all filters passed and a JSON
        string with the (modified) result.
        """
        if message is None:
            return False, None

        try:
            data = loads(message)
        except JSONDecodeError as e:
            raise InternalMessageHandlerError(
                "Decoding '{}' failed.".format(message)
            ) from e

        passes = all(
            (func(data) for name, func in self.filters.items() if name not in exclude)
        )
        return passes, data

    async def _queue_reader(self):
        source, message = await self.queue.get()
        if source == "websocket":
            await self._handle_remote_message(message)
        else:
            passes, data = self._apply_filters(message)
            if passes:
                await self._send(source, data)

    async def _send(self, source, data, client_reference=None):
        await self.websocket.send(
            dumps(
                dict(
                    source=source,
                    content=data,
                    timestamp=datetime.now().timestamp() * 1000,  # how JS expects it
                    client_reference=client_reference,
                )
            )
        )

    def _parse_remote_message(self, message):
        command, *arguments = message.split()
        args = []
        kwargs = {}
        for arg in arguments:
            if "=" in arg:
                name, value = arg.split("=", 1)
                kwargs[name] = value
            else:
                args.append(arg)
        return command, args, kwargs

    async def _handle_remote_message(self, message):
        try:
            command, args, kwargs = self._parse_remote_message(message)
            if command not in self.allowed_commands:
                # Don't even echo it back, most likely it's spam!
                logger.info(
                    "Got unknown command '%s' from %s!",
                    command,
                    self.websocket.remote_address,
                )
                return
            logger.debug(
                "Processing command '%s' with args %s from %s.",
                command,
                args,
                self.websocket.remote_address,
            )
            await getattr(self, "_handle_{}_command".format(command.lower()))(
                *args, **kwargs
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            raise RemoteMessageHandlerError(
                "Handling message '{}' failed: {}".format(message, e)
            ) from e

    def channel_is_allowed(self, channel_name):
        """Return wheather the given channel is accessable from the API

        Overwrite this method to limit access to specific channnels only.
        """
        return True

    @classmethod
    async def create(cls, redis, websocket, read_timeout=None):
        """Create a handler instance setting up tasks and queues."""

        if read_timeout:
            logger.warning(
                "read_timeout is not used anymore because cleanup is trigered "
                "immidiatly on connection loss"
            )

        self = cls(redis, websocket)
        self.consumer_task = asyncio.create_task(self._websocket_reader())
        self.tasks["consumer_task"] = self.consumer_task
        return self

    async def listen(self):
        """Read and handle messages from internal message queue"""
        await self._send("websocket", {"status": "open"})
        while self.websocket.open:
            queue_reader_task = asyncio.create_task(self._queue_reader())
            self.tasks["queue_reader"] = queue_reader_task
            await queue_reader_task

    async def close(self):
        """Close all connections and cancel all tasks."""
        if self.websocket.open:
            await self.websocket.close()
        for task in self.tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


class WebsocketHandler(WebsocketHandlerBase, CommandsMixin):
    """Provides a Redis proxy to predefined channels"""

    allowed_commands = "SUB", "DEL", "PING", "GET"
    channel_names = set()

    def channel_is_allowed(self, channel_name):
        """Return whether the given channel should be accessible

        Overwrite this method to fit your usecase, default is that you'll
        need to set the allowed channels in a subclass.
        """
        return channel_name in self.channel_names
