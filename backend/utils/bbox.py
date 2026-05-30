import hashlib
import json


# ---------------------------------------------------------------------------
# Bbox construction
# ---------------------------------------------------------------------------

def bbox_from_stops(stops: list[dict], padding_m: float = 500.0) -> dict:
    """Tight bbox around a list of {lat, lon} stops with padding in metres."""
    pad = padding_m / 111_000
    lats = [s["lat"] for s in stops]
    lons = [s["lon"] for s in stops]
    return {
        "min_lat": min(lats) - pad,
        "max_lat": max(lats) + pad,
        "min_lon": min(lons) - pad,
        "max_lon": max(lons) + pad,
    }


def bbox_from_loop(start: dict, max_dist_m: float) -> dict:
    """Square bbox centred on start that comfortably contains a loop of max_dist_m."""
    pad = (max_dist_m / 111_000) + 0.005
    return {
        "min_lat": start["lat"] - pad,
        "max_lat": start["lat"] + pad,
        "min_lon": start["lon"] - pad,
        "max_lon": start["lon"] + pad,
    }


# ---------------------------------------------------------------------------
# Bbox utilities
# ---------------------------------------------------------------------------

def round_bbox(bbox: dict, dp: int = 3) -> dict:
    """Round all coordinates to dp decimal places (~110 m at dp=3)."""
    return {k: round(v, dp) for k, v in bbox.items()}


def bbox_center(bbox: dict) -> tuple[float, float]:
    """Return (lat, lon) centre of bbox — used for weather station lookup."""
    lat = (bbox["min_lat"] + bbox["max_lat"]) / 2
    lon = (bbox["min_lon"] + bbox["max_lon"]) / 2
    return lat, lon


def bbox_to_polygon(bbox: dict) -> dict:
    """
    Convert bbox dict to a closed GeoJSON Polygon.
    Coordinates are [longitude, latitude] per RFC 7946.
    First and last ring vertex are identical (required by SDK).
    """
    min_lon, min_lat = bbox["min_lon"], bbox["min_lat"]
    max_lon, max_lat = bbox["max_lon"], bbox["max_lat"]
    return {
        "type": "Polygon",
        "coordinates": [[
            [min_lon, min_lat],  # SW
            [max_lon, min_lat],  # SE
            [max_lon, max_lat],  # NE
            [min_lon, max_lat],  # NW
            [min_lon, min_lat],  # SW — closed ring
        ]],
    }


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------

def make_cache_key(
    city: str,
    bbox: dict,
    time_slot: str,
    analyses: list[str],
) -> str:
    """
    sha256( city : bbox_3dp_json : time_slot : sorted_analyses )
    Bbox is rounded to 3 dp before hashing (~110 m grid snapping) so nearby
    routes over the same area reuse the same cache entry.
    """
    bbox_r = round_bbox(bbox, dp=3)
    payload = (
        f"{city}:"
        f"{json.dumps(bbox_r, sort_keys=True)}:"
        f"{time_slot}:"
        f"{sorted(analyses)}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()
