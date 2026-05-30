from pydantic import BaseModel
from typing import Optional

class Stop(BaseModel):
    lat: float
    lon: float
    label: Optional[str] = None

class RouteRequest(BaseModel):
    city: str                          # barcelona | dubai | chennai
    route_type: str                    # typical | multi | loop
    stops: list[Stop]                  # 1 for loop, 2 for typical, 2-6 for multi
    time_slot: str                     # early_morning | morning | afternoon | evening | night
    max_distance_m: float = 3000.0     # loop only
    persona_id: Optional[str] = None      # pre-seeded persona UUID
    custom_weights: Optional[dict[str, float]] = None # {w_speed, w_shade, w_nature, w_discovery}
    age_group: Optional[str] = None       # under_18 | 18_35 | 36_55 | 56_70 | 70_plus
    turn_preference: str = "mid"       # low | mid | high
    poi_query: Optional[str] = None    # natural language POI prompt, e.g. "grab coffee and post office"
