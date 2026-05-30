import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Sidebar } from './components/Sidebar';
import { MapPanel } from './components/MapPanel';
import { ResultSummary } from './components/ResultSummary';
import { LoadingOverlay } from './components/LoadingOverlay';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: false,
    },
  },
});

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="flex w-full h-full overflow-hidden">
        <Sidebar />
        <div className="flex-1 relative overflow-hidden">
          <MapPanel />
          <LoadingOverlay />
          <ResultSummary />
        </div>
      </div>
    </QueryClientProvider>
  );
};

export default App;
