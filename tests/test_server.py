import asyncio
from unittest.mock import MagicMock

import pytest
from websockets import exceptions


def test_websocket_handler_creation(loop, server, websocket):
    server.handlers = MagicMock()
    websocket.await_recv.side_effect = exceptions.ConnectionClosed(1001, "foo")

    with pytest.warns(RuntimeWarning):
        asyncio.run(server.websocket_handler(websocket, "/foo"))

    assert websocket.await_recv.call_count == 1
    assert websocket.await_send.call_count == 1
    sent_str = websocket.await_send.call_args_list[0][0][0]
    assert '"status": "open"' in sent_str

    assert server.handlers.__setitem__.call_count == 1
    assert server.handlers.__delitem__.called_once_with(("EGG", 2000))
