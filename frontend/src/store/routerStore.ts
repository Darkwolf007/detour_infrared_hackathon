import { create } from 'zustand';
import type { Stop, WeightVector, Persona, RouteResult } from '../types';
import { CITY_CONFIGS } from '../utils/cityConfig';

export const ROUTE_DEFAULTS: Record<string, 'typical' | 'multi' | 'loop'> = {
  office: 'typical',
  home: 'typical',
  transit: 'typical',
  errands: 'multi',
  kid: 'loop',
  couple: 'loop',
  dog: 'loop',
  running: 'loop',
  walking: 'loop',
  cycling: 'loop',
  tourist: 'multi',
  shopping: 'multi',
  hopping: 'multi',
};

interface RouterState {
  city: 'barcelona' | 'dubai' | 'chennai';
  ageGroup: string;
  reason: string;
  subReason: string;
  personaId: string | null;
  customWeights: WeightVector | null;
  routeType: 'typical' | 'multi' | 'loop';
  stops: Stop[];
  timeSlot: string;
  maxDistanceM: number;
  activePersona: Persona | null;
  activeStopIndex: number | null;   // which stop is armed for map-click picking
  poiQuery: string;
  isLoading: boolean;
  loadingStage: string | null;
  loadingProgress: number | null;
  jobId: string | null;
  routeResult: RouteResult | null;
  error: string | null;

  // Actions
  setCity: (city: 'barcelona' | 'dubai' | 'chennai') => void;
  setAgeGroup: (ageGroup: string) => void;
  setReason: (reason: string) => void;
  setSubReason: (subReason: string) => void;
  setPersonaId: (id: string | null) => void;
  setRouteType: (type: 'typical' | 'multi' | 'loop') => void;
  setStops: (stops: Stop[]) => void;
  updateStop: (index: number, stop: Partial<Stop>) => void;
  addStop: () => void;
  removeStop: (index: number) => void;
  setTimeSlot: (slot: string) => void;
  setMaxDistanceM: (dist: number) => void;
  setCustomWeights: (weights: WeightVector | null) => void;
  setActivePersona: (persona: Persona | null) => void;
  setActiveStopIndex: (index: number | null) => void;
  setPoiQuery: (q: string) => void;
  setIsLoading: (isLoading: boolean) => void;
  setLoadingStage: (stage: string | null) => void;
  setLoadingProgress: (progress: number | null) => void;
  setJobId: (id: string | null) => void;
  setRouteResult: (result: RouteResult | null) => void;
  setError: (err: string | null) => void;
  resetRouteState: () => void;
}

export const useRouterStore = create<RouterState>((set) => ({
  city: 'barcelona',
  ageGroup: '18_35',
  reason: 'commute',
  subReason: 'office',
  personaId: null,
  customWeights: null,
  routeType: 'typical',
  stops: [
    { id: '1', lat: 41.3874, lon: 2.1686, label: 'Placa de Catalunya, Barcelona' },
    { id: '2', lat: 41.3891, lon: 2.1764, label: 'Arc de Triomf, Barcelona' }
  ],
  timeSlot: 'morning',
  maxDistanceM: 3000,
  activePersona: null,
  activeStopIndex: null,
  poiQuery: '',
  isLoading: false,
  loadingStage: null,
  loadingProgress: null,
  jobId: null,
  routeResult: null,
  error: null,

  setCity: (city) => set((state) => {
    const config = CITY_CONFIGS[city];
    const centerStop: Stop = {
      id: '1',
      lat: config.center[0],
      lon: config.center[1],
      label: `Center of ${config.name}`
    };

    let newStops: Stop[] = [];
    if (state.routeType === 'typical') {
      newStops = [
        { ...centerStop, id: '1', label: `Start Stop (${config.name})` },
        { id: '2', lat: config.center[0] + 0.005, lon: config.center[1] + 0.005, label: `End Stop (${config.name})` }
      ];
    } else if (state.routeType === 'multi') {
      newStops = [
        { ...centerStop, id: '1', label: `Stop 1 (${config.name})` },
        { id: '2', lat: config.center[0] + 0.005, lon: config.center[1] + 0.005, label: `Stop 2 (${config.name})` }
      ];
    } else {
      newStops = [
        { ...centerStop, id: '1', label: `Start Location (${config.name})` }
      ];
    }

    return { city, stops: newStops, routeResult: null, error: null };
  }),

  setAgeGroup: (ageGroup) => set({ ageGroup }),
  
  setReason: (reason) => set({ reason }),

  setSubReason: (subReason) => set((state) => {
    const defaultRoute = ROUTE_DEFAULTS[subReason] || 'typical';
    
    // Automatically switch route type & adapt stops
    const config = CITY_CONFIGS[state.city];
    let newStops = [...state.stops];
    
    if (defaultRoute === 'loop') {
      newStops = [{ id: '1', lat: config.center[0], lon: config.center[1], label: `Start Location (${config.name})` }];
    } else if (state.routeType === 'loop') {
      // Switched from loop to типиcal or multi
      newStops = [
        { id: '1', lat: config.center[0], lon: config.center[1], label: `Start Stop (${config.name})` },
        { id: '2', lat: config.center[0] + 0.005, lon: config.center[1] + 0.005, label: `End Stop (${config.name})` }
      ];
    }
    
    return { 
      subReason, 
      routeType: defaultRoute, 
      stops: newStops,
      routeResult: null,
      error: null
    };
  }),

  setPersonaId: (personaId) => set({ personaId }),

  setRouteType: (routeType) => set((state) => {
    const config = CITY_CONFIGS[state.city];
    let newStops: Stop[] = [];
    
    if (routeType === 'loop') {
      newStops = [
        { id: '1', lat: config.center[0], lon: config.center[1], label: `Start Location (${config.name})` }
      ];
    } else {
      newStops = [
        { id: '1', lat: config.center[0], lon: config.center[1], label: `Start Stop (${config.name})` },
        { id: '2', lat: config.center[0] + 0.005, lon: config.center[1] + 0.005, label: `End Stop (${config.name})` }
      ];
    }
    
    return { routeType, stops: newStops, routeResult: null, error: null };
  }),

  setStops: (stops) => set({ stops }),

  updateStop: (index, stopUpdate) => set((state) => {
    const newStops = [...state.stops];
    newStops[index] = { ...newStops[index], ...stopUpdate };
    return { stops: newStops };
  }),

  addStop: () => set((state) => {
    if (state.stops.length >= 6) return {}; // limit to 6 stops
    const lastStop = state.stops[state.stops.length - 1];
    const newStop: Stop = {
      id: String(Date.now()),
      lat: lastStop.lat + 0.002,
      lon: lastStop.lon + 0.002,
      label: `Stop ${state.stops.length + 1}`
    };
    return { stops: [...state.stops, newStop] };
  }),

  removeStop: (index) => set((state) => {
    if (state.stops.length <= 2) return {}; // keep at least 2 stops
    const newStops = state.stops.filter((_, i) => i !== index);
    return { stops: newStops };
  }),

  setTimeSlot: (timeSlot) => set({ timeSlot }),

  setMaxDistanceM: (maxDistanceM) => set({ maxDistanceM }),

  setCustomWeights: (customWeights) => set({ customWeights }),

  setActivePersona: (activePersona) => set({ activePersona }),

  setActiveStopIndex: (activeStopIndex) => set({ activeStopIndex }),

  setPoiQuery: (poiQuery) => set({ poiQuery }),

  setIsLoading: (isLoading) => set({ isLoading }),

  setLoadingStage: (loadingStage) => set({ loadingStage }),

  setLoadingProgress: (loadingProgress) => set({ loadingProgress }),

  setJobId: (jobId) => set({ jobId }),

  setRouteResult: (routeResult) => set({ routeResult }),

  setError: (error) => set({ error }),

  resetRouteState: () => set({
    isLoading: false,
    loadingStage: null,
    loadingProgress: null,
    jobId: null,
    routeResult: null,
    error: null
  })
}));
