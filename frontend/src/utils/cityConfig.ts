import type { LatLngTuple } from 'leaflet';

export interface CityInfo {
  name: string;
  slug: 'barcelona' | 'dubai' | 'chennai';
  center: LatLngTuple;
  zoom: number;
  bbox: string; // Used by Nominatim for bounding results: 'west,south,east,north'
  warning?: string;
}

export const CITY_CONFIGS: Record<'barcelona' | 'dubai' | 'chennai', CityInfo> = {
  barcelona: {
    name: 'Barcelona',
    slug: 'barcelona',
    center: [41.3874, 2.1686] as LatLngTuple,
    zoom: 14,
    bbox: '1.9,41.2,2.4,41.6',
  },
  dubai: {
    name: 'Dubai',
    slug: 'dubai',
    center: [25.2048, 55.2708] as LatLngTuple,
    zoom: 13,
    bbox: '54.9,24.8,55.6,25.5',
  },
  chennai: {
    name: 'Chennai',
    slug: 'chennai',
    center: [13.0827, 80.2707] as LatLngTuple,
    zoom: 13,
    bbox: '79.8,12.8,80.5,13.3',
  }
};
