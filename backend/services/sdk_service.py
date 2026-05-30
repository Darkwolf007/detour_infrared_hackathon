import json
import os
import logging
from datetime import datetime
import calendar
from infrared_sdk import InfraredClient
from infrared_sdk.tiling.types import TiledRunError
from infrared_sdk.analyses.types import (
    AnalysesName,
    UtciModelBaseRequest,
    UtciModelRequest,
    WindModelRequest,
    SolarRadiationModelRequest,
    BaseAnalysisPayload,
)
from infrared_sdk.models import Location, TimePeriod

logger = logging.getLogger("thermal_router.sdk_service")


def _parse_features(raw) -> list[dict]:
    """Ensure vegetation features are dicts, not JSON strings."""
    result = []
    for f in (raw or []):
        if isinstance(f, str):
            try:
                f = json.loads(f)
            except Exception:
                continue
        if isinstance(f, dict):
            result.append(f)
    return result

# Time slot hours (start, end)
TIME_SLOTS = {
    "early_morning": (6, 9),
    "morning":       (9, 12),
    "afternoon":     (12, 16),
    "evening":       (16, 20),
    "night":         (20, 24),
}

def run_sdk(bbox: dict, time_slot: str, city_lat: float, city_lon: float, on_stage=None) -> dict:
    """
    Run UTCI, Wind, and Solar analyses for a given bbox and time slot.
    Returns: {
        "utci": np.ndarray,
        "wind": np.ndarray,
        "solar": np.ndarray,
        "bounds": tuple,
        "legend": dict,
        "vegetation_features": list
    }
    """
    api_key = os.environ.get("INFRARED_API_KEY")
    if not api_key:
        raise ValueError("INFRARED_API_KEY is not set in environment.")

    # 1. Resolve Time Period (current month, time slot hours)
    now = datetime.now()
    month = now.month
    # Find last day of current month safely
    _, last_day = calendar.monthrange(now.year, month)
    
    h_start, h_end = TIME_SLOTS.get(time_slot, (12, 16))
    # Clamp end hour so it doesn't exceed 23
    if h_end >= 24:
        h_end = 23

    tp = TimePeriod(
        start_month=month,
        start_day=1,
        start_hour=h_start,
        end_month=month,
        end_day=last_day,
        end_hour=h_end,
    )

    polygon = {
        "type": "Polygon",
        "coordinates": [[
            [bbox["min_lon"], bbox["min_lat"]],
            [bbox["max_lon"], bbox["min_lat"]],
            [bbox["max_lon"], bbox["max_lat"]],
            [bbox["min_lon"], bbox["max_lat"]],
            [bbox["min_lon"], bbox["min_lat"]],
        ]]
    }

    logger.info(f"Running Infrared SDK for bbox: {bbox}, slot: {time_slot}")

    def _stage(text: str, pct: int) -> None:
        if on_stage:
            try:
                on_stage(text, pct)
            except Exception:
                pass

    with InfraredClient(api_key=api_key, logger=logger) as client:
        # 2. Fetch context features
        _stage("Fetching 3D city model", 15)
        logger.info("Fetching area context features from Infrared SDK...")
        area = client.buildings.get_area(polygon)
        logger.info(f"Found {area.total_buildings} buildings.")

        _stage("Fetching vegetation data", 30)
        area_veg = client.vegetation.get_area(polygon)
        logger.info(f"Found {area_veg.total_trees} trees.")

        # Ground materials — the /ground-material/collect endpoint is currently
        # returning 500 for every tile, causing analysis tiles to fail.  Skip it
        # entirely so run_area_and_wait can complete without per-tile 500s.
        gm_for_run = {}
        logger.info("Skipping ground materials fetch (endpoint unstable).")

        # 3. Locate nearest TMY weather station and filter timeline
        weather_data = None
        _stage("Fetching weather data", 50)
        try:
            logger.info("Finding weather station...")
            stations = client.weather.get_weather_file_from_location(
                lat=city_lat,
                lon=city_lon,
                radius=50,
            )
            if stations:
                station_id = stations[0].get("uuid") or stations[0].get("identifier")
                logger.info(f"Found weather station: {station_id}")
                weather_data = client.weather.filter_weather_data(
                    identifier=station_id,
                    time_period=tp,
                )
            else:
                logger.warning("No weather stations found — running Wind-only analysis.")
        except Exception as wx_err:
            logger.warning(f"Weather fetch failed: {wx_err} — falling back to Wind-only analysis.")

        # 4. Construct payloads
        wind_payload = WindModelRequest(
            analysis_type=AnalysesName.wind_speed,
            wind_speed=10,
            wind_direction=270,
        )

        if weather_data:
            logger.info("Constructing UTCI + Wind + Solar payloads...")
            utci_payload = UtciModelRequest.from_weatherfile_payload(
                payload=UtciModelBaseRequest(analysis_type=AnalysesName.thermal_comfort_index),
                location=Location(latitude=city_lat, longitude=city_lon),
                time_period=tp,
                weather_data=weather_data,
            )
            solar_payload = SolarRadiationModelRequest.from_weatherfile_payload(
                payload=BaseAnalysisPayload(analysis_type=AnalysesName.solar_radiation),
                location=Location(latitude=city_lat, longitude=city_lon),
                time_period=tp,
                weather_data=weather_data,
            )
            run_payloads = [utci_payload, wind_payload, solar_payload]
        else:
            logger.info("Constructing Wind-only payload (weather unavailable)...")
            run_payloads = [wind_payload]

        # 5. Run analyses
        _stage("Running simulation", 60)
        logger.info(f"Running {len(run_payloads)} analysis/analyses in run_area_and_wait...")
        try:
            results = client.run_area_and_wait(
                run_payloads,
                polygon,
                buildings=area.buildings,
                vegetation=area_veg.features,
                ground_materials=gm_for_run,
            )
        except TiledRunError as tile_err:
            # All tiles failed — log and re-raise so the caller falls back to OSM-only
            logger.error(f"All analysis tiles failed: {tile_err}")
            raise

        if weather_data:
            utci_res, wind_res, solar_res = results
        else:
            wind_res = results[0]
            utci_res = solar_res = None

        # Construct final payload with shapes, bounds, legends, grids.
        # Each analysis grid has its OWN actual extent (tile-boundary-snapped),
        # which may be slightly larger than the input polygon.  Use the SDK-reported
        # bounds so the overlay image is placed correctly; fall back to input bbox
        # only when the SDK did not produce a grid.
        _fallback = (bbox["min_lon"], bbox["min_lat"], bbox["max_lon"], bbox["max_lat"])
        wind_bounds  = wind_res.bounds or _fallback
        utci_bounds  = utci_res.bounds  if utci_res  else _fallback
        solar_bounds = solar_res.bounds if solar_res else _fallback

        sdk_result = {
            "wind":  wind_res.merged_grid,
            "utci":  utci_res.merged_grid  if utci_res  else None,
            "solar": solar_res.merged_grid if solar_res else None,
            "bounds":      utci_bounds if utci_res else wind_bounds,
            "utci_bounds":  utci_bounds,
            "wind_bounds":  wind_bounds,
            "solar_bounds": solar_bounds,
            "legend": {
                "wind": {
                    "min": float(wind_res.min_legend)  if wind_res.min_legend  is not None else 0.0,
                    "max": float(wind_res.max_legend)  if wind_res.max_legend  is not None else 10.0,
                },
                **({"utci": {
                    "min": float(utci_res.min_legend)  if utci_res.min_legend  is not None else 0.0,
                    "max": float(utci_res.max_legend)  if utci_res.max_legend  is not None else 40.0,
                }} if utci_res else {}),
                **({"solar": {
                    "min": float(solar_res.min_legend) if solar_res.min_legend is not None else 0.0,
                    "max": float(solar_res.max_legend) if solar_res.max_legend is not None else 1000.0,
                }} if solar_res else {}),
            },
            "vegetation_features": _parse_features(area_veg.features),
        }
        
        return sdk_result
