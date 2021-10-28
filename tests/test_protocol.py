import pytest

from redis_websocket_api.exceptions import RemoteMessageHandlerError


def test_errors(loop, handler):
    with pytest.raises(RemoteMessageHandlerError):
        loop.run_until_complete(handler._handle_remote_message(""))

    assert (
        loop.run_until_complete(handler._handle_remote_message("unknown cmd")) is None
    )


def test_subsription_commands(loop, handler):
    with pytest.raises(RemoteMessageHandlerError):
        loop.run_until_complete(handler._handle_remote_message("SUB"))

    handler.channel_names = ["egg"]
    assert "egg" not in handler.subscriptions
    loop.run_until_complete(handler._handle_remote_message("SUB egg"))
    assert "egg" in handler.subscriptions
    loop.run_until_complete(handler._handle_remote_message("DEL egg"))
    assert "egg" not in handler.subscriptions
    assert loop.run_until_complete(handler._handle_remote_message("DEL egg")) is None


def test_get_command(loop, handler, redis, websocket):
    with pytest.raises(RemoteMessageHandlerError):
        loop.run_until_complete(handler._handle_remote_message("GET"))

    loop.run_until_complete(handler._handle_remote_message("GET egg"))
    redis.await_hvals.assert_not_called()

    handler.channel_names = ["egg"]
    loop.run_until_complete(handler._handle_remote_message("GET egg"))
    redis.await_hvals.assert_called_once_with("egg")
    assert '"source": "egg"' in websocket.await_send.call_args_list[0][0][0]

    loop.run_until_complete(handler._handle_remote_message("GET egg ref"))
    redis.await_hget.assert_called_once_with("egg", "ref")

    redis.await_hget.reset_mock()
    websocket.await_send.reset_mock()
    loop.run_until_complete(handler._handle_remote_message("GET egg ref cref"))
    redis.await_hget.assert_called_once_with("egg", "ref")
    assert '"client_reference": "cref"' in websocket.await_send.call_args_list[0][0][0]

    redis.await_hget.reset_mock()
    websocket.await_send.reset_mock()
    loop.run_until_complete(
        handler._handle_remote_message("GET egg ref client_ref=cref")
    )
    assert '"client_reference": "cref"' in websocket.await_send.call_args_list[0][0][0]

    redis.await_hvals.reset_mock()
    redis.await_hvals.return_value = ['{"hello": "world"}']
    websocket.await_send.reset_mock()
    loop.run_until_complete(handler._handle_remote_message("GET egg"))
    redis.await_hvals.assert_called_once_with("egg")
    assert (
        '"content": {"hello": "world"}' in websocket.await_send.call_args_list[0][0][0]
    )


def test_ping_pong(loop, handler, websocket):
    loop.run_until_complete(handler._handle_remote_message("PING"))
    assert '"content": "PONG"' in websocket.await_send.call_args_list[0][0][0]
