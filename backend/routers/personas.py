import json
import logging
import os
import re
from functools import lru_cache

from google import genai
from google.genai import types
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from utils.db import get_supabase

logger = logging.getLogger("thermal_router.personas")

router = APIRouter(tags=["personas"])

VALID_CITIES = {"barcelona", "dubai", "chennai"}

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class Persona(BaseModel):
    id: str
    reason: str
    sub_reason: str
    name: str
    description: str
    icon: str | None = None
    w_speed: float
    w_shade: float
    w_nature: float
    w_discovery: float
    turn_preference: str
    turn_penalty_angle: int | None = None
    turn_penalty_weight: float | None = None
    default_route: str
    sdk_analyses: list[str] = []
    city: str | None = None
    is_default: bool = False
    is_public: bool = False
    created_by: str | None = None
    created_at: str | None = None


class CustomPersonaRequest(BaseModel):
    description: str
    city: str


# ---------------------------------------------------------------------------
# Gemini — lazy singleton
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_gemini_client() -> genai.Client:
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


_GEMINI_SYSTEM = (
    "You convert user descriptions into walking route weights. "
    "Return ONLY valid JSON. No markdown. No backticks. No explanation."
)

_GEMINI_USER = """\
User description: "{description}"
City: {city}

Return ONLY this JSON (no other text):
{{"name":"2-3 word label","w_speed":0.0,"w_shade":0.0,"w_nature":0.0,"w_discovery":0.0,\
"turn_preference":"low|mid|high","default_route":"typical|multi|loop","reasoning":"one sentence"}}

Rules:
- w_speed + w_shade + w_nature + w_discovery must sum to exactly 1.0
- turn_preference: low=straight fast, mid=balanced, high=winding exploratory
- default_route: typical=A to B, multi=multiple stops, loop=circular
- City climate context:
  dubai: weight shade heavily (UTCI often 40 C daytime)
  chennai: weight nature+shade (hot humid, tree cover matters)
  barcelona: balanced (mild climate, good infrastructure)"""

_GEMINI_FALLBACK = {
    "name": "General walker",
    "w_speed": 0.25,
    "w_shade": 0.35,
    "w_nature": 0.25,
    "w_discovery": 0.15,
    "turn_preference": "mid",
    "default_route": "typical",
    "reasoning": "Balanced weights used as fallback.",
}


def _infer_persona(description: str, city: str) -> dict:
    client = _get_gemini_client()
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=_GEMINI_USER.format(description=description, city=city),
        config=types.GenerateContentConfig(
            system_instruction=_GEMINI_SYSTEM,
            temperature=0.2,
        ),
    )
    # Strip any accidental markdown fences before parsing
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.text.strip(), flags=re.MULTILINE)
    data = json.loads(raw)

    keys = ["w_speed", "w_shade", "w_nature", "w_discovery"]
    total = sum(data[k] for k in keys)
    if abs(total - 1.0) > 0.05:
        for k in keys:
            data[k] = round(data[k] / total, 3)

    if data.get("turn_preference") not in ("low", "mid", "high"):
        data["turn_preference"] = "mid"
    if data.get("default_route") not in ("typical", "multi", "loop"):
        data["default_route"] = "typical"

    return data


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/personas", response_model=list[Persona])
def get_personas(city: str | None = Query(None, description="Filter by city slug")):
    """Return all default personas plus any public custom ones."""
    sb = get_supabase()
    query = sb.table("personas").select("*").or_("is_default.eq.true,is_public.eq.true")
    if city:
        if city not in VALID_CITIES:
            raise HTTPException(400, f"city must be one of {sorted(VALID_CITIES)}")
        # Return personas that are global (city IS NULL) or match the requested city
        query = query.or_(f"city.eq.{city},city.is.null")
    result = query.order("created_at").execute()
    return result.data


@router.post("/personas/custom")
def create_custom_persona(req: CustomPersonaRequest):
    """Infer routing weights from a free-text description via Gemini."""
    if req.city not in VALID_CITIES:
        raise HTTPException(400, f"city must be one of {sorted(VALID_CITIES)}")
    if not req.description.strip():
        raise HTTPException(400, "description cannot be empty")

    try:
        persona = _infer_persona(req.description.strip(), req.city)
    except Exception:
        logger.exception("Gemini inference failed — returning fallback persona")
        persona = _GEMINI_FALLBACK.copy()

    return {"inferred_persona": persona}
