from unittest.mock import MagicMock

import pytest

from redis_websocket_api import WebsocketHandler, WebsocketServer


@pytest.fixture
def loop():
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        loop.close()


def get_async_mock(mock, name, raise_=None):
    async def mocked(*args, **kwargs):
        result = getattr(mock, "await_{}".format(name))(*args, **kwargs)
        if not isinstance(result, MagicMock):
            return result

    return mocked


class AsyncMagicMock(MagicMock):
    def __getattr__(self, name):
        if name.startswith("await_") or name.startswith("_"):
            return super().__getattr__(name)
        return get_async_mock(self, name)


@pytest.fixture
def websocket():
    websocket = AsyncMagicMock()
    websocket.remote_address = ("EGG", 2000)
    return websocket


@pytest.fixture
def redis():
    return AsyncMagicMock()


@pytest.fixture
def handler(websocket, redis):
    return WebsocketHandler(redis=redis, websocket=websocket)


@pytest.fixture
def server(redis):
    return WebsocketServer(redis, read_timeout=1, keep_alive_timeout=1)
