import concurrent.futures
import logging
import os
import uuid
import numpy as np
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse

from utils.db import get_supabase
from utils.bbox import bbox_from_stops, bbox_from_loop, make_cache_key
from utils.normalise import apply_age_boost
from utils.grid_sampler import enrich_all_edges
from utils.map_layers import utci_grid_to_png, wind_grid_to_png, solar_grid_to_png, graph_to_network_geojson

from models.request_models import RouteRequest
from models.response_models import RouteResult, PoiWaypoint

from services.cache_service import get_cached_sdk, deserialise_grids, store_sdk_cache
from services.sdk_service import run_sdk
from services.osm_service import get_walk_graph_cached, assign_costs, nearest_node
from services.poi_service import find_poi_nodes
from services.routing_service import (
    route_typical,
    route_multi,
    route_loop,
    get_path_distance,
    path_to_geojson,
    path_to_edge_scores,
    build_summary
)

# Set SKIP_SDK=true in .env to bypass the Infrared API (OSM-only, instant results for testing)
SKIP_SDK = os.getenv("SKIP_SDK", "false").lower() == "true"
# Seconds before the SDK call is aborted and routing falls back to OSM-only scores
SDK_TIMEOUT_S = int(os.getenv("SDK_TIMEOUT", "180"))

logger = logging.getLogger("thermal_router.route")
router = APIRouter(tags=["route"])

# In-memory jobs tracking
jobs = {}

CITY_DEFAULTS = {
    "barcelona": (41.3874, 2.1686),
    "dubai": (25.2048, 55.2708),
    "chennai": (13.0827, 80.2707)
}

# Fixed city-level analysis bboxes for the SDK.
# All routes within a city share ONE cached grid per time_slot, so users never
# re-burn tokens for a second route in the same area.
# Sized to cover typical demo routes; routes outside these bounds fall back to
# the per-route bbox (rare edge case).
_SDK_ANALYSIS_BBOXES = {
    "barcelona": {
        # Covers: Placa de Catalunya, Las Ramblas, Gothic Quarter, Arc de Triomf
        "min_lat": 41.374, "max_lat": 41.404,
        "min_lon": 2.148,  "max_lon": 2.198,
    },
    "dubai": {
        # Covers: DIFC, Downtown Dubai, Burj Khalifa, Dubai Mall area
        "min_lat": 25.182, "max_lat": 25.220,
        "min_lon": 55.256, "max_lon": 55.308,
    },
    "chennai": {
        # Covers: Nungambakkam, Mylapore, Adyar areas
        "min_lat": 13.052, "max_lat": 13.098,
        "min_lon": 80.248, "max_lon": 80.296,
    },
}


def _sdk_bbox_for(city: str, route_bbox: dict) -> dict:
    """
    Return the canonical city-level SDK analysis bbox if the route is contained
    within it; otherwise fall back to the route bbox so the SDK covers the full
    route area regardless of distance from city centre.
    """
    city_sdk = _SDK_ANALYSIS_BBOXES.get(city.lower())
    if city_sdk is None:
        return route_bbox
    # Use city bbox only when the route is fully inside it
    if (city_sdk["min_lat"] <= route_bbox["min_lat"] and
            city_sdk["max_lat"] >= route_bbox["max_lat"] and
            city_sdk["min_lon"] <= route_bbox["min_lon"] and
            city_sdk["max_lon"] >= route_bbox["max_lon"]):
        return city_sdk
    # Route extends outside the city bbox — fall back to route bbox
    logger.info(
        f"Route bbox extends outside city SDK bbox for {city} — using per-route bbox"
    )
    return route_bbox

def _stage(job_id: str, text: str, pct: int) -> None:
    """Push a progress update into the in-memory jobs store."""
    jobs[job_id] = {"status": "processing", "job_id": job_id, "stage": text, "progress": pct}


def process_route_task(job_id: str, req: RouteRequest):
    """
    Background worker task to orchestrate building the walking route.
    """
    logger.info(f"Background task starting for job {job_id}")
    try:
        _stage(job_id, "Resolving route area", 3)

        # 1. Resolve geographic bounding box
        if req.route_type == "loop":
            if not req.stops:
                raise ValueError("Loop routing requires exactly 1 start stop.")
            bbox = bbox_from_loop(req.stops[0].dict(), req.max_distance_m)
        else:
            if len(req.stops) < 2:
                raise ValueError("Typical/Multi routing requires at least 2 stops.")
            bbox = bbox_from_stops([s.dict() for s in req.stops], padding_m=500.0)

        # 2. Resolve persona weights & settings
        _stage(job_id, "Loading persona preferences", 6)
        weights = {"w_speed": 0.25, "w_shade": 0.35, "w_nature": 0.25, "w_discovery": 0.15}
        turn_pref = req.turn_preference
        persona_analyses = ["UTCI", "Wind", "Solar", "Vegetation"]

        if req.persona_id:
            try:
                sb = get_supabase()
                res = sb.table("personas").select("*").eq("id", req.persona_id).execute()
                if res.data:
                    p = res.data[0]
                    weights = {
                        "w_speed": p["w_speed"],
                        "w_shade": p["w_shade"],
                        "w_nature": p["w_nature"],
                        "w_discovery": p["w_discovery"]
                    }
                    turn_pref = p.get("turn_preference", "mid")
                    persona_analyses = p.get("sdk_analyses") or ["UTCI", "Wind", "Solar", "Vegetation"]
            except Exception as p_err:
                logger.warning(f"Could not load persona {req.persona_id} from DB, using defaults: {p_err}")

        elif req.custom_weights:
            weights = req.custom_weights

        # Apply age modifier boost to w_shade
        weights = apply_age_boost(weights, req.age_group)
        logger.info(f"Using resolved weights: {weights}, turns: {turn_pref}")

        # 3. Retrieve microclimate grids (from Cache or SDK)
        _stage(job_id, "Checking microclimate cache", 10)
        analyses = ["utci", "wind", "solar"]

        # Use a canonical city-level bbox for the SDK so every route within the
        # same city+time_slot hits the same cache entry and never re-burns tokens.
        sdk_bbox = _sdk_bbox_for(req.city, bbox)
        cache_key = make_cache_key(req.city, sdk_bbox, req.time_slot, analyses)
        logger.info(f"SDK bbox: {sdk_bbox}  cache_key prefix: {cache_key[:12]}…")

        sdk_result = None
        is_unscored = SKIP_SDK  # honour env flag immediately
        sdk_from_cache = False   # True when loaded from Supabase — skip re-writing

        if not SKIP_SDK:
            # Cache lookup — failure here must NOT kill the live SDK call
            try:
                cached_row = get_cached_sdk(cache_key, city=req.city, time_slot=req.time_slot)
                if cached_row:
                    sdk_result = deserialise_grids(cached_row)
                    sdk_from_cache = True
                    logger.info("Using cached SDK result.")
                    _stage(job_id, "Microclimate data loaded from cache", 75)
            except Exception as cache_err:
                logger.warning(f"Cache lookup failed: {cache_err} — proceeding to live SDK call.")

            # Live SDK call — only when no cache hit
            if sdk_result is None:
                city_lat, city_lon = CITY_DEFAULTS.get(req.city.lower(), (41.3874, 2.1686))
                logger.info(f"No cache hit — calling Infrared SDK for city area (timeout {SDK_TIMEOUT_S}s)…")

                def _sdk_stage(text: str, pct: int) -> None:
                    _stage(job_id, text, pct)

                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                        future = ex.submit(run_sdk, sdk_bbox, req.time_slot, city_lat, city_lon, _sdk_stage)
                        sdk_result = future.result(timeout=SDK_TIMEOUT_S)
                except concurrent.futures.TimeoutError:
                    logger.warning(f"SDK timed out after {SDK_TIMEOUT_S}s — falling back to OSM-only routing.")
                    is_unscored = True
                except Exception as sdk_err:
                    logger.exception(f"Microclimate pipeline failed: {sdk_err} — falling back to OSM-only routing.")
                    is_unscored = True

            # Only write to Supabase when we got a fresh SDK result (not a cache hit)
            if sdk_result and not is_unscored and not sdk_from_cache:
                _stage(job_id, "Storing microclimate data", 78)
                try:
                    store_sdk_cache(cache_key, req.city, sdk_bbox, req.time_slot, analyses, sdk_result)
                except Exception as cache_err:
                    logger.warning(f"Cache write failed (routing continues with live SDK data): {cache_err}")

        # 4. Fetch street network from OpenStreetMap (disk-cached after first download)
        _stage(job_id, "Loading street network", 82)
        G = get_walk_graph_cached(bbox)

        # 5. Map stops to nearest graph nodes
        stop_nodes = [nearest_node(G, stop.lat, stop.lon) for stop in req.stops]

        # 5b. Resolve POI waypoints from the natural-language prompt (if provided).
        poi_waypoint_models: list[PoiWaypoint] = []
        if req.poi_query and req.poi_query.strip() and len(stop_nodes) >= 2:
            _stage(job_id, "Finding POIs on your route", 84)
            try:
                poi_data = find_poi_nodes(G, bbox, req.poi_query)
                if poi_data:
                    poi_nodes = [p["node_id"] for p in poi_data]
                    poi_waypoint_models = [
                        PoiWaypoint(lat=p["lat"], lon=p["lon"], name=p["name"],
                                    poi_type=p["poi_type"], emoji=p["emoji"])
                        for p in poi_data
                    ]
                    stop_nodes = [stop_nodes[0]] + poi_nodes + [stop_nodes[-1]]
                    logger.info(f"Inserted {len(poi_nodes)} POI waypoint(s): {[p['name'] for p in poi_data]}")
                else:
                    logger.info("No POI waypoints resolved from prompt")
            except Exception as poi_err:
                logger.warning(f"POI resolution failed (routing continues without): {poi_err}")

        # 6. Core Raster-to-Vector Enrichment
        _stage(job_id, "Scoring route segments", 88)
        if is_unscored or not sdk_result:
            grids = {}
            bounds = (bbox["min_lon"], bbox["min_lat"], bbox["max_lon"], bbox["max_lat"])
            grid_bounds = None
            veg_features = []
        else:
            grids = {k: v for k, v in sdk_result.items() if isinstance(v, np.ndarray)}
            bounds = sdk_result["bounds"]
            grid_bounds = {
                key: sdk_result[f"{key}_bounds"]
                for key in ("utci", "wind", "solar")
                if f"{key}_bounds" in sdk_result
            } or None
            veg_features = sdk_result.get("vegetation_features") or []

        edge_scores = enrich_all_edges(G, grids, bounds, veg_features, persona_analyses, grid_bounds=grid_bounds)

        # 7. Apply weight vector to edge costs
        G = assign_costs(G, edge_scores, weights)

        # 8. Compute routing path
        _stage(job_id, "Computing optimal path", 94)
        if len(stop_nodes) > 2:
            # POI waypoints were injected — always use multi-stop chaining
            path = route_multi(G, stop_nodes)
        elif req.route_type == "loop":
            path = route_loop(G, stop_nodes[0], req.max_distance_m, turn_pref)
        elif req.route_type == "multi":
            path = route_multi(G, stop_nodes)
        else:
            path = route_typical(G, stop_nodes[0], stop_nodes[1])

        # 9. Format output models
        dist = get_path_distance(G, path)
        route_geojson = path_to_geojson(G, path)
        edge_scores_list = path_to_edge_scores(G, path, edge_scores)

        # Count path edges that pass through high-discovery areas (named streets,
        # plazas, commercial corridors) as a proxy for POI density.
        # The poi_density field is set by assign_costs via _edge_discovery_score.
        poi_count = 0
        for u, v in zip(path[:-1], path[1:]):
            edge_map = G[u].get(v, {})
            if not edge_map:
                continue
            best_k = min(edge_map, key=lambda k: edge_map[k].get("cost", 99999))
            if edge_scores.get((u, v, best_k), {}).get("poi_density", 0) > 0.65:
                poi_count += 1

        summary = build_summary(edge_scores_list, dist, poi_count)

        # 10. Build overlay layers
        _stage(job_id, "Rendering map overlays", 97)
        network_geojson = None
        utci_image = utci_bounds = None
        wind_image = wind_bounds = None
        solar_image = solar_bounds = None

        try:
            network_geojson = graph_to_network_geojson(G)
        except Exception as e:
            logger.warning(f"Network GeoJSON failed: {e}")

        if sdk_result and not is_unscored:
            # Use per-grid bounds for accurate placement (tile-snapped extents)
            def _gb(key: str):
                return sdk_result.get(f"{key}_bounds") or sdk_result.get("bounds")

            # grids is already filtered to numpy arrays only — safe to pass directly
            if "utci" in grids:
                try:
                    utci_image, utci_bounds = utci_grid_to_png(grids["utci"], _gb("utci"))
                except Exception as e:
                    logger.warning(f"UTCI PNG failed: {e}")

            if "wind" in grids:
                try:
                    wind_image, wind_bounds = wind_grid_to_png(grids["wind"], _gb("wind"))
                except Exception as e:
                    logger.warning(f"Wind PNG failed: {e}")

            if "solar" in grids:
                try:
                    solar_image, solar_bounds = solar_grid_to_png(grids["solar"], _gb("solar"))
                except Exception as e:
                    logger.warning(f"Solar PNG failed: {e}")

        result = RouteResult(
            status="done",
            job_id=job_id,
            route_geojson=route_geojson,
            edge_scores=edge_scores_list,
            summary=summary,
            is_unscored=is_unscored,
            network_geojson=network_geojson,
            utci_image=utci_image,   utci_bounds=utci_bounds,
            wind_image=wind_image,   wind_bounds=wind_bounds,
            solar_image=solar_image, solar_bounds=solar_bounds,
            poi_waypoints=poi_waypoint_models,
        )
        jobs[job_id] = result.dict()
        
        # 10. Store log in route_requests table
        try:
            sb = get_supabase()
            sb.table("route_requests").insert({
                "job_id": job_id,
                "city": req.city,
                "route_type": req.route_type,
                "stops": [s.dict() for s in req.stops],
                "time_slot": req.time_slot,
                "summary": summary.dict(),
                "created_at": datetime.now().isoformat()
            }).execute()
        except Exception as db_err:
            logger.warning(f"Could not persist route request to DB: {db_err}")

        logger.info(f"Background task finished for job {job_id} successfully.")

    except Exception as err:
        logger.exception(f"Job {job_id} processing failed.")
        result = RouteResult(
            status="error",
            job_id=job_id,
            error=str(err)
        )
        jobs[job_id] = result.dict()

@router.post("/route", status_code=202)
def create_route(req: RouteRequest, background_tasks: BackgroundTasks):
    """
    Submit a walking route request. Runs asynchronously via BackgroundTasks.
    Returns 202 with job_id for polling.
    """
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "job_id": job_id}
    
    background_tasks.add_task(process_route_task, job_id, req)
    
    return {
        "status": "processing",
        "job_id": job_id,
        "estimated_seconds": 8
    }

@router.get("/route/status/{job_id}", response_model=RouteResult)
def get_route_status(job_id: str):
    """
    Poll the status of an ongoing route routing job.
    """
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return job
