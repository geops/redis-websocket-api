from collections import namedtuple
from functools import partial
from logging import getLogger

from pyproj import Proj as Projection, transform as transform_projection

__all__ = ["GeoCommandsMixin"]

logger = getLogger(__name__)

BoundingBox = namedtuple("BoundingBox", ["left", "bottom", "right", "top"])


class GeoCommandsMixin:
    """Provide functions for excluding or transforming GeoJSON before sending.

    Filter functions accept one positional argument (the message as dict) and
    may accept any number of keyword arguments.
    """

    projection_in = Projection(init="epsg:4326")
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

    def _transform_coords(self, feature_type, coords):
        transform_func = partial(
            transform_projection, self.projection_in, self.projection_out
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
            projection, = args
            if projection == "epsg:4326" and "projection" in self.filters:
                del self.filters["projection"]
            else:
                try:
                    self.projection_out = Projection(init=projection)
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

    def _projection_filter(self, data):
        """Transform coordinates in Feature or FeatureCollection to self.projection_out."""
        if self._is_collection(data):
            return all([self._projection_filter(item) for item in data["features"]])

        if self.projection_out:
            feature_type = self._feature_type(data)
            if feature_type is not None:
                try:
                    if feature_type.startswith("Multi"):
                        data["geometry"]["coordinates"] = [
                            self._transform_coords(feature_type[5:], item)
                            for item in data["geometry"]["coordinates"]
                        ]
                    else:
                        data["geometry"]["coordinates"] = self._transform_coords(
                            feature_type, data["geometry"]["coordinates"]
                        )
                except NotImplementedError:
                    logger.warning(
                        "Not projecting feature of type '%s': %s", feature_type, data
                    )

        return True  # Do not filter anything, just transform data
