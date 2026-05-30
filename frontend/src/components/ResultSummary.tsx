import React from 'react';
import { Navigation, Clock, Thermometer, TreePine, MapPin, Zap } from 'lucide-react';
import { useRouterStore } from '../store/routerStore';
import { utciColor } from '../utils/utciColor';

// ── UTCI → neo-brutalist comfort label + accent color ──────────────────────

function comfortStyle(normScore: number): { label: string; bg: string; color: string } {
  if (normScore < 0.3)  return { label: 'COMFORTABLE', bg: '#d1fae5', color: '#000' };
  if (normScore < 0.6)  return { label: 'MODERATE',    bg: '#fef3c7', color: '#000' };
  if (normScore < 0.8)  return { label: 'HOT',         bg: '#FFE600', color: '#000' };
  return                       { label: 'EXTREME',      bg: '#fecaca', color: '#000' };
}

// ── Stat cell ──────────────────────────────────────────────────────────────

const StatCell: React.FC<{
  label: string;
  value: string;
  sub?: string;
  accent?: string;
  icon?: React.ElementType;
  last?: boolean;
}> = ({ label, value, sub, accent, icon: Icon, last = false }) => (
  <div
    className="flex flex-col justify-center px-4 py-3 shrink-0"
    style={{ borderRight: last ? 'none' : '2px solid #000', minWidth: 80 }}
  >
    <div
      style={{
        fontSize: 8, fontWeight: 900,
        textTransform: 'uppercase',
        letterSpacing: '0.14em',
        color: '#888',
        display: 'flex', alignItems: 'center', gap: 3,
        marginBottom: 3,
      }}
    >
      {Icon && <Icon size={9} />}
      {label}
    </div>
    <div
      style={{
        fontSize: 15, fontWeight: 900,
        letterSpacing: '-0.02em',
        color: accent ?? '#000',
        lineHeight: 1.1,
      }}
    >
      {value}
    </div>
    {sub && (
      <div style={{ fontSize: 8, color: '#888', fontWeight: 600, marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {sub}
      </div>
    )}
  </div>
);

// ── Tag chip ───────────────────────────────────────────────────────────────

const Tag: React.FC<{ label: string; dot?: string }> = ({ label, dot }) => (
  <span
    className="inline-flex items-center gap-1.5 shrink-0"
    style={{
      fontSize: 9, fontWeight: 900,
      textTransform: 'uppercase',
      letterSpacing: '0.10em',
      color: '#000',
      background: '#fff',
      border: '1.5px solid #000',
      boxShadow: '1.5px 1.5px 0 #000',
      padding: '3px 7px',
    }}
  >
    {dot && <span style={{ width: 7, height: 7, borderRadius: '50%', background: dot, border: '1px solid #000', flexShrink: 0 }} />}
    {label}
  </span>
);

// ── component ──────────────────────────────────────────────────────────────

export const ResultSummary: React.FC = () => {
  const { routeResult } = useRouterStore();
  if (!routeResult || routeResult.status !== 'done' || !routeResult.summary) return null;

  const { summary, is_unscored, poi_waypoints } = routeResult;
  const normScore = Math.max(0, Math.min(1, (summary.avg_utci - 26) / 20));
  const cs = comfortStyle(normScore);
  const poiCount = poi_waypoints?.length ?? summary.poi_count;

  return (
    <div
      className="absolute bottom-4 z-[1000] animate-fade-in"
      style={{
        left: 16, right: 16,
        fontFamily: "'Space Grotesk', 'Inter', sans-serif",
      }}
    >
      <div
        style={{
          background: '#F4F4F0',
          border: '2.5px solid #000',
          boxShadow: '4px 4px 0 #000',
          display: 'flex',
          alignItems: 'stretch',
          overflow: 'hidden',
        }}
      >
        {/* ── Colour band: comfort rating ── */}
        <div
          style={{
            width: 6,
            background: utciColor(normScore),
            flexShrink: 0,
          }}
        />

        {/* ── Stats row ── */}
        <StatCell icon={Navigation} label="Distance" value={`${(summary.distance_m / 1000).toFixed(2)} km`} />
        <StatCell icon={Clock}      label="Walk time" value={`${Math.round(summary.duration_min)} min`} />
        <StatCell icon={Thermometer} label="Feels like" value={`${summary.avg_utci.toFixed(1)}°C`} />

        {/* Comfort badge cell */}
        <div
          className="flex flex-col justify-center px-3 py-2 shrink-0"
          style={{ borderRight: '2px solid #000' }}
        >
          <div style={{ fontSize: 8, fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.14em', color: '#888', marginBottom: 3 }}>
            Comfort
          </div>
          <div
            style={{
              fontSize: 10, fontWeight: 900,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              background: cs.bg,
              color: cs.color,
              border: '2px solid #000',
              boxShadow: '2px 2px 0 #000',
              padding: '3px 8px',
              whiteSpace: 'nowrap',
            }}
          >
            {cs.label}
          </div>
        </div>

        {/* ── Tags ── */}
        <div
          className="flex items-center gap-2 px-4 flex-1 min-w-0 overflow-x-auto"
          style={{ borderRight: '2px solid #000' }}
        >
          <Tag dot="#f59e0b" label={`Shade ${Math.round(summary.shade_pct)}%`} />
          <Tag dot="#10b981" label={`Green ${Math.round(summary.nature_pct)}%`} />
          {poiCount > 0 && <Tag dot="#6366f1" label={`${poiCount} POI${poiCount !== 1 ? 's' : ''}`} />}
          {(poi_waypoints ?? []).map((p, i) => (
            <Tag key={i} dot="#FFE600" label={`${p.emoji} ${p.name}`} />
          ))}
        </div>

        {/* ── Badge ── */}
        <div className="flex items-center px-4 shrink-0">
          {is_unscored ? (
            <div
              style={{
                fontSize: 9, fontWeight: 900,
                textTransform: 'uppercase',
                letterSpacing: '0.10em',
                background: '#fecaca',
                color: '#000',
                border: '2px solid #000',
                boxShadow: '2px 2px 0 #000',
                padding: '4px 8px',
                display: 'flex', alignItems: 'center', gap: 5,
              }}
            >
              <MapPin size={10} /> OSM Fallback
            </div>
          ) : (
            <div
              style={{
                fontSize: 9, fontWeight: 900,
                textTransform: 'uppercase',
                letterSpacing: '0.10em',
                background: '#FFE600',
                color: '#000',
                border: '2px solid #000',
                boxShadow: '2px 2px 0 #000',
                padding: '4px 8px',
                display: 'flex', alignItems: 'center', gap: 5,
              }}
            >
              <Zap size={10} /> Climate Optimised
            </div>
          )}
        </div>

      </div>
    </div>
  );
};

export default ResultSummary;
