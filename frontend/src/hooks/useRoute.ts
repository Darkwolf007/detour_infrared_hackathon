import { useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import axios from 'axios';
import { useRouterStore } from '../store/routerStore';
import type { RouteResult, RouteRequest } from '../types';

const API_BASE = 'http://localhost:8001/api/v1';

export const useRoute = () => {
  const {
    city,
    routeType,
    stops,
    timeSlot,
    maxDistanceM,
    personaId,
    customWeights,
    ageGroup,
    activePersona,
    poiQuery,
    jobId,
    isLoading,
    setJobId,
    setIsLoading,
    setLoadingStage,
    setLoadingProgress,
    setRouteResult,
    setError,
    resetRouteState
  } = useRouterStore();

  // 1. Route polling query
  const { data: pollData, error: pollError } = useQuery<RouteResult>({
    queryKey: ['route-status', jobId],
    queryFn: async () => {
      const response = await axios.get<RouteResult>(`${API_BASE}/route/status/${jobId}`);
      return response.data;
    },
    enabled: !!jobId && isLoading,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.status === 'done' || data?.status === 'error') return false;
      return 2000;
    },
  });

  // 2. Sync backend stage/progress into store while processing
  useEffect(() => {
    if (!pollData) return;

    if (pollData.status === 'processing') {
      if (pollData.stage) setLoadingStage(pollData.stage);
      if (pollData.progress != null) setLoadingProgress(pollData.progress);
    } else if (pollData.status === 'done') {
      setLoadingProgress(100);
      setRouteResult(pollData);
      setIsLoading(false);
      setJobId(null);
    } else if (pollData.status === 'error') {
      setError(pollData.error || 'Job failed on backend');
      setIsLoading(false);
      setJobId(null);
    }
  }, [pollData, setRouteResult, setIsLoading, setJobId, setError, setLoadingStage, setLoadingProgress]);

  // 3. Handle polling network errors
  useEffect(() => {
    if (pollError) {
      setError('Connection to polling service lost.');
      setIsLoading(false);
      setJobId(null);
    }
  }, [pollError, setError, setIsLoading, setJobId]);

  // 4. Mutation to initiate route request
  const submitRoute = useMutation({
    mutationFn: async () => {
      resetRouteState();
      setIsLoading(true);
      setLoadingStage('Submitting route request…');
      setLoadingProgress(0);

      const payload: RouteRequest = {
        city,
        route_type: routeType,
        stops: stops.map((s) => ({ lat: s.lat, lon: s.lon, label: s.label })),
        time_slot: timeSlot,
        max_distance_m: maxDistanceM,
        persona_id: personaId,
        custom_weights: customWeights,
        age_group: ageGroup,
        turn_preference: activePersona?.turn_preference ?? 'mid',
        poi_query: poiQuery.trim() || null,
      };

      const response = await axios.post<{ job_id: string }>(`${API_BASE}/route`, payload);
      return response.data;
    },
    onSuccess: (data) => {
      setJobId(data.job_id);
    },
    onError: (err: any) => {
      console.error(err);
      setError(err.response?.data?.detail || 'Failed to submit route request.');
      setIsLoading(false);
    }
  });

  return { submitRoute };
};
