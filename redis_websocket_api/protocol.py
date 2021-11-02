from collections import namedtuple
from logging import getLogger

logger = getLogger(__name__)

Message = namedtuple("Message", ["source", "content"])


class CommandsMixin:
    """Provide command handlers for instructions sent by the client.

    Command handlers accept any number of positional and no keyword arguments.

    They can be activated in the WebsocketHandler by adding their name to the
    allowed_commands attribute.

    The commend name is translated to a method name like this:

        "_handle_{name}_command".format(name=a_tralis_protocol_command.lower())
    """

    async def _handle_del_command(self, channel_name):
        """Delete a redis channel subscription."""
        self.subscriptions.discard(channel_name)

    async def _handle_sub_command(self, channel_name):
        """Subscribe to redis channel"""
        if self.channel_is_allowed(channel_name):
            self.subscriptions.add(channel_name)

    async def _handle_ping_command(self, *args):
        """Prevent client-side timeout using a keep-alive message."""
        await self._send("websocket", "PONG")

    async def _handle_get_command(self, channel_name, ref=None, client_ref=None):
        """Get cached elements by key, optionally filter by reference.

        This command is guaranteed to send at least one message with the key
        and reference as source. The content is ``null`` if no valid content
        can be returned.

        If a client_ref is given, it is added to the envelope of the message
        sent.
        """
        if not self.channel_is_allowed(channel_name):
            return

        if ref is not None:
            source = "{} {}".format(channel_name, ref)
            _, data = self._apply_filters(await self.redis.hget(channel_name, ref))
            send_count = 1
            await self._send(source, data, client_reference=client_ref)
        else:
            source = channel_name
            values = await self.redis.hvals(channel_name)

            send_count = 0
            if values is not None:
                for value in values:
                    passed, data = self._apply_filters(value)
                    if passed:
                        send_count += 1
                        await self._send(
                            channel_name, data, client_reference=client_ref
                        )

            if send_count == 0:
                logger.info(
                    "No data for 'GET %s', sending empty message.", channel_name
                )
                send_count = 1
                await self._send(channel_name, None, client_reference=client_ref)

        logger.debug(
            "Sent %s messages in response to 'GET %s %s'.",
            send_count,
            channel_name,
            ref,
        )
