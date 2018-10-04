from json import loads

import pytest

from redis_websocket_api import WebsocketHandler
from redis_websocket_api.geo_protocol import GeoCommandsMixin, BoundingBox

GEOJSON = """\
{{
    "type": "Feature",
    "properties": {{}},
    "geometry": {{
        "type": "{type_}",
        "coordinates": [{coordinates}]
    }}
}}
"""


def get_geojson(type_, coordinates):
    return GEOJSON.format(type_=type_, coordinates=coordinates)


@pytest.fixture
def geo_handler(websocket, redis):
    class GeoHandler(WebsocketHandler, GeoCommandsMixin):
        allowed_commands = 'BBOX', 'PROJECTION', 'GET'

    return GeoHandler(redis=redis, websocket=websocket, channel_names=[])


def test_bbox_command(loop, geo_handler):
    loop.run_until_complete(geo_handler._handle_remote_message('BBOX egg'))
    assert geo_handler.bbox is None
    loop.run_until_complete(geo_handler._handle_remote_message('BBOX 1 2 3 4'))
    assert 'bbox' in geo_handler.filters
    assert geo_handler.bbox == BoundingBox(
        left=1.0, bottom=2.0, right=3.0, top=4.0)
    loop.run_until_complete(geo_handler._handle_remote_message('BBOX'))
    assert 'bbox' not in geo_handler.filters


def test_bbox_filter(loop, geo_handler):
    loop.run_until_complete(geo_handler._handle_remote_message('BBOX 1 2 3 4'))
    assert 'bbox' in geo_handler.filters

    input_msg = get_geojson('Point', '2.1, 3.5')
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))

    input_msg = get_geojson('Point', '0.1, 3.5')
    assert geo_handler._apply_filters(input_msg) == (False, loads(input_msg))

    input_msg = get_geojson('Polygon', '[[0.1, 3.5], [2.1, 3.4]]')
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))

    input_msg = get_geojson('Polygon', '[[0.1, 3.5], [5.1, 3.4]]')
    assert geo_handler._apply_filters(input_msg) == (False, loads(input_msg))

    input_msg = get_geojson('LineString', '[0.1, 3.5], [5.1, 3.4]')
    assert geo_handler._apply_filters(input_msg) == (False, loads(input_msg))

    input_msg = get_geojson('LineString', '[0.1, 3.5], [2.1, 3.4]')
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))

    input_msg = get_geojson('Unknown', '[0.1, 3.5], [2.1, 3.4]')
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))

    input_msg = '"PONG"'
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))


def test_projection_command(loop, geo_handler):
    loop.run_until_complete(geo_handler._handle_remote_message('PROJECTION egg'))
    assert 'projection' not in geo_handler.filters
    loop.run_until_complete(geo_handler._handle_remote_message('PROJECTION e g'))
    assert 'projection' not in geo_handler.filters

    loop.run_until_complete(
        geo_handler._handle_remote_message('PROJECTION epsg:3857'))
    assert 'projection' in geo_handler.filters

    loop.run_until_complete(
        geo_handler._handle_remote_message('PROJECTION epsg:4326'))
    assert 'projection' not in geo_handler.filters


def test_projection_filter(loop, geo_handler):
    assert geo_handler._projection_filter({}) is True
    loop.run_until_complete(
        geo_handler._handle_remote_message('PROJECTION epsg:3857'))
    assert geo_handler.projection_out is not None
    assert geo_handler._projection_filter({}) is True

    input_msg = get_geojson('LineString', '[0.1, 3.5], [2.1, 3.4]')
    assert geo_handler._apply_filters(input_msg) == (True, {
        'geometry': {
            'coordinates': [
                (11131.949079326665, 389860.7582541955),
                (233770.93066587413, 378708.59661392024)],
            'type': 'LineString'
        },
        'properties': {},
        'type': 'Feature'})

    input_msg = get_geojson('Point', '0.1, 3.5')
    assert geo_handler._apply_filters(input_msg) == (True, {
        'geometry': {
            'coordinates': (11131.949079326665, 389860.7582541955),
            'type': 'Point'
        },
        'properties': {},
        'type': 'Feature'})

    input_msg = get_geojson('Polygon', '[[0.1, 3.5], [2.1, 3.4]]')
    assert geo_handler._apply_filters(input_msg) == (True, {
        'geometry': {
            'coordinates': [[
                (11131.949079326665, 389860.7582541955),
                (233770.93066587413, 378708.59661392024)]],
            'type': 'Polygon'
        },
        'properties': {},
        'type': 'Feature'})

    input_msg = get_geojson('Unknown', '[0.1, 3.5], [2.1, 3.4]')
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))
