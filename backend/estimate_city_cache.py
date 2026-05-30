"""
Estimate the cost and tile count for pre-caching thermal comfort analyses
for entire cities: Barcelona, Dubai, Chennai.

Run with:  python estimate_city_cache.py
Does NOT trigger any actual analysis — uses preview_area() only.
"""

import os
from dotenv import load_dotenv
from infrared_sdk import InfraredClient

load_dotenv()

# Your remaining credit budget — update this before running
CREDITS_REMAINING = 7_700

# ---------------------------------------------------------------------------
# City bounding boxes
# ---------------------------------------------------------------------------
CITIES = {
    "Barcelona": {
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [2.069,  41.320],
                [2.228,  41.320],
                [2.228,  41.470],
                [2.069,  41.470],
                [2.069,  41.320],
            ]],
        },
        "description": "~17 km × 17 km urban core",
    },
    "Dubai": {
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [55.130, 24.990],
                [55.450, 24.990],
                [55.450, 25.350],
                [55.130, 25.350],
                [55.130, 24.990],
            ]],
        },
        "description": "~35 km × 40 km urban area",
    },
    "Chennai": {
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [80.170, 12.900],
                [80.330, 12.900],
                [80.330, 13.200],
                [80.170, 13.200],
                [80.170, 12.900],
            ]],
        },
        "description": "~18 km × 33 km urban area",
    },
}

# Analysis types to preview.
# Solar / UTCI use 512 m grid (edge-to-edge).
# Wind uses 256 m grid with 50% overlap — costs ~4x more tiles for same area.
ANALYSIS_TYPES = [
    "solar-radiation",
    "thermal-comfort",
    "wind-speed",
]

# Dubai wind alone needs ~20k tiles; set high enough to not re-throw
MAX_TILES = 25_000

# ---------------------------------------------------------------------------

def fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"


def main():
    api_key = os.environ.get("INFRARED_API_KEY")
    if not api_key:
        raise SystemExit("INFRARED_API_KEY not set in environment / .env file.")

    grand_tokens = 0
    grand_time_s = 0.0
    rows = []  # (city, analysis_type, tiles, time_s, tokens)

    with InfraredClient(api_key=api_key) as client:
        for city_name, city in CITIES.items():
            print(f"\n{'=' * 65}")
            print(f"  {city_name}  ({city['description']})")
            print(f"{'=' * 65}")

            city_tokens = 0
            city_time_s = 0.0

            for analysis_type in ANALYSIS_TYPES:
                try:
                    preview = client.preview_area(
                        city["polygon"],
                        analysis_type=analysis_type,
                        max_tiles_override=MAX_TILES,
                    )
                    tiles  = preview.tile_count
                    time_s = preview.estimated_time_s
                    tokens = preview.estimated_cost_tokens
                except Exception as e:
                    print(f"  {analysis_type:<22}  ERROR: {e}")
                    continue

                city_tokens += tokens
                city_time_s += time_s
                rows.append((city_name, analysis_type, tiles, time_s, tokens))

                print(
                    f"  {analysis_type:<22}  "
                    f"tiles={tiles:>6,}  "
                    f"time={fmt_time(time_s):>12}  "
                    f"tokens={tokens:>9,}"
                )

            print(
                f"  {'— city total —':<22}  "
                f"{'':>14}"
                f"time={fmt_time(city_time_s):>12}  "
                f"tokens={city_tokens:>9,}"
            )
            grand_tokens += city_tokens
            grand_time_s += city_time_s

    # ---------------------------------------------------------------------------
    # Summary and budget analysis
    # ---------------------------------------------------------------------------
    print(f"\n{'=' * 65}")
    print(f"  GRAND TOTAL — all 3 cities, all 3 analysis types")
    print(f"  Estimated wall-clock time : {fmt_time(grand_time_s)}")
    print(f"  Estimated tokens          : {grand_tokens:,}")
    print(f"{'=' * 65}")

    print(f"\n{'=' * 65}")
    print(f"  BUDGET CHECK  (remaining: {CREDITS_REMAINING:,} credits)")
    print(f"{'=' * 65}")

    # Rank cheapest options first
    rows_sorted = sorted(rows, key=lambda r: r[4])
    cumulative = 0
    print(f"  {'Priority':<4}  {'City':<12} {'Analysis':<22} {'tokens':>9}  {'cum. total':>10}  fits?")
    print(f"  {'-'*4}  {'-'*12} {'-'*22} {'-'*9}  {'-'*10}  {'-'*5}")
    for i, (city_name, atype, tiles, time_s, tokens) in enumerate(rows_sorted, 1):
        cumulative += tokens
        fits = "YES" if cumulative <= CREDITS_REMAINING else "NO "
        print(f"  {i:<4}  {city_name:<12} {atype:<22} {tokens:>9,}  {cumulative:>10,}  {fits}")

    print()
    affordable = [r for r in rows_sorted if r[4] <= CREDITS_REMAINING]
    if grand_tokens <= CREDITS_REMAINING:
        print("  VERDICT: Full city cache fits within your remaining budget.")
    else:
        print(f"  VERDICT: Full cache needs {grand_tokens:,} tokens — exceeds budget by {grand_tokens - CREDITS_REMAINING:,}.")
        print()
        print("  RECOMMENDATION — skip wind-speed for the large cities (it costs")
        print("  ~4x more tiles than solar/thermal for the same area).  Cache only")
        print("  solar-radiation + thermal-comfort for all 3 cities and use OSM")
        print("  as a wind proxy, or cache wind only for the smallest city.")
        no_wind_total = sum(r[4] for r in rows if r[1] != "wind-speed")
        print(f"\n  solar + thermal only (no wind): {no_wind_total:,} tokens")
        utci_only = sum(r[4] for r in rows if r[1] == "thermal-comfort")
        print(f"  thermal-comfort only           : {utci_only:,} tokens")

    print()


if __name__ == "__main__":
    main()
