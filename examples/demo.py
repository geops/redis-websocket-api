"""Async Websocket API providing access to redis channels and cache."""

import logging
import asyncio

from aioredis import create_redis_pool
from websockets import exceptions

from redis_websocket_api import WebsocketHandler, WebsocketServer
from redis_websocket_api.geo_protocol import GeoCommandsMixin
from redis_websocket_api.exceptions import (
    RemoteMessageHandlerError, InternalMessageHandlerError)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

REDIS_ADDRESS = ('localhost', 6379)
EXAMPLE_GEOJSON = """\
{{
    "type": "Feature",
    "properties": {{"id": {id}}},
    "geometry": {{
        "type": "Point",
        "coordinates": [{lon}, {lat}]
    }}
}}
"""


class ExampleWebsocketHandler(WebsocketHandler, GeoCommandsMixin):
    """Implement and handle websocket based Redis proxy protocol."""

    allowed_commands = 'SUB', 'DEL', 'BBOX', 'PROJECTION', 'PING', 'GET'


class ExampleWebsocketServer(WebsocketServer):

    handler_class = ExampleWebsocketHandler

    async def websocket_handler(self, websocket, path):
        """Create and register WebsocketHandler with error handling"""
        try:
            await super().websocket_handler(websocket, path)
        except (exceptions.ConnectionClosed, asyncio.TimeoutError):
            logger.info("Client %s disconnected", websocket.remote_address)
        except RemoteMessageHandlerError as e:
            logger.info("Hanging up on %s after invalid remote command: %s",
                        websocket.remote_address, e, exc_info=True)
        except InternalMessageHandlerError:
            logger.exception("Hanging up on %s because of buggy message!",
                             websocket.remote_address)


async def example_producer():
    """Dummy producer putting data into redis for demonstrating the API"""

    redis = await create_redis_pool(REDIS_ADDRESS)

    # If there is a HSET with the same name as a channel it's content serves as
    # initial data when performing a `GET channel_name` from the websocket
    # client.
    await redis.hset(
        'example_channel_1', 'initial_data_1', '{"some_json": "no GeoJSON"}')
    await redis.hset(
        'example_channel_2', 'initial_data_1', EXAMPLE_GEOJSON.format(
            id=1, lon=7.8486934304237375, lat=47.9914151679489))

    counter = 1
    while True:
        counter += 1
        message = EXAMPLE_GEOJSON.format(
            id=counter, lon=counter % 180, lat=counter % 90)
        # Keeping the initial data up to date
        redis.hset('example_channel_2', 'data_{}'.format(counter), message)
        # Pushing to subscribers
        redis.publish('example_channel_2', message)
        await asyncio.sleep(.1)


def main():
    loop = asyncio.get_event_loop()
    loop.create_task(example_producer())

    ExampleWebsocketServer(
        redis=loop.run_until_complete(create_redis_pool(REDIS_ADDRESS)),
        subscriber=loop.run_until_complete(create_redis_pool(REDIS_ADDRESS)),
        read_timeout=30,
        keep_alive_timeout=120,
    ).listen(
        host='localhost',
        port=8000,
        channel_names=('example_channel_1', 'example_channel_2'),
        loop=loop
    )


if __name__ == '__main__':
    main()
