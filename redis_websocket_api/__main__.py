#!/usr/bin/env python3

"""Simple redis websocket api allowing access to all channels and hsets

Intended for debugging and development only.
"""

from os import getenv
from logging import basicConfig, INFO
import aioredis

from redis_websocket_api import WebsocketHandler, WebsocketServer


class PublishEverythingHandler(WebsocketHandler):
    def channel_is_allowed(self, channel_name):
        return True


def main():
    basicConfig(level=INFO)
    redis = aioredis.from_url(
        getenv("REDIS_DSN", "redis:///"), encoding="utf-8", decode_responses=True
    )
    server = WebsocketServer(redis=redis, handler_class=PublishEverythingHandler,)
    host = getenv("HOST", "localhost")
    port = int(getenv("PORT", 8765))
    server.listen(host, port, channel_patterns=["[a-z]*"])


if __name__ == "__main__":
    main()
