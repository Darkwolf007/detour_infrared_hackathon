# ---------------------------------------------------------------------------
# Grid value normalisation — raw SDK float → 0–1 score
# ---------------------------------------------------------------------------

def normalise_utci(raw: float) -> float:
    """26°C = comfortable, 46°C = extreme stress → 0–1. Higher = hotter = worse."""
    return max(0.0, min(1.0, (raw - 26.0) / 20.0))


def normalise_lawson(raw: float) -> float:
    """Lawson pedestrian wind comfort class 0–5 → 0–1. Higher = windier = worse."""
    return max(0.0, min(1.0, raw / 5.0))


def normalise_solar(raw: float) -> float:
    """Direct sun hours 0–8 h → 0–1. Higher = more exposed = worse for shade."""
    return max(0.0, min(1.0, raw / 8.0))


def combined_shade(solar_norm: float, svf_norm: float = 0.5) -> float:
    """
    Composite shade score where higher = more shaded = better.
      solar_norm : from normalise_solar  (0=shaded, 1=fully exposed)
      svf_norm   : sky-view factor norm  (0=deep canyon, 1=open sky)
                   defaults to 0.5 when SVF grid is not available.
    """
    return 0.6 * (1.0 - solar_norm) + 0.4 * (1.0 - svf_norm)


# ---------------------------------------------------------------------------
# Edge attribute lookup tables
# ---------------------------------------------------------------------------

# Penalty for surface roughness/discomfort (higher = worse for walkers)
SURFACE_PENALTY: dict[str | None, float] = {
    "asphalt":       0.00,
    "paving_stones": 0.05,
    "concrete":      0.05,
    "sett":          0.15,
    "compacted":     0.20,
    "gravel":        0.40,
    "dirt":          0.50,
    "sand":          0.90,
    None:            0.10,   # unknown surface
}

# Penalty for sharing road with fast/heavy traffic (higher = less safe)
HIGHWAY_SAFETY: dict[str | None, float] = {
    "footway":       0.00,
    "path":          0.05,
    "pedestrian":    0.00,
    "living_street": 0.05,
    "residential":   0.10,
    "cycleway":      0.05,
    "tertiary":      0.30,
    "secondary":     0.50,
    "primary":       0.70,
    "trunk":         0.90,
    None:            0.20,   # unknown highway type
}

# ---------------------------------------------------------------------------
# Persona weight adjustments
# ---------------------------------------------------------------------------

# Additional shade weight to add based on user's age group.
# Subtracted equally from w_speed and w_discovery, then renormalised.
AGE_SHADE_BOOST: dict[str, float] = {
    "under_18": 0.00,
    "18_35":    0.00,
    "36_55":    0.05,
    "56_70":    0.15,
    "70_plus":  0.25,
}


def apply_age_boost(weights: dict, age_group: str | None) -> dict:
    """Boost w_shade by the age-group amount and renormalise all weights."""
    if not age_group:
        return weights
    boost = AGE_SHADE_BOOST.get(age_group, 0.0)
    if boost == 0.0:
        return weights

    w = weights.copy()
    w["w_shade"] = min(1.0, w["w_shade"] + boost)
    reduction = boost / 2.0
    w["w_speed"]     = max(0.0, w["w_speed"]     - reduction)
    w["w_discovery"] = max(0.0, w["w_discovery"] - reduction)
    return normalise_weights(
        w["w_speed"], w["w_shade"], w["w_nature"], w["w_discovery"]
    )


def normalise_weights(
    speed: float,
    shade: float,
    nature: float,
    discovery: float,
) -> dict:
    """Renormalise four weights so they sum to exactly 1.0."""
    total = speed + shade + nature + discovery
    if total == 0.0:
        total = 1.0
    return {
        "w_speed":     round(speed     / total, 4),
        "w_shade":     round(shade     / total, 4),
        "w_nature":    round(nature    / total, 4),
        "w_discovery": round(discovery / total, 4),
    }
