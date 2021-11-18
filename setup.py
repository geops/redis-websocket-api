#!/usr/bin/env python

import os

from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, "README.md")) as f:
    README = f.read()

setup(
    name="redis-websocket-api",
    version="0.4.2",
    description="Redis-over-WebSocket API on top of websockets and aioredis",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/geops/redis-websocket-api",
    author="Milan Oberkirch | geOps",
    author_email="milan.oberkirch@geops.de",
    license="MIT",
    keywords="tralis websocket websockets aioredis redis",
    packages=["redis_websocket_api"],
    install_requires=["aioredis", "websockets", "hiredis"],
    extras_require={"testing": ["pytest"], "geo": ["pyproj<2"]},
    python_requires=">=3.7",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX",
        "Environment :: Web Environment",
        "Framework :: AsyncIO",
        "Intended Audience :: Developers",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
        "Topic :: Scientific/Engineering :: GIS",
    ],
)
