export interface Stop {
  id: string;
  lat: number;
  lon: number;
  label?: string;
}

export interface WeightVector {
  w_speed: number;
  w_shade: number;
  w_nature: number;
  w_discovery: number;
}

export interface Persona {
  id: string;
  reason: string;
  sub_reason: string;
  name: string;
  description: string;
  icon?: string;
  w_speed: number;
  w_shade: number;
  w_nature: number;
  w_discovery: number;
  turn_preference: string;
  turn_penalty_angle?: number;
  turn_penalty_weight?: number;
  default_route: string;
  sdk_analyses: string[];
  city?: string;
  is_default: boolean;
  is_public: boolean;
}

export interface EdgeScore {
  coordinates: [number, number][]; // Array of [lon, lat] pairs
  utci_score: number;
  raw_utci: number;
  wind_score: number;
  shade_score: number;
  veg_score: number;
}

export interface RouteSummary {
  distance_m: number;
  duration_min: number;
  avg_utci: number;
  avg_shade: number;
  comfort_rating: 'comfortable' | 'moderate' | 'hot' | 'extreme';
  shade_pct: number;
  nature_pct: number;
  poi_count: number;
}

export interface RouteRequest {
  city: 'barcelona' | 'dubai' | 'chennai';
  route_type: 'typical' | 'multi' | 'loop';
  stops: { lat: number; lon: number; label?: string }[];
  time_slot: string;
  max_distance_m: number;
  persona_id?: string | null;
  custom_weights?: WeightVector | null;
  age_group?: string | null;
  turn_preference: string;
  poi_query?: string | null;
}

export interface PoiWaypoint {
  lat: number;
  lon: number;
  name: string;
  poi_type: string;
  emoji: string;
}

export interface RouteResult {
  status: 'processing' | 'done' | 'error';
  job_id: string;
  stage?: string;
  progress?: number;
  route_geojson?: { type: 'LineString'; coordinates: [number, number][] } | null;
  edge_scores: EdgeScore[];
  summary?: RouteSummary | null;
  narrative?: string | null;
  is_unscored: boolean;
  error?: string | null;
  network_geojson?: { type: string; features: any[] } | null;
  // Analysis layer overlays
  utci_image?: string | null;
  utci_bounds?: [[number, number], [number, number]] | null;
  wind_image?: string | null;
  wind_bounds?: [[number, number], [number, number]] | null;
  solar_image?: string | null;
  solar_bounds?: [[number, number], [number, number]] | null;
  // POI waypoints resolved from the prompt
  poi_waypoints?: PoiWaypoint[];
}
