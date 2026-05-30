import React from 'react';
import { useRouterStore } from '../store/routerStore';

export const LoadingOverlay: React.FC = () => {
  const { isLoading, loadingStage, loadingProgress } = useRouterStore();
  if (!isLoading) return null;

  const pct = loadingProgress ?? 0;

  return (
    <div
      className="absolute bottom-5 right-4 z-[9999] w-64 animate-fade-in pointer-events-none"
      style={{ fontFamily: "'Space Grotesk', 'Inter', sans-serif" }}
    >
      <div
        style={{
          background: '#F4F4F0',
          border: '2.5px solid #000',
          boxShadow: '4px 4px 0 #000',
        }}
      >
        {/* ── Header ── */}
        <div
          className="flex items-center gap-2 px-3 py-2"
          style={{ borderBottom: '2px solid #000', background: '#fff' }}
        >
          {/* Pulsing dot */}
          <span
            className="shrink-0 pulse-marker-active"
            style={{
              display: 'inline-block',
              width: 8, height: 8,
              background: '#E3411E',
              border: '1.5px solid #000',
              boxShadow: '1px 1px 0 #000',
            }}
          />
          <span
            style={{
              fontSize: 9, fontWeight: 900,
              textTransform: 'uppercase',
              letterSpacing: '0.16em',
              color: '#000',
              flex: 1,
            }}
          >
            Building Route
          </span>
          <span
            style={{
              fontSize: 11, fontWeight: 900,
              color: '#000',
              background: pct > 0 ? '#FFE600' : 'transparent',
              border: pct > 0 ? '1.5px solid #000' : '1.5px solid #ccc',
              padding: '1px 5px',
              letterSpacing: '0.04em',
            }}
          >
            {pct}%
          </span>
        </div>

        {/* ── Progress bar ── */}
        <div className="px-3 py-2.5" style={{ borderBottom: '2px solid #000', background: '#F4F4F0' }}>
          <div
            style={{
              height: 10,
              background: '#fff',
              border: '2px solid #000',
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                position: 'absolute', top: 0, left: 0,
                width: `${pct}%`, height: '100%',
                background: '#FFE600',
                borderRight: pct < 100 ? '2px solid #000' : 'none',
                transition: 'width 0.5s ease-out',
              }}
            />
            {/* tick marks */}
            {[25, 50, 75].map(t => (
              <div
                key={t}
                style={{
                  position: 'absolute', top: 0, left: `${t}%`,
                  width: 1, height: '100%',
                  background: pct > t ? '#c8a800' : '#ddd',
                }}
              />
            ))}
          </div>
        </div>

        {/* ── Stage text ── */}
        <div className="px-3 py-2" style={{ background: '#F4F4F0' }}>
          <p
            style={{
              fontSize: 10, fontWeight: 700,
              color: '#000',
              letterSpacing: '0.01em',
              minHeight: 14,
              textOverflow: 'ellipsis',
              overflow: 'hidden',
              whiteSpace: 'nowrap',
            }}
          >
            {loadingStage || 'Initialising…'}
          </p>
          {pct < 15 && (
            <p
              style={{
                fontSize: 8, fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.12em',
                color: '#888',
                marginTop: 4,
              }}
            >
              First run: 2–4 min · cached: instant
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default LoadingOverlay;
