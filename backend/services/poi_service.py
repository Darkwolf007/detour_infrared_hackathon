"""
POI resolution: parse a natural-language prompt for amenity keywords,
query Overpass via osmnx, and return graph node IDs to use as waypoints.
"""
import logging
import networkx as nx
import osmnx as ox

from services.osm_service import nearest_node

logger = logging.getLogger("thermal_router.poi_service")

# Display emoji for each OSM amenity / shop / leisure type
_POI_EMOJI: dict[str, str] = {
    "cafe": "☕", "post_office": "📮", "pharmacy": "💊",
    "bank": "🏦", "atm": "💳", "supermarket": "🛒",
    "convenience": "🛒", "restaurant": "🍽", "fast_food": "🍔",
    "park": "🌳", "garden": "🌿", "museum": "🏛",
    "library": "📚", "fitness_centre": "💪", "hospital": "🏥",
    "bus_stop": "🚌", "bakery": "🥐",
}

def _emoji_for(tags: dict) -> str:
    for val in tags.values():
        vals = [val] if isinstance(val, str) else val
        for v in vals:
            if v in _POI_EMOJI:
                return _POI_EMOJI[v]
    return "📍"

def _type_for(tags: dict) -> str:
    for val in tags.values():
        vals = [val] if isinstance(val, str) else val
        for v in vals:
            if isinstance(v, str):
                return v
    return "poi"

# ---------------------------------------------------------------------------
# Keyword → OSM tag mapping
# ---------------------------------------------------------------------------

KEYWORD_TAGS: list[tuple[str, dict]] = [
    # food / drink
    ("coffee",       {"amenity": "cafe"}),
    ("café",         {"amenity": "cafe"}),
    ("cafe",         {"amenity": "cafe"}),
    ("tea",          {"amenity": "cafe"}),
    ("juice",        {"amenity": "cafe"}),
    ("bakery",       {"shop": "bakery"}),
    ("restaurant",   {"amenity": "restaurant"}),
    ("eat",          {"amenity": ["restaurant", "fast_food"]}),
    ("lunch",        {"amenity": ["restaurant", "fast_food"]}),
    ("dinner",       {"amenity": "restaurant"}),
    ("fast food",    {"amenity": "fast_food"}),
    # errands
    ("post office",  {"amenity": "post_office"}),
    ("postoffice",   {"amenity": "post_office"}),
    ("postal",       {"amenity": "post_office"}),
    ("pharmacy",     {"amenity": "pharmacy"}),
    ("chemist",      {"amenity": "pharmacy"}),
    ("medicine",     {"amenity": "pharmacy"}),
    ("bank",         {"amenity": "bank"}),
    ("atm",          {"amenity": "atm"}),
    ("cash",         {"amenity": "atm"}),
    ("supermarket",  {"shop": "supermarket"}),
    ("grocery",      {"shop": ["supermarket", "convenience"]}),
    ("convenience",  {"shop": "convenience"}),
    ("shopping",     {"shop": True}),
    # leisure
    ("park",         {"leisure": "park"}),
    ("garden",       {"leisure": ["park", "garden"]}),
    ("library",      {"amenity": "library"}),
    ("gym",          {"leisure": "fitness_centre"}),
    ("museum",       {"tourism": "museum"}),
    ("monument",     {"tourism": "monument"}),
    ("viewpoint",    {"tourism": "viewpoint"}),
    # transport
    ("bus stop",     {"highway": "bus_stop"}),
    ("metro",        {"station": "subway"}),
    ("hospital",     {"amenity": "hospital"}),
    ("clinic",       {"amenity": ["clinic", "hospital"]}),
]


def extract_poi_tags(query: str) -> list[dict]:
    """
    Return a deduplicated list of OSM tag dicts matching keywords in `query`.
    Capped at 3 unique POI types to avoid over-complicated routes.
    """
    q = query.lower()
    found: list[dict] = []
    seen: set[str] = set()
    for keyword, tags in KEYWORD_TAGS:
        if keyword in q:
            key = str(sorted(tags.items()))
            if key not in seen:
                found.append(tags)
                seen.add(key)
            if len(found) >= 3:
                break
    return found


# ---------------------------------------------------------------------------
# Graph-node resolution
# ---------------------------------------------------------------------------

def _features_from_bbox(bbox: dict, tags: dict):
    """
    Wrapper around ox.features_from_bbox that handles the API change in osmnx 2.x
    (bbox tuple vs positional north/south/east/west).
    Returns a GeoDataFrame or None on failure.
    """
    try:
        # osmnx 2.x: bbox = (left, bottom, right, top) = (min_lon, min_lat, max_lon, max_lat)
        return ox.features_from_bbox(
            (bbox["min_lon"], bbox["min_lat"], bbox["max_lon"], bbox["max_lat"]),
            tags=tags,
        )
    except TypeError:
        # osmnx 1.x positional form
        try:
            return ox.features_from_bbox(
                north=bbox["max_lat"], south=bbox["min_lat"],
                east=bbox["max_lon"],  west=bbox["min_lon"],
                tags=tags,
            )
        except Exception:
            return None
    except Exception as e:
        logger.warning("features_from_bbox failed for %s: %s", tags, e)
        return None


def find_poi_nodes(G: nx.MultiGraph, bbox: dict, poi_query: str) -> list[dict]:
    """
    Parse `poi_query` for amenity keywords, query OSM for matching features
    within `bbox`, snap each to the nearest graph node.

    Returns a list of dicts:
        {"node_id": int, "lat": float, "lon": float,
         "name": str, "poi_type": str, "emoji": str}
    One entry per unique POI type found (max 3).
    """
    tag_list = extract_poi_tags(poi_query)
    if not tag_list:
        logger.info("No POI keywords found in query: %r", poi_query)
        return []

    results: list[dict] = []

    for tags in tag_list:
        try:
            gdf = _features_from_bbox(bbox, tags)
            if gdf is None or gdf.empty:
                logger.info("No OSM features for tags %s", tags)
                continue

            for _, row in gdf.head(5).iterrows():
                try:
                    centroid = row.geometry.centroid
                    # Use the project's vectorised haversine nearest-node finder.
                    # ox.distance.nearest_nodes requires graph['crs'] + scikit-learn,
                    # neither of which is guaranteed here (DB-built graphs have no crs,
                    # sklearn is not installed) — it would raise and silently drop the POI.
                    node_id = nearest_node(G, lat=centroid.y, lon=centroid.x)
                    node_data = G.nodes[node_id]
                    poi_name = str(row.get("name", "")).strip() or _type_for(tags).replace("_", " ").title()
                    results.append({
                        "node_id": node_id,
                        "lat":  float(node_data.get("y", centroid.y)),
                        "lon":  float(node_data.get("x", centroid.x)),
                        "name": poi_name,
                        "poi_type": _type_for(tags),
                        "emoji": _emoji_for(tags),
                    })
                    logger.info("POI waypoint: %s @ node %d (%.5f, %.5f)",
                                poi_name, node_id, centroid.y, centroid.x)
                    break
                except Exception as snap_err:
                    logger.debug("Snap failed: %s", snap_err)
                    continue

        except Exception as e:
            logger.warning("POI lookup failed for tags %s: %s", tags, e)
            continue

    return results
