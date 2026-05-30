from pydantic import BaseModel
from typing import Optional

class EdgeScore(BaseModel):
    coordinates: list[list[float]]     # [[lon,lat], ...] for this edge segment
    utci_score: float
    raw_utci: float
    wind_score: float
    shade_score: float
    veg_score: float

class RouteSummary(BaseModel):
    distance_m: float
    duration_min: float
    avg_utci: float
    avg_shade: float
    comfort_rating: str                # comfortable | moderate | hot | extreme
    shade_pct: float
    nature_pct: float
    poi_count: int

class PoiWaypoint(BaseModel):
    lat: float
    lon: float
    name: str
    poi_type: str
    emoji: str

class RouteResult(BaseModel):
    status: str                        # processing | done | error
    job_id: str
    stage: Optional[str] = None
    progress: Optional[int] = None
    route_geojson: Optional[dict] = None
    edge_scores: list[EdgeScore] = []
    summary: Optional[RouteSummary] = None
    narrative: Optional[str] = None
    is_unscored: bool = False
    error: Optional[str] = None
    # Street network overlay
    network_geojson: Optional[dict] = None
    # UTCI thermal comfort layer
    utci_image: Optional[str] = None
    utci_bounds: Optional[list] = None       # [[minLat, minLon], [maxLat, maxLon]]
    # Wind speed layer
    wind_image: Optional[str] = None
    wind_bounds: Optional[list] = None
    # Solar radiation layer
    solar_image: Optional[str] = None
    solar_bounds: Optional[list] = None
    # POI waypoints resolved from the prompt
    poi_waypoints: list[PoiWaypoint] = []
