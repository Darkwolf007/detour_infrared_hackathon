import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
logger = logging.getLogger("thermal_router")

from routers import cache, personas, route
from utils.graphml_sync import sync_graphml


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ThermalRoute API starting — syncing graphml from R2 …")
    sync_graphml()
    logger.info("ThermalRoute API ready")
    yield
    logger.info("ThermalRoute API shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ThermalRoute API",
        description="Thermal comfort pedestrian routing — Barcelona, Dubai, Chennai",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS: comma-separated origins from env, defaults to local dev + placeholder Vercel URL
    raw_origins = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:5174,https://thermal-route.vercel.app",
    )
    cors_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(personas.router, prefix="/api/v1")
    app.include_router(route.router, prefix="/api/v1")
    app.include_router(cache.router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "service": "thermal-route-api", "version": "0.1.0"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
