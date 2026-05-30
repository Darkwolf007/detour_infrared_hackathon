import os
import logging
from dotenv import load_dotenv

# Import the exact classes and enums used in the official SDK demos
from infrared_sdk import InfraredClient
from infrared_sdk.analyses.types import (
    AnalysesName,
    UtciModelBaseRequest,
    UtciModelRequest,
)
from infrared_sdk.models import Location, TimePeriod

# 1. Setup local logging to trace the simulation steps clearly
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s"
)
logger = logging.getLogger("infrared_test")

# 2. Load environment variables from your local .env file
load_dotenv()

API_KEY = os.getenv("INFRARED_API_KEY")
if not API_KEY or API_KEY == "your_actual_api_key_here":
    raise ValueError("Please set a valid INFRARED_API_KEY in your .env file.")

# 3. Setup core testing configurations (Using a small zone in Munich)
POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [11.570, 48.195],
            [11.580, 48.195],
            [11.580, 48.201],
            [11.570, 48.201],
            [11.570, 48.195],  # Loop closed perfectly
        ]
    ],
}

LATITUDE = 48.1983
LONGITUDE = 11.575

# The SDK requires an explicit non-zero duration window (e.g., a month block or day sequence)
TIME_PERIOD = TimePeriod(
    start_month=7,
    start_day=1,
    start_hour=12,
    end_month=7,
    end_day=31,
    end_hour=16,
)

def run_test_pipeline():
    # 4. Initialize client context manager
    logger.info("Connecting to Infrared City API...")
    with InfraredClient(logger=logger) as client:
        
        # 5. Fetch required spatial layers once
        logger.info("Fetching architectural geometries...")
        area = client.buildings.get_area(POLYGON)
        logger.info(f"Found {area.total_buildings} buildings.")

        logger.info("Fetching local vegetation mapping...")
        area_veg = client.vegetation.get_area(POLYGON)
        logger.info(f"Found {area_veg.total_trees} trees.")

        logger.info("Fetching base surface layers...")
        area_gm = client.ground_materials.get_area(POLYGON)
        logger.info(f"Found {area_gm.total_features} ground material features.")

        # API Safeguard: Skip ground material injection if the polygon layer is massive
        gm_for_run = area_gm.layers if area_gm.total_features <= 5000 else {}

        # 6. Resolve weather parameters
        logger.info("Locating nearest TMY weather monitoring station...")
        stations = client.weather.get_weather_file_from_location(
            lat=LATITUDE,
            lon=LONGITUDE,
            radius=50,
        )
        if not stations:
            raise RuntimeError("No operational weather stations found within a 50km radius.")
            
        weather_id = stations[0].get("identifier") or stations[0].get("uuid")
        logger.info(f"Using station index: {weather_id}")

        logger.info("Extracting meteorological timelines...")
        weather_data = client.weather.filter_weather_data(
            identifier=weather_id,
            time_period=TIME_PERIOD,
        )

        # 7. Construct advanced model request via factory initializer
        logger.info("Building full UTCI analysis schema...")
        payload = UtciModelRequest.from_weatherfile_payload(
            payload=UtciModelBaseRequest(
                analysis_type=AnalysesName.thermal_comfort_index
            ),
            location=Location(latitude=LATITUDE, longitude=LONGITUDE),
            time_period=TIME_PERIOD,
            weather_data=weather_data,
        )

        # 8. Execute the automated micro-tiling orchestration loop
        logger.info("Submitting tasks and entering automated execution loop...")
        result = client.run_area_and_wait(
            payload,
            POLYGON,
            buildings=area.buildings,
            vegetation=area_veg.features,
            ground_materials=gm_for_run,
        )
        
        # 9. Log out out tracking stats
        logger.info("==================================================")
        logger.info("               SIMULATION REPORT                  ")
        logger.info("==================================================")
        logger.info(f"Analysis Type : {result.analysis_type}")
        logger.info(f"Grid Matrix   : {result.grid_shape[0]}x{result.grid_shape[1]} cells")
        logger.info(f"Job Status    : {result.succeeded_jobs}/{result.total_jobs} tasks OK")
        logger.info(f"Comfort Delta : [{result.min_legend:.2f}°C to {result.max_legend:.2f}°C UTCI]")
        logger.info("==================================================")

if __name__ == "__main__":
    run_test_pipeline()