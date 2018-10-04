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
    version='0.0',
    description='Websocket API using Redis as message broker backend',
    long_description=README,
    author='Milan Oberkirch | geOps',
    author_email='milan.oberkirch@geops.de',
    keywords='tralis websocket aioredis api',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    extras_require={
        'testing': ['pytest'],
        'geo': ['pyproj']
    },
    install_requires=requires,
    entry_points='''
        [console_scripts]
        redis_websocket_api_example=redis_websocket_api.example:main
    ''',
)
