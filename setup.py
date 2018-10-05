#!/usr/bin/env python

import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md')) as f:
    README = f.read()
with open(os.path.join(here, 'requirements.txt')) as f:
    requires = [line.strip() for line in f if len(line) > 1 and not line.startswith('#')]

setup(
    name='redis-websocket-api',
    version='0.0.1',
    description='Redis-over-WebSocket API on top of websockets and aioredis',
    long_description=README,
    url='https://github.com/geops/redis-websocket-api',
    author='Milan Oberkirch | geOps',
    author_email='milan.oberkirch@geops.de',
    keywords='tralis websocket websockets aioredis redis',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    extras_require={
        'testing': ['pytest'],
        'geo': ['pyproj']
    },
    python_requires='>=3.5',
    install_requires=requires,
    entry_points='''
        [console_scripts]
        redis_websocket_api_example=redis_websocket_api.example:main
    ''',
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
