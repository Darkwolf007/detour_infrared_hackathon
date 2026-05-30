import { useState, useEffect } from 'react';
import axios from 'axios';
import { CITY_CONFIGS } from '../utils/cityConfig';

export interface GeocodingResult {
  place_id: number;
  licence: string;
  osm_type: string;
  osm_id: number;
  boundingbox: string[];
  lat: string;
  lon: string;
  display_name: string;
  class: string;
  type: string;
  importance: number;
}

export const useNominatim = (query: string, citySlug: 'barcelona' | 'dubai' | 'chennai') => {
  const [suggestions, setSuggestions] = useState<GeocodingResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  useEffect(() => {
    if (!query || query.trim().length < 3) {
      setSuggestions([]);
      return;
    }

    const cityConfig = CITY_CONFIGS[citySlug];
    const delayDebounceFn = setTimeout(async () => {
      setIsSearching(true);
      try {
        const url = `https://nominatim.openstreetmap.org/search`;
        const response = await axios.get<GeocodingResult[]>(url, {
          params: {
            q: query,
            format: 'json',
            limit: 4,
            viewbox: cityConfig.bbox,
            bounded: 1,
            'accept-language': 'en'
          }
        });
        setSuggestions(response.data);
      } catch (error) {
        console.error('Nominatim search failed:', error);
      } finally {
        setIsSearching(false);
      }
    }, 400); // 400ms debounce

    return () => clearTimeout(delayDebounceFn);
  }, [query, citySlug]);

  return { suggestions, isSearching };
};
