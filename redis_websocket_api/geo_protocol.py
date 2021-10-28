from collections import namedtuple
from functools import partial, lru_cache
from logging import getLogger

from pyproj import Proj, transform as transform_projection

__all__ = ["GeoCommandsMixin"]

logger = getLogger(__name__)

BoundingBox = namedtuple("BoundingBox", ["left", "bottom", "right", "top"])


@lru_cache(maxsize=128)
def get_projection(value):
    return Proj(init=value)


class GeoCommandsMixin:
    """Provide functions for excluding or transforming GeoJSON before sending.

    Filter functions accept one positional argument (the message as dict) and
    may accept any number of keyword arguments.
    """

    default_projection = "epsg:4326"
    projection_in = get_projection(default_projection)
    projection_out = None
    bbox = None

    @staticmethod
    def _is_collection(data):
        return isinstance(data, dict) and data.get("type") == "FeatureCollection"

    @staticmethod
    def _feature_type(data):
        if isinstance(data, dict) and data.get("type") == "Feature":
            return data["geometry"]["type"]
        else:
            return None

    @staticmethod
    def _point_in_bbox(point, bbox):
        x, y = point
        return x > bbox.left and x < bbox.right and y > bbox.bottom and y < bbox.top

    def _feature_coords_in_bbox(self, bbox, feature_type, coords):
        if feature_type == "Polygon":
            for ring in coords:
                if any((self._point_in_bbox(point, bbox) for point in ring)):
                    return True
            return False
        elif feature_type == "LineString":
            return any((self._point_in_bbox(point, bbox) for point in coords))
        elif feature_type == "Point":
            return self._point_in_bbox(coords, bbox)

        raise NotImplementedError(
            "Feature type {} is not supported yet".format(feature_type)
        )

    def _transform_coords(self, feature_type, coords, projection_out=None):
        if projection_out == get_projection(self.default_projection):
            return coords

        transform_func = partial(
            transform_projection,
            self.projection_in,
            projection_out or self.projection_out,
        )

        if feature_type == "LineString":
            return [transform_func(*point) for point in coords]
        elif feature_type == "Polygon":
            return [[transform_func(*point) for point in ring] for ring in coords]
        elif feature_type == "Point":
            return transform_func(*coords)

        raise NotImplementedError(
            "Feature type {} is not supported yet".format(feature_type)
        )

    async def _handle_bbox_command(self, *args):
        """Set BoundingBox and activate box_filter."""
        if len(args) == 4:
            left, bottom, right, top = map(float, args)
            self.bbox = BoundingBox(left, bottom, right, top)
            self.filters["bbox"] = self._bbox_filter
            logger.debug(
                "Client %s set self.bbox to %s",
                self.websocket.remote_address,
                self.bbox,
            )
        elif len(args) == 0 and self.filters.pop("bbox", None):
            logger.debug("Client %s removed self.bbox", self.websocket.remote_address)

    async def _handle_projection_command(self, *args):
        """Set projection_out and activate projection_filter."""
        if len(args) != 1:
            logger.warning(
                "Got %s arguments for 'PROJECTION' from %s, expected 1.",
                len(args),
                self.websocket.remote_address,
            )
        else:
            (projection,) = args
            if projection == self.default_projection:
                if "projection" in self.filters:
                    del self.filters["projection"]
                    logger.debug(
                        "Removed 'PROJECTION' filter for %s",
                        self.websocket.remote_address,
                    )
            else:
                try:
                    self.projection_out = get_projection(projection)
                    self.filters["projection"] = self._projection_filter
                    logger.debug(
                        "Set 'PROJECTION' to '%s' for %s.",
                        projection,
                        self.websocket.remote_address,
                    )
                except RuntimeError:
                    logger.info(
                        "Could not set 'PROJECTION' to '%s' for %s.",
                        projection,
                        self.websocket.remote_address,
                    )

    async def _handle_pget_command(
        self, channel_name, ref=None, client_ref=None, projection=None
    ):
        """Like GET but with srid option for specifieing projection"""
        if not self.channel_is_allowed(channel_name):
            return

        projection_out = get_projection(projection or self.default_projection)

        if ref is not None:
            source = "{} {}".format(channel_name, ref)
            values = [await self.redis.hget(channel_name, ref, encoding="utf-8")]
        else:
            source = channel_name
            values = await self.redis.hvals(channel_name, encoding="utf-8") or ()

        send_count = 0
        for value in values:
            passed, data = self._apply_filters(value, exclude="projection")
            passed = self._projection_filter(data, projection_out=projection_out)
            if passed:
                send_count += 1
                await self._send(source, data, client_reference=client_ref)

        if send_count == 0:
            send_count = 1
            await self._send(channel_name, None, client_reference=client_ref)

        logger.debug(
            "Sent %s messages in response to 'PGET %s %s %s %s'.",
            send_count,
            channel_name,
            ref,
            client_ref,
            projection,
        )

    def _bbox_filter(self, data, bbox=None):
        """Include Feature or FeatureCollection if any of it's coordinates is within bbox.

        Does not exclude messages which are not features.

        :param bbox: BoundingBox to filer by (default: self.bbox)
        """
        bbox = bbox or self.bbox
        if self._is_collection(data):
            return any(
                map(lambda item: self._bbox_filter(item, bbox), data["features"])
            )

        feature_type = self._feature_type(data)
        if feature_type is not None and bbox:
            try:
                if feature_type.startswith("Multi"):
                    return any(
                        (
                            self._feature_coords_in_bbox(bbox, feature_type[5:], item)
                            for item in data["geometry"]["coordinates"]
                        )
                    )
                else:
                    return self._feature_coords_in_bbox(
                        bbox, feature_type, data["geometry"]["coordinates"]
                    )
            except NotImplementedError:
                logger.warning(
                    "Not applying BBOX filter to Feature type '%s' in %s",
                    feature_type,
                    data,
                )

        return True  # Only filter objects we could handle above

    def _projection_filter(self, data, projection_out=None):
        """Transform coordinates in Feature or FeatureCollection to projection_out.

        Uses self.projection_out set by PROJECTION by default.
        """
        if self._is_collection(data):
            return all(
                [
                    self._projection_filter(item, projection_out=projection_out)
                    for item in data["features"]
                ]
            )

        if projection_out or self.projection_out:
            feature_type = self._feature_type(data)
            if feature_type is not None:
                try:
                    if feature_type.startswith("Multi"):
                        data["geometry"]["coordinates"] = [
                            self._transform_coords(
                                feature_type[5:], item, projection_out
                            )
                            for item in data["geometry"]["coordinates"]
                        ]
                    else:
                        data["geometry"]["coordinates"] = self._transform_coords(
                            feature_type,
                            data["geometry"]["coordinates"],
                            projection_out,
                        )
                except NotImplementedError:
                    logger.warning(
                        "Not projecting feature of type '%s': %s", feature_type, data
                    )

        return True  # Do not filter anything, just transform data
