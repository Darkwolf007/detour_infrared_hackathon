import base64
import json
import logging
from datetime import datetime, timedelta, timezone

import numpy as np

from utils.bbox import round_bbox
from utils.db import get_supabase

logger = logging.getLogger("thermal_router.cache")

TTL_HOURS = 72  # 3 days — microclimate data is stable enough

# ---------------------------------------------------------------------------
# Grid serialisation  (float32 numpy ↔ base64 string for Supabase JSONB)
# ---------------------------------------------------------------------------

def _grid_to_b64(grid: np.ndarray) -> str:
    return base64.b64encode(grid.astype(np.float32).tobytes()).decode()


def _b64_to_grid(data: str, shape: list[int]) -> np.ndarray:
    return np.frombuffer(base64.b64decode(data), dtype=np.float32).reshape(shape)


def serialise_grids(grids: dict) -> dict:
    """
    Prepare the grids dict for Supabase JSONB storage.
    Input:  {"utci": ndarray, "wind": ndarray, "solar": ndarray}
    Output: {"utci": {"data": "<b64>", "shape": [H, W]}, ...}
    """
    return {
        name: {"data": _grid_to_b64(grid), "shape": list(grid.shape)}
        for name, grid in grids.items()
        if isinstance(grid, np.ndarray)
    }


def _compress_veg(veg_features: list) -> list:
    """
    Compress GeoJSON vegetation features to bare [lon, lat] pairs.
    Reduces a typical 2000-tree payload from ~1.2 MB to ~50 KB.
    Polygons/MultiPolygons are collapsed to their centroid.
    """
    from shapely.geometry import shape as sh_shape

    coords = []
    for f in veg_features:
        if not isinstance(f, dict):
            continue
        geom = f.get("geometry")
        if not geom:
            continue
        g_type = geom.get("type")
        try:
            if g_type == "Point":
                c = geom.get("coordinates", [])
                if len(c) >= 2:
                    coords.append([round(float(c[0]), 6), round(float(c[1]), 6)])
            elif g_type in ("Polygon", "MultiPolygon"):
                centroid = sh_shape(geom).centroid
                coords.append([round(centroid.x, 6), round(centroid.y, 6)])
        except Exception:
            pass
    return coords


def _decompress_veg(compressed: list) -> list:
    """Reconstruct minimal GeoJSON Point features from [lon, lat] pairs."""
    return [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": c}, "properties": {}}
        for c in compressed
        if isinstance(c, list) and len(c) == 2
    ]


def deserialise_grids(row: dict) -> dict:
    """
    Reconstruct numpy arrays + bounds tuple from a sdk_cache row.
    Returns {"utci": ndarray, "wind": ndarray, "solar": ndarray,
             "bounds": (min_lon, min_lat, max_lon, max_lat),
             "vegetation_features": list}
    """
    result: dict = {}

    # Vegetation features are stored inside the grids JSONB under the "_veg" key.
    # Since v2 they are stored as compressed [lon, lat] pairs (not full GeoJSON).
    grids_raw = dict(row.get("grids") or {})
    veg_raw = grids_raw.pop("_veg", None)

    # Extract per-grid bounds stored alongside grids
    for key in ("utci_bounds", "wind_bounds", "solar_bounds"):
        raw = grids_raw.pop(f"_{key}", None)
        if raw and len(raw) == 4:
            result[key] = tuple(raw)

    for name, blob in grids_raw.items():
        if isinstance(blob, dict) and "data" in blob and "shape" in blob:
            result[name] = _b64_to_grid(blob["data"], blob["shape"])

    bounds_raw = row.get("bounds")
    if bounds_raw:
        if isinstance(bounds_raw, list):
            result["bounds"] = tuple(bounds_raw)
        else:
            result["bounds"] = (
                bounds_raw["min_lon"], bounds_raw["min_lat"],
                bounds_raw["max_lon"], bounds_raw["max_lat"],
            )

    # Detect format: compressed list-of-lists vs legacy full GeoJSON features
    if isinstance(veg_raw, list) and veg_raw and isinstance(veg_raw[0], list):
        result["vegetation_features"] = _decompress_veg(veg_raw)
    else:
        result["vegetation_features"] = veg_raw or (row.get("vegetation") or [])
    return result


# ---------------------------------------------------------------------------
# Cache read
# ---------------------------------------------------------------------------

def get_cached_sdk(
    cache_key: str,
    city: str | None = None,
    time_slot: str | None = None,
) -> dict | None:
    """
    Return a sdk_cache row if one exists for this key (or city+time_slot).

    Lookup order:
    1. Exact cache_key match (non-expired)
    2. Most recent city+time_slot match (non-expired) — handles bbox changes
    3. Most recent city+time_slot match (any age) — last resort when API is down
    """
    sb = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Exact key
    res = (
        sb.table("sdk_cache")
        .select("*")
        .eq("cache_key", cache_key)
        .gt("expires_at", now_iso)
        .limit(1)
        .execute()
    )
    if res.data:
        logger.info("SDK cache HIT (exact) key=%s…", cache_key[:16])
        return res.data[0]

    # 2 & 3. Fuzzy fallback by city+time_slot
    if city and time_slot:
        for extra_filter in [True, False]:  # True = non-expired only, False = any age
            q = (
                sb.table("sdk_cache")
                .select("*")
                .eq("city", city)
                .eq("time_slot", time_slot)
                .order("created_at", desc=True)
                .limit(1)
            )
            if extra_filter:
                q = q.gt("expires_at", now_iso)
            res2 = q.execute()
            if res2.data:
                label = "non-expired" if extra_filter else "any-age"
                logger.info("SDK cache HIT (fuzzy %s) city=%s slot=%s", label, city, time_slot)
                return res2.data[0]

    logger.info("SDK cache MISS key=%s…", cache_key[:16])
    return None


# ---------------------------------------------------------------------------
# Cache write
# ---------------------------------------------------------------------------

def store_sdk_cache(
    cache_key: str,
    city: str,
    bbox: dict,
    time_slot: str,
    analyses: list[str],
    sdk_result: dict,
) -> None:
    """
    Persist an SDK result to sdk_cache with a 24-hour TTL.

    sdk_result must contain:
      "utci"   : np.ndarray float32
      "wind"   : np.ndarray float32
      "solar"  : np.ndarray float32
      "bounds" : (min_lon, min_lat, max_lon, max_lat)
      "legend" : {"utci": {"min": float, "max": float}, ...}   optional
    """
    sb = get_supabase()
    now = datetime.now(timezone.utc)

    grids = {k: v for k, v in sdk_result.items() if isinstance(v, np.ndarray)}
    bounds = sdk_result.get("bounds")
    legend = sdk_result.get("legend", {})

    # Downsample grids if the serialised payload would exceed Supabase's
    # statement timeout budget (~400 KB). Each 2× downsample halves both
    # dimensions so routing quality is unaffected (street segments >> 1 pixel).
    MAX_GRID_BYTES = 400_000
    grids_serialised = serialise_grids(grids)
    payload_bytes = len(json.dumps(grids_serialised).encode())
    if payload_bytes > MAX_GRID_BYTES:
        step = 2
        while payload_bytes > MAX_GRID_BYTES and step <= 8:
            grids_ds = {k: v[::step, ::step] for k, v in grids.items()}
            grids_serialised = serialise_grids(grids_ds)
            payload_bytes = len(json.dumps(grids_serialised).encode())
            step *= 2
        logger.info(f"Grids downsampled ×{step // 2} to fit cache budget ({payload_bytes // 1024} KB)")

    # Embed vegetation_features inside grids JSONB under "_veg" key
    veg = sdk_result.get("vegetation_features") or []
    if veg:
        grids_serialised["_veg"] = _compress_veg(veg)

    # Embed per-grid actual bounds (tile-boundary-snapped extents from the SDK)
    for key in ("utci_bounds", "wind_bounds", "solar_bounds"):
        val = sdk_result.get(key)
        if val:
            grids_serialised[f"_{key}"] = list(val)

    row = {
        "cache_key": cache_key,
        "city": city,
        "bbox": round_bbox(bbox),
        "time_slot": time_slot,
        "analyses": sorted(analyses),
        "grids": grids_serialised,
        "bounds": list(bounds) if bounds else None,
        "legend": legend,
        "expires_at": (now + timedelta(hours=TTL_HOURS)).isoformat(),
        "created_at": now.isoformat(),
    }

    try:
        sb.table("sdk_cache").insert(row).execute()
        logger.info("SDK cache stored key=%s… city=%s slot=%s", cache_key[:16], city, time_slot)
    except Exception as e:
        err_str = str(e)
        if "23505" in err_str or "duplicate" in err_str.lower():
            logger.info("SDK cache: key already exists, skipping write (race condition)")
        else:
            raise


# ---------------------------------------------------------------------------
# Cache stats  (used by GET /cache/status)
# ---------------------------------------------------------------------------

def get_cache_stats() -> dict:
    """Return row count and oldest/newest entry for monitoring."""
    sb = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()

    total = sb.table("sdk_cache").select("id", count="exact").execute()
    live  = (
        sb.table("sdk_cache")
        .select("id", count="exact")
        .gt("expires_at", now_iso)
        .execute()
    )
    return {
        "total_rows": total.count,
        "live_rows":  live.count,
        "expired_rows": (total.count or 0) - (live.count or 0),
    }
