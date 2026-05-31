# ── Stage 1: Build dependencies ──────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

# OS-level libs needed to compile native Python wheels (shapely, numpy, scipy …)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgdal-dev \
        libgeos-dev \
        libproj-dev \
    && rm -rf /var/lib/apt/lists/*

ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Slim runtime image ──────────────────────────────────────────────
FROM python:3.11-slim-bookworm

# Runtime C libs (GDAL, GEOS, PROJ) — needed by shapely, geopandas at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgdal32 \
        libgeos-c1v5 \
        libproj25 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN useradd -m -s /bin/bash appuser

WORKDIR /app

# Copy pre-built Python packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Create the _osm_cache directory (graphml files synced from R2 at startup)
RUN mkdir -p /app/_osm_cache && chown -R appuser:appuser /app

USER appuser

# Render injects PORT env var; default to 7860
ENV PORT=7860
EXPOSE ${PORT}

# Health check — start-period is long to allow R2 graphml sync + preload
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Start the FastAPI server
# --timeout-keep-alive 65  → survive Render's 60s proxy keep-alive
# --workers 1              → graphml preload is ~2 GB per worker
CMD uvicorn main:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --timeout-keep-alive 65 \
    --workers 1
