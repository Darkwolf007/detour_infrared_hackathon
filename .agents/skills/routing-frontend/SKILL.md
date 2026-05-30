# Skill: Thermal Comfort Router — React Frontend

## Stack
React 18, TypeScript, react-leaflet 4.x, TailwindCSS,
Zustand (state), React Query (polling), Nominatim (free geocoding)

## Map tiles — FREE, no API key
```
https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png
Attribution: © OpenStreetMap contributors
```

## City default centers
```typescript
const CITY_DEFAULTS = {
  barcelona: { center: [41.3874, 2.1686] as LatLngTuple, zoom: 14 },
  dubai:     { center: [25.2048, 55.2708] as LatLngTuple, zoom: 13 },
  chennai:   { center: [13.0827, 80.2707] as LatLngTuple, zoom: 13 },
}
const CITY_BBOX = {
  barcelona: '1.9,41.2,2.4,41.6',
  dubai:     '54.9,24.8,55.6,25.5',
  chennai:   '79.8,12.8,80.5,13.3',
}
```

## Layout — two panel desktop
```
┌──────────────────────────────────────────────────┐
│  Header: "ThermalRoute" + active city badge      │
├──────────────────┬───────────────────────────────┤
│  Left: 380px     │  Right: flex-1                │
│  Input form      │  Leaflet map full height      │
│  overflow-y auto │  Route as colored GeoJSON     │
└──────────────────┴───────────────────────────────┘
```

## Zustand store
```typescript
interface RouterStore {
  city: 'barcelona'|'dubai'|'chennai'|null
  ageGroup: string|null
  reason: string|null
  subReason: string|null
  personaId: string|null
  customWeights: WeightVector|null
  routeType: 'typical'|'multi'|'loop'
  stops: Stop[]                  // {id,lat,lon,label}
  timeSlot: string
  maxDistanceM: number           // loop only, default 3000
  preferences: Preferences
  activePersona: Persona|null
  isFormValid: boolean
  isLoading: boolean
  loadingStage: string|null
  jobId: string|null
  routeResult: RouteResult|null
  error: string|null
}
```

## Auto-select route type from sub-reason
```typescript
const ROUTE_DEFAULTS: Record<string, string> = {
  office:'typical', home:'typical', transit:'typical', errands:'multi',
  kid:'loop', couple:'loop', dog:'loop',
  running:'loop', walking:'loop', cycling:'loop',
  tourist:'multi', shopping:'multi', hopping:'multi',
}
```

## StopInputs rendering per route type
```
typical: exactly 2 LocationInput (start, end)
multi:   dynamic 2-6 LocationInput + AddStopButton (no auto-suggest in v1)
loop:    1 LocationInput + LoopDistanceChips [1km,2km,5km,10km,30min,60min]
```

## LocationInput — Nominatim geocoding
```typescript
const searchNominatim = async (query: string, city: string) => {
  const url = `https://nominatim.openstreetmap.org/search`
    + `?q=${encodeURIComponent(query)}&format=json&limit=4`
    + `&viewbox=${CITY_BBOX[city]}&bounded=1`
  return fetch(url, { headers: {'User-Agent':'ThermalRouter/1.0','Accept-Language':'en'} })
    .then(r => r.json())
}
// Debounce 400ms. Max 1 req/sec (Nominatim policy).
```

## Map click → set stop
```typescript
// MapClickHandler listens for map clicks when activeInputIndex !== null
// On click: reverse geocode via Nominatim → fill LocationInput
// Cursor shows crosshair when map-click mode active
```

## Route coloring by UTCI score
```typescript
const utciColor = (score: number) => {
  if (score < 0.3) return '#22c55e'   // green — comfortable
  if (score < 0.6) return '#f59e0b'   // amber — moderate
  if (score < 0.8) return '#ef4444'   // red — hot
  return '#7c3aed'                     // purple — extreme
}
// Render edge_scores from API as individual Polyline components
// weight=5, opacity=0.85, tooltip shows raw UTCI °C on hover
```

## Loading overlay messages (sequence)
```typescript
const STAGES = [
  { ms: 0,    text: 'Fetching street network...' },
  { ms: 1500, text: 'Connecting to weather data...' },
  { ms: 3000, text: 'Simulating microclimate...' },
  { ms: 7000, text: 'Finding your ideal route...' },
]
```

## React Query polling
```typescript
useQuery({
  queryKey: ['route-status', jobId],
  queryFn:  () => fetch(`/api/v1/route/status/${jobId}`).then(r=>r.json()),
  enabled:  !!jobId && isLoading,
  refetchInterval: (data) => data?.status === 'done' ? false : 2000,
})
```

## Result summary panel (below map after route)
- Total distance + estimated duration
- Comfort rating badge
- Average UTCI °C
- Gemini narrative (2 sentences)
- Three metric chips: avg shade % / avg green % / POI count on route

## City-specific warnings
```typescript
// Dubai — afternoon heat
city==='dubai' && timeSlot==='afternoon'
  → "Peak heat expected 12–4 PM. Consider early morning or evening."

// Chennai — monsoon
city==='chennai' && isMonsoon() && ['morning','afternoon'].includes(timeSlot)
  → "Monsoon season — footpaths may be wet."

// Barcelona — superblock badge on stops inside superblock boundaries
```

## Preference panel (collapsed by default)
Sliders: Speed / Shade / Nature / Discovery (0-10 each, normalised to weights)
Distance chips: 500m / 1km / 2km / 5km / No limit
Avoid chips: Busy roads / Direct sun / Stairs / Commercial streets
Shows weight bar chart (live update as sliders move)
Badge changes from "Auto from reason" to "Customised" when sliders touched
