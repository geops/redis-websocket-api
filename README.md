An extensible Redis-over-WebSocket API on top of websockets and aioredis.


Installation
------------

For basic functionality:

    pip install redis_websocket_api

With geo extension (filtering messages by extent, projection transformation):

    pip install redis_websocket_api[geo]


Server-Side Usage
-----------------

Start the `WebsocketServer` like this:

    from aioredis import create_redis_pool
    from redis_websocket_api import WebsocketServer

    REDIS_ADDRESS = ('localhost', 6379)


    WebsocketServer(
        redis=loop.run_until_complete(create_redis_pool(REDIS_ADDRESS)),
        subscriber=loop.run_until_complete(create_redis_pool(REDIS_ADDRESS)),
        read_timeout=30,
        keep_alive_timeout=120,
    ).listen(
        host='localhost',
        port=8000,
        channel_names=('public_channel_1', 'public_channel_2'),
    )

Have a look at `examples/demo.py` for an example with the `GeoCommandsMixin`
added.


Client-Side Usage
-----------------

#### `WebsocketHandler`

The default functionality provides the following interface to the web client
(expecting the requests over a websocket connection):
- `GET key` translates to `hvals key`
- `GET key hkey` translates to `hget key hkey`
- `SUB key` subscribes the websocket to a redis channel (using a single redis
  connection pool for all clients)
- `DEL key` unsubscribes the client from the channel
- `PING` causes a `PONG` response (to avoid timeouts)

#### Subclass of `WebsocketHandler` with `GeoCommandsMixin` added

By adding the `GeoCommandsMixin` the web client can use
- `BBOX left bottom right top` to only receive GeoJSON features within this box
  plus all messages which are not valid GeoJSON
- `PROJECTION epsg:number` causes all future GeoJSON features to be transformed
  to the given projection

See `examples/demo.py` for how to use an extended `WebsocketHandler` subclass.

Geo commands are currently limited to `LineString`, `Polygon`, and `Point`
geometries.

#### Build your own protocol

Using the commands listed above for communicating from client to server is
completly optional and determinded by the Mixin classes added to the
`WebsocketHandlerBase`.
