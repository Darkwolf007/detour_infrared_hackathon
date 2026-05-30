"""
Pre-warm the OSM walk graph disk cache for all 3 cities.

After this runs successfully the routing server never calls Overpass API again —
every route request loads from disk in ~0.1 s.

=== TWO MODES ===

MODE A  (automatic, tries Overpass API over the internet)
    cd thermal-router/backend
    python prewarm_osm.py

    If your network blocks Overpass API use MODE B instead.

MODE B  (manual, load from local .osm files you downloaded)
    1. For each city download an .osm extract covering the bbox shown below.

       Recommended:  https://extract.bbbike.org/
         - Click "Bounding box", paste the coords, choose format "OSM XML (.osm.gz)"
         - Download the .osm.gz, then place it in  thermal-router/backend/_osm_input/

       Alternative (if browser can reach it):  https://overpass-turbo.eu/
         - Draw bbox on map → Export → OpenStreetMap data (.osm)

    2. Name the files exactly:
         thermal-router/backend/_osm_input/barcelona.osm   (or .osm.gz)
         thermal-router/backend/_osm_input/dubai.osm       (or .osm.gz)
         thermal-router/backend/_osm_input/chennai.osm     (or .osm.gz)

    3. Re-run:  python prewarm_osm.py
       MODE B activates automatically when the .osm / .osm.gz files are found.

BBOXES to paste into BBBike / Overpass Turbo:
    Barcelona   min_lon=2.120  min_lat=41.355  max_lon=2.220  max_lat=41.430
    Dubai       min_lon=55.200 min_lat=25.100  max_lon=55.380 max_lat=25.310
    Chennai     min_lon=80.200 min_lat=13.000  max_lon=80.360 max_lat=13.160
"""

import gzip
import logging
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))

import osmnx as ox

from services.osm_service import get_walk_graph_cached, _graph_cache_path, _GRAPH_CACHE_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
logger = logging.getLogger("prewarm")

_OSM_INPUT_DIR = os.path.join(os.path.dirname(__file__), "_osm_input")

CITY_BBOXES = {
    "barcelona": {
        "min_lat": 41.340, "max_lat": 41.450,
        "min_lon": 2.080,  "max_lon": 2.240,
    },
    "dubai": {
        "min_lat": 25.090, "max_lat": 25.320,
        "min_lon": 55.170, "max_lon": 55.400,
    },
    "chennai": {
        "min_lat": 13.055, "max_lat": 13.110,
        "min_lon": 80.250, "max_lon": 80.300,
    },
}


def _resolve_osm_file(city: str) -> str | None:
    """Return path to a usable .osm file, unzipping .osm.gz automatically if needed."""
    osm_path = os.path.join(_OSM_INPUT_DIR, f"{city}.osm")
    gz_path  = os.path.join(_OSM_INPUT_DIR, f"{city}.osm.gz")

    if os.path.exists(osm_path):
        return osm_path

    if os.path.exists(gz_path):
        logger.info(f"Unzipping {gz_path} → {osm_path}")
        with gzip.open(gz_path, "rb") as f_in, open(osm_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        return osm_path

    return None


def prewarm_from_xml(city: str, bbox: dict, osm_file: str) -> None:
    """Load graph from a local .osm file, clip to bbox, and save to the disk cache."""
    cache_path = _graph_cache_path(bbox)
    if os.path.exists(cache_path):
        logger.info(f"{city}: graphml already cached — skipping ({cache_path})")
        return
    logger.info(f"{city}: loading from local file {osm_file}")
    # graph_from_xml in osmnx v2 has no network_type param; we load everything
    # and rely on the highway-safety penalty in assign_costs to deprioritise
    # non-walkable edges at routing time.
    G = ox.graph_from_xml(osm_file, retain_all=True)

    # Clip to our target bbox (osmnx v2 bbox tuple: west, south, east, north)
    G = ox.truncate.truncate_graph_bbox(
        G,
        (bbox["min_lon"], bbox["min_lat"], bbox["max_lon"], bbox["max_lat"]),
    )
    G = ox.convert.to_undirected(G)
    ox.save_graphml(G, filepath=cache_path)
    logger.info(
        f"{city}: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges — "
        f"saved to cache ({cache_path})"
    )


if __name__ == "__main__":
    logger.info(f"OSM graph cache directory: {os.path.abspath(_GRAPH_CACHE_DIR)}")
    os.makedirs(_GRAPH_CACHE_DIR, exist_ok=True)
    os.makedirs(_OSM_INPUT_DIR, exist_ok=True)

    for city, bbox in CITY_BBOXES.items():
        logger.info(f"=== Processing {city.upper()} ===")
        try:
            osm_file = _resolve_osm_file(city)
            if osm_file:
                logger.info(f"{city}: MODE B — using local .osm file")
                prewarm_from_xml(city, bbox, osm_file)
            else:
                logger.info(f"{city}: MODE A — downloading from Overpass API")
                G = get_walk_graph_cached(bbox)
                logger.info(
                    f"{city}: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges — cached OK"
                )
        except Exception as e:
            logger.error(f"{city}: FAILED — {e}")

    logger.info("")
    logger.info("Done. Restart the backend server — all routes now load from disk.")
    logger.info(f"Cache files: {os.path.abspath(_GRAPH_CACHE_DIR)}")
