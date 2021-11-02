from functools import partial
from json import loads

import pytest
from pytest import approx as approx_

from redis_websocket_api import WebsocketHandler
from redis_websocket_api.geo_protocol import GeoCommandsMixin, BoundingBox
from redis_websocket_api.exceptions import RemoteMessageHandlerError

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


FEATURE_COLLECTION = """\
{{
    "type": "FeatureCollection",
    "properties": {{}},
    "features": [
        {features}
    ]
}}
"""

# relative doesnt make sense with cyclic coordinates which might get close to 0
# on one axis. Then the relative tolerance rises to infinity
approx = partial(approx_, abs=1e-9)


def get_geojson(type_, coordinates):
    return GEOJSON.format(type_=type_, coordinates=coordinates)


def get_feature_collection(*features):
    features = ",\n".join(features)
    return FEATURE_COLLECTION.format(features=features)


@pytest.fixture
def geo_handler(websocket, redis):
    class GeoHandler(WebsocketHandler, GeoCommandsMixin):
        allowed_commands = "BBOX", "PROJECTION", "GET", "PGET"

    handler = GeoHandler(redis=redis, websocket=websocket)
    handler.channel_names = ["egg"]
    return handler


def test_bbox_command(loop, geo_handler):
    loop.run_until_complete(geo_handler._handle_remote_message("BBOX egg"))
    assert geo_handler.bbox is None
    loop.run_until_complete(geo_handler._handle_remote_message("BBOX 1 2 3 4"))
    assert "bbox" in geo_handler.filters
    assert geo_handler.bbox == BoundingBox(left=1.0, bottom=2.0, right=3.0, top=4.0)
    loop.run_until_complete(geo_handler._handle_remote_message("BBOX"))
    assert "bbox" not in geo_handler.filters


def test_bbox_filter(loop, geo_handler):
    loop.run_until_complete(geo_handler._handle_remote_message("BBOX 1 2 3 4"))
    assert "bbox" in geo_handler.filters

    input_msg = get_geojson("Point", "2.1, 3.5")
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))

    input_msg = get_geojson("Point", "0.1, 3.5")
    assert geo_handler._apply_filters(input_msg) == (False, loads(input_msg))

    input_msg = get_geojson("Polygon", "[[0.1, 3.5], [2.1, 3.4]]")
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))

    input_msg = get_geojson("Polygon", "[[0.1, 3.5], [5.1, 3.4]]")
    assert geo_handler._apply_filters(input_msg) == (False, loads(input_msg))

    input_msg = get_geojson("LineString", "[0.1, 3.5], [5.1, 3.4]")
    assert geo_handler._apply_filters(input_msg) == (False, loads(input_msg))

    input_msg = get_geojson("LineString", "[0.1, 3.5], [2.1, 3.4]")
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))

    input_msg = get_geojson("MultiLineString", "[[0.1, 3.5], [5.1, 3.4]]")
    assert geo_handler._apply_filters(input_msg) == (False, loads(input_msg))

    input_msg = get_geojson("MultiLineString", "[[0.1, 3.5], [2.1, 3.4]]")
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))

    input_msg = get_geojson("Unknown", "[0.1, 3.5], [2.1, 3.4]")
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))

    input_msg = '"PONG"'
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))


def test_projection_command(loop, geo_handler):
    loop.run_until_complete(geo_handler._handle_remote_message("PROJECTION egg"))
    assert "projection" not in geo_handler.filters
    loop.run_until_complete(geo_handler._handle_remote_message("PROJECTION e g"))
    assert "projection" not in geo_handler.filters

    loop.run_until_complete(geo_handler._handle_remote_message("PROJECTION epsg:3857"))
    assert "projection" in geo_handler.filters

    loop.run_until_complete(geo_handler._handle_remote_message("PROJECTION epsg:4326"))
    assert "projection" not in geo_handler.filters


def test_projection_filter(loop, geo_handler):
    assert geo_handler._projection_filter({}) is True
    loop.run_until_complete(geo_handler._handle_remote_message("PROJECTION epsg:3857"))
    assert geo_handler.projection_out is not None
    assert geo_handler._projection_filter({}) is True

    input_msg = get_geojson("LineString", "[0.1, 3.5], [2.1, 3.4]")
    assert geo_handler._apply_filters(input_msg) == (
        True,
        {
            "geometry": {
                "coordinates": [
                    approx((11131.949079326665, 389860.7582541955)),
                    approx((233770.93066587413, 378708.59661392024)),
                ],
                "type": "LineString",
            },
            "properties": {},
            "type": "Feature",
        },
    )

    input_msg = get_geojson(
        "MultiLineString", "[[0.1, 3.5], [2.1, 3.4]], [[2.1, 3.4], [0.1, 3.5]]"
    )
    assert geo_handler._apply_filters(input_msg) == (
        True,
        {
            "geometry": {
                "coordinates": [
                    [
                        approx((11131.949079326665, 389860.7582541955)),
                        approx((233770.93066587413, 378708.59661392024)),
                    ],
                    [
                        approx((233770.93066587413, 378708.59661392024)),
                        approx((11131.949079326665, 389860.7582541955)),
                    ],
                ],
                "type": "MultiLineString",
            },
            "properties": {},
            "type": "Feature",
        },
    )

    input_msg = get_geojson("Point", "0.1, 3.5")
    assert geo_handler._apply_filters(input_msg) == (
        True,
        {
            "geometry": {
                "coordinates": approx((11131.949079326665, 389860.7582541955)),
                "type": "Point",
            },
            "properties": {},
            "type": "Feature",
        },
    )

    input_msg = get_geojson("MultiPoint", "[0.1, 3.5], [2.1, 3.4]")
    assert geo_handler._apply_filters(input_msg) == (
        True,
        {
            "geometry": {
                "coordinates": [
                    approx((11131.949079326665, 389860.7582541955)),
                    approx((233770.93066587413, 378708.59661392024)),
                ],
                "type": "MultiPoint",
            },
            "properties": {},
            "type": "Feature",
        },
    )

    input_msg = get_geojson("Polygon", "[[0.1, 3.5], [2.1, 3.4]]")
    assert geo_handler._apply_filters(input_msg) == (
        True,
        {
            "geometry": {
                "coordinates": [
                    [
                        approx((11131.949079326665, 389860.7582541955)),
                        approx((233770.93066587413, 378708.59661392024)),
                    ]
                ],
                "type": "Polygon",
            },
            "properties": {},
            "type": "Feature",
        },
    )

    input_msg = get_geojson(
        "MultiPolygon",
        "[[[0.1, 3.5], [2.1, 3.4]], [[2.1, 3.4], [2.1, 3.4]]], [[[0.1, 3.5], [2.1, 3.4]]]",
    )
    assert geo_handler._apply_filters(input_msg) == (
        True,
        {
            "geometry": {
                "coordinates": [
                    [
                        [
                            approx((11131.949079326665, 389860.7582541955)),
                            approx((233770.93066587413, 378708.59661392024)),
                        ],
                        [
                            approx((233770.93066587413, 378708.59661392024)),
                            approx((233770.93066587413, 378708.59661392024)),
                        ],
                    ],
                    [
                        [
                            approx((11131.949079326665, 389860.7582541955)),
                            approx((233770.93066587413, 378708.59661392024)),
                        ]
                    ],
                ],
                "type": "MultiPolygon",
            },
            "properties": {},
            "type": "Feature",
        },
    )

    input_msg = get_geojson("Unknown", "[0.1, 3.5], [2.1, 3.4]")
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))


def test_feature_collection_bbox_filter(loop, geo_handler):
    loop.run_until_complete(geo_handler._handle_remote_message("BBOX 1 2 3 4"))
    assert "bbox" in geo_handler.filters

    input_msg = get_feature_collection(
        get_geojson("LineString", "[0, 0.5], [0.1, 0.7]"),
        get_geojson("Polygon", "[[5, 6], [7, 8]]"),
    )
    assert geo_handler._apply_filters(input_msg) == (False, loads(input_msg))

    input_msg = get_feature_collection(
        get_geojson("LineString", "[0, 0.5], [0.1, 0.7]"),
        get_geojson("Polygon", "[[5, 6], [7, 8]]"),
        get_geojson("Point", "1.5, 2.5"),
    )
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))

    input_msg = get_feature_collection(
        get_geojson("LineString", "[0.1, 3.5], [2.1, 3.4]"),
        get_geojson("Point", "0.1, 3.5"),
        get_geojson("Polygon", "[[0.1, 3.5], [2.1, 3.4]]"),
        get_geojson("Unknown", "[0.1, 3.5], [2.1, 3.4]"),
    )
    assert geo_handler._apply_filters(input_msg) == (True, loads(input_msg))


def test_feature_collection_projection_filter(loop, geo_handler):
    assert geo_handler._projection_filter({}) is True
    loop.run_until_complete(geo_handler._handle_remote_message("PROJECTION epsg:3857"))
    assert geo_handler.projection_out is not None
    assert geo_handler._projection_filter({}) is True

    input_msg = get_feature_collection(
        get_geojson("LineString", "[0.1, 3.5], [2.1, 3.4]"),
        get_geojson("Point", "0.1, 3.5"),
        get_geojson("Polygon", "[[0.1, 3.5], [2.1, 3.4]]"),
        get_geojson("Unknown", "[0.1, 3.5], [2.1, 3.4]"),
    )
    assert geo_handler._apply_filters(input_msg) == (
        True,
        {
            "type": "FeatureCollection",
            "properties": {},
            "features": [
                {
                    "geometry": {
                        "coordinates": [
                            approx((11131.949079326665, 389860.7582541955)),
                            approx((233770.93066587413, 378708.59661392024)),
                        ],
                        "type": "LineString",
                    },
                    "properties": {},
                    "type": "Feature",
                },
                {
                    "geometry": {
                        "coordinates": approx((11131.949079326665, 389860.7582541955)),
                        "type": "Point",
                    },
                    "properties": {},
                    "type": "Feature",
                },
                {
                    "geometry": {
                        "coordinates": [
                            [
                                approx((11131.949079326665, 389860.7582541955)),
                                approx((233770.93066587413, 378708.59661392024)),
                            ]
                        ],
                        "type": "Polygon",
                    },
                    "properties": {},
                    "type": "Feature",
                },
                {
                    "geometry": {
                        "coordinates": [[0.1, 3.5], [2.1, 3.4]],
                        "type": "Unknown",
                    },
                    "properties": {},
                    "type": "Feature",
                },
            ],
        },
    )


def test_pget_command(loop, geo_handler, redis, websocket):
    with pytest.raises(RemoteMessageHandlerError):
        loop.run_until_complete(geo_handler._handle_remote_message("PGET"))

    loop.run_until_complete(geo_handler._handle_remote_message("PGET foo"))
    redis.await_hvals.assert_not_called()

    loop.run_until_complete(geo_handler._handle_remote_message("PGET egg"))
    redis.await_hvals.assert_called_once_with("egg", encoding="utf-8")
    assert '"source": "egg"' in websocket.await_send.call_args_list[0][0][0]

    loop.run_until_complete(geo_handler._handle_remote_message("PGET egg ref"))
    redis.await_hget.assert_called_once_with("egg", "ref", encoding="utf-8")

    redis.await_hget.reset_mock()
    websocket.await_send.reset_mock()
    loop.run_until_complete(geo_handler._handle_remote_message("PGET egg ref cref"))
    redis.await_hget.assert_called_once_with("egg", "ref", encoding="utf-8")
    assert '"client_reference": "cref"' in websocket.await_send.call_args_list[0][0][0]

    redis.await_hget.reset_mock()
    websocket.await_send.reset_mock()
    loop.run_until_complete(
        geo_handler._handle_remote_message("PGET egg ref client_ref=cref")
    )
    assert '"client_reference": "cref"' in websocket.await_send.call_args_list[0][0][0]

    redis.await_hvals.reset_mock()
    redis.await_hvals.return_value = ['{"hello": "world"}']
    websocket.await_send.reset_mock()
    loop.run_until_complete(geo_handler._handle_remote_message("PGET egg"))
    redis.await_hvals.assert_called_once_with("egg", encoding="utf-8")
    assert (
        '"content": {"hello": "world"}' in websocket.await_send.call_args_list[0][0][0]
    )

    source_data = [
        get_feature_collection(
            get_geojson("LineString", "[0.1, 3.5], [2.1, 3.4]"),
            get_geojson("Point", "0.1, 3.5"),
            get_geojson("Polygon", "[[0.1, 3.5], [2.1, 3.4]]"),
            get_geojson("Unknown", "[0.1, 3.5], [2.1, 3.4]"),
        )
    ]

    redis.await_hvals.reset_mock()
    redis.await_hvals.return_value = source_data
    websocket.await_send.reset_mock()
    loop.run_until_complete(geo_handler._handle_remote_message("PGET egg"))
    redis.await_hvals.assert_called_once_with("egg", encoding="utf-8")
    result = loads(websocket.await_send.call_args_list[0][0][0])
    assert result["content"] == loads(source_data[0])

    redis.await_hvals.reset_mock()
    redis.await_hvals.return_value = source_data
    websocket.await_send.reset_mock()
    loop.run_until_complete(
        geo_handler._handle_remote_message("PGET egg projection=epsg:3857")
    )
    redis.await_hvals.assert_called_once_with("egg", encoding="utf-8")
    result = loads(websocket.await_send.call_args_list[0][0][0])
    assert result["content"] != loads(source_data[0])
