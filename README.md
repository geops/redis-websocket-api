An extensible Redis-over-WebSocket API on top of websockets and aioredis.


Installation
------------

For basic functionality:

    pip install redis_websocket_api

With geo extension (filtering messages by extent, projection transformation):

    pip install redis_websocket_api[geo]


Server-Side Usage
-----------------

For a quick test you can run

```bash
python -m redis_websocket_api
```

to start a simple redis websocket api on `ws://localhost:8765`.

This does [roughly](./redis_websocket_api/__main__.py) the equivalant of:

```python
from aioredis import from_url
from redis_websocket_api import WebsocketServer, WebsocketHandler


class PublishEverythingHandler(WebsocketHandler):

    def channel_is_allowed(self, channel_name):
        return True


WebsocketServer(
    redis=from_url("redis:///", encoding="utf-8", decode_responses=True),
    read_timeout=30,
    keep_alive_timeout=120,
    handler_class=PublishEverythingHandler,
).listen(
    host='localhost',
    port=8000,
    channel_patterns=["[a-z]*"],
)
```

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

Note that the projection input and output coordinates will use the traditional GIS order,
that is longitude, latitude for geographic CRS and easting, northing for most projected CRS.
If you want the input and output axis order to strictly follow the definition of the CRS,
use `StrictAxisOrderGeoCommandsMixin` instead of `GeoCommandsMixin`.

#### Build your own protocol

Using the commands listed above for communicating from client to server is
completly optional and determinded by the Mixin classes added to the
`WebsocketHandlerBase`.
