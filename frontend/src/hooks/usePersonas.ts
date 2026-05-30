import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import type { Persona } from '../types';

const API_BASE = 'http://localhost:8001/api/v1';

export const usePersonas = (citySlug: string) => {
  return useQuery<Persona[]>({
    queryKey: ['personas', citySlug],
    queryFn: async () => {
      const response = await axios.get<Persona[]>(`${API_BASE}/personas`, {
        params: { city: citySlug }
      });
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // Cache for 5 mins
  });
};
