import React, { useEffect, useMemo, useState } from 'react';
import { MapContainer, TileLayer, Polyline, Marker, Popup, Rectangle, ImageOverlay, useMap, useMapEvents } from 'react-leaflet';
import L, { LatLngBounds } from 'leaflet';
import 'leaflet/dist/leaflet.css';

import { useRouterStore } from '../store/routerStore';
import { CITY_CONFIGS } from '../utils/cityConfig';
import { utciColor, getComfortLabel } from '../utils/utciColor';
import type { PoiWaypoint } from '../types';

// Fix Leaflet default icon paths
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon   from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({ iconUrl: markerIcon, iconRetinaUrl: markerIcon2x, shadowUrl: markerShadow });

// ── marker factories ────────────────────────────────────────────────────────

const stopMarker = (color: string, label: string) => L.divIcon({
  html: `<div style="position:relative;display:flex;align-items:center;justify-content:center">
    <div style="position:absolute;width:32px;height:32px;border-radius:50%;background:${color}22" class="pulse-marker-active"></div>
    <div style="width:22px;height:22px;border-radius:50%;background:${color};border:2.5px solid #000;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:900;color:#fff;font-family:'Space Grotesk',sans-serif;box-shadow:2px 2px 0 #000">
      ${label}
    </div>
  </div>`,
  className: '',
  iconSize: [32, 32],
  iconAnchor: [16, 16],
});

const poiMarker = (poi: PoiWaypoint) => L.divIcon({
  html: `<div style="display:flex;flex-direction:column;align-items:center;gap:2px">
    <div style="width:30px;height:30px;background:#FFE600;border:2.5px solid #000;box-shadow:2px 2px 0 #000;display:flex;align-items:center;justify-content:center;font-size:14px">
      ${poi.emoji}
    </div>
    <div style="background:#FFE600;border:2px solid #000;box-shadow:1px 1px 0 #000;padding:1px 5px;font-size:8px;font-weight:900;color:#000;font-family:'Space Grotesk',sans-serif;white-space:nowrap;max-width:80px;overflow:hidden;text-overflow:ellipsis;text-transform:uppercase;letter-spacing:0.05em">
      ${poi.name.length > 12 ? poi.name.slice(0,12)+'…' : poi.name}
    </div>
  </div>`,
  className: '',
  iconSize: [30, 48],
  iconAnchor: [15, 48],
});

// ── layer config ────────────────────────────────────────────────────────────

interface LayerDef {
  id: string;
  label: string;
  color: string;
  defaultOn: boolean;
}
const LAYERS: LayerDef[] = [
  { id: 'route',   label: 'Route',   color: '#E3411E', defaultOn: true  },
  { id: 'utci',    label: 'UTCI',    color: '#f97316', defaultOn: true  },
  { id: 'wind',    label: 'Wind',    color: '#14b8a6', defaultOn: false },
  { id: 'solar',   label: 'Solar',   color: '#fbbf24', defaultOn: false },
  { id: 'network', label: 'Streets', color: '#94a3b8', defaultOn: false },
  { id: 'pois',    label: 'POIs',    color: '#FFE600', defaultOn: true  },
];

// ── inner map components ────────────────────────────────────────────────────

const MapClickHandler: React.FC = () => {
  const map = useMap();
  const { activeStopIndex, updateStop, setActiveStopIndex } = useRouterStore();
  useEffect(() => {
    map.getContainer().style.cursor = activeStopIndex !== null ? 'crosshair' : '';
  }, [activeStopIndex, map]);
  useMapEvents({
    click: async (e) => {
      if (activeStopIndex === null) return;
      const idx = activeStopIndex;
      const { lat, lng } = e.latlng;
      updateStop(idx, { lat, lon: lng, label: `${lat.toFixed(5)}, ${lng.toFixed(5)}` });
      setActiveStopIndex(null);
      try {
        const res = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json`);
        if (res.ok) {
          const data = await res.json();
          const parts: string[] = (data.display_name ?? '').split(', ');
          updateStop(idx, { label: parts.slice(0, 3).join(', ') || `${lat.toFixed(5)}, ${lng.toFixed(5)}` });
        }
      } catch { /* keep coordinate label */ }
    },
  });
  return null;
};

const MapController: React.FC = () => {
  const map = useMap();
  const { city, routeResult } = useRouterStore();
  useEffect(() => {
    const config = CITY_CONFIGS[city];
    map.setView(config.center, config.zoom);
  }, [city, map]);
  useEffect(() => {
    if (routeResult?.route_geojson?.coordinates?.length) {
      const bounds = new LatLngBounds(routeResult.route_geojson.coordinates.map(c => [c[1], c[0]] as [number, number]));
      map.fitBounds(bounds, { paddingTopLeft: [40, 40], paddingBottomRight: [100, 40] });
    }
  }, [routeResult, map]);
  return null;
};

// ── layer toggle panel ──────────────────────────────────────────────────────

const LayerPanel: React.FC<{ active: Set<string>; toggle: (id: string) => void; hasResult: boolean }> = ({ active, toggle, hasResult }) => (
  <div
    className="absolute top-3 right-3 z-[1000] flex flex-col gap-1 p-2"
    style={{ background: '#F4F4F0', border: '2.5px solid #000', boxShadow: '3px 3px 0 #000' }}
  >
    <div className="text-[8px] font-black uppercase tracking-widest text-black mb-0.5 px-0.5">Layers</div>
    {LAYERS.map(layer => {
      const on = active.has(layer.id);
      const disabled = !hasResult && !['route', 'pois'].includes(layer.id);
      return (
        <button
          key={layer.id}
          type="button"
          onClick={() => !disabled && toggle(layer.id)}
          className="flex items-center gap-1.5 px-2 py-1 text-[9px] font-black uppercase tracking-wide transition-all"
          style={{
            background: on ? layer.color : 'transparent',
            color: on ? (layer.color === '#FFE600' ? '#000' : '#000') : '#888',
            border: `1.5px solid ${on ? '#000' : '#ccc'}`,
            boxShadow: on ? '1.5px 1.5px 0 #000' : 'none',
            opacity: disabled ? 0.3 : 1,
            cursor: disabled ? 'not-allowed' : 'pointer',
          }}
        >
          <span
            className="w-2 h-2 shrink-0"
            style={{ background: on ? '#000' : layer.color, border: '1px solid #000' }}
          />
          {layer.label}
        </button>
      );
    })}
  </div>
);

// ── main component ──────────────────────────────────────────────────────────

export const MapPanel: React.FC = () => {
  const { city, stops, routeResult, activeStopIndex, isLoading } = useRouterStore();
  const cityConfig = CITY_CONFIGS[city];

  // Layer visibility state
  const [activeLayers, setActiveLayers] = useState<Set<string>>(
    () => new Set(LAYERS.filter(l => l.defaultOn).map(l => l.id))
  );
  const toggleLayer = (id: string) =>
    setActiveLayers(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });

  const show = (id: string) => activeLayers.has(id);

  const analysisBounds = useMemo(() => {
    if (!isLoading) return null;
    const placed = stops.filter(s => s.lat && s.lon);
    if (!placed.length) return null;
    const lats = placed.map(s => s.lat), lons = placed.map(s => s.lon);
    const pad = 0.006;
    return [[Math.min(...lats)-pad, Math.min(...lons)-pad], [Math.max(...lats)+pad, Math.max(...lons)+pad]] as [[number,number],[number,number]];
  }, [stops, isLoading]);

  return (
    <div className="flex-1 h-full w-full relative">

      {/* Map-pick mode banner */}
      {activeStopIndex !== null && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[9999] px-4 py-2 text-xs font-black uppercase tracking-wider pointer-events-none animate-fade-in"
          style={{ background: '#FFE600', border: '2px solid #000', boxShadow: '3px 3px 0 #000', color: '#000' }}>
          Click map to place pin
        </div>
      )}

      {/* Layer toggle panel */}
      <LayerPanel active={activeLayers} toggle={toggleLayer} hasResult={!!routeResult} />

      <MapContainer center={cityConfig.center} zoom={cityConfig.zoom} zoomControl={false} className="w-full h-full">
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        />
        <MapClickHandler />
        <MapController />

        {/* Loading bbox rectangle */}
        {analysisBounds && (
          <Rectangle bounds={analysisBounds} pathOptions={{ color: '#E3411E', weight: 2, opacity: 0.7, fillOpacity: 0.04, dashArray: '6 4' }} />
        )}

        {/* Stop markers */}
        {stops.map((stop, idx) => {
          if (!stop.lat || !stop.lon) return null;
          const isStart = idx === 0, isEnd = idx === stops.length - 1;
          const label = stops.length === 2 ? (isStart ? 'S' : 'E') : String(idx + 1);
          const color = isStart ? '#10b981' : isEnd ? '#E3411E' : '#6366f1';
          return (
            <Marker key={stop.id} position={[stop.lat, stop.lon]} icon={stopMarker(color, label)}>
              <Popup>
                <div style={{ fontFamily:"'Space Grotesk',sans-serif", padding:'8px 12px', background:'#F4F4F0', minWidth:120 }}>
                  <div style={{ fontSize:8, fontWeight:900, textTransform:'uppercase', letterSpacing:'0.14em', color:'#E3411E', marginBottom:3 }}>
                    {isStart ? 'Start' : isEnd ? 'End' : `Stop ${idx}`}
                  </div>
                  <div style={{ fontSize:11, fontWeight:700, color:'#000' }}>{stop.label}</div>
                </div>
              </Popup>
            </Marker>
          );
        })}

        {/* ── SDK analysis overlays ─────────────────────────────────── */}

        {show('utci') && routeResult?.utci_image && routeResult.utci_bounds && (
          <ImageOverlay
            url={`data:image/png;base64,${routeResult.utci_image}`}
            bounds={routeResult.utci_bounds as [[number,number],[number,number]]}
            opacity={0.50} zIndex={300}
          />
        )}

        {show('wind') && routeResult?.wind_image && routeResult.wind_bounds && (
          <ImageOverlay
            url={`data:image/png;base64,${routeResult.wind_image}`}
            bounds={routeResult.wind_bounds as [[number,number],[number,number]]}
            opacity={0.45} zIndex={310}
          />
        )}

        {show('solar') && routeResult?.solar_image && routeResult.solar_bounds && (
          <ImageOverlay
            url={`data:image/png;base64,${routeResult.solar_image}`}
            bounds={routeResult.solar_bounds as [[number,number],[number,number]]}
            opacity={0.40} zIndex={320}
          />
        )}

        {/* ── Street network ────────────────────────────────────────── */}
        {show('network') && routeResult?.network_geojson?.features?.map((feat: any, idx: number) => {
          const geomType = feat.geometry?.type;
          const coords = feat.geometry?.coordinates;
          if (!coords) return null;
          if (geomType === 'LineString') {
            return (
              <Polyline key={`net-${idx}`} positions={coords.map((c: number[]) => [c[1], c[0]] as [number,number])}
                pathOptions={{ color: '#94a3b8', weight: 1, opacity: 0.3 }} />
            );
          }
          if (geomType === 'MultiLineString') {
            return (coords as number[][][]).map((line, li) => (
              <Polyline key={`net-${idx}-${li}`} positions={line.map(c => [c[1], c[0]] as [number,number])}
                pathOptions={{ color: '#94a3b8', weight: 1, opacity: 0.3 }} />
            ));
          }
          return null;
        })}

        {/* ── Route edge scores ─────────────────────────────────────── */}
        {show('route') && routeResult?.edge_scores?.map((edge, idx) => {
          const color = utciColor(edge.utci_score);
          return (
            <Polyline key={`edge-${idx}`}
              positions={edge.coordinates.map(c => [c[1], c[0]] as [number,number])}
              pathOptions={{ color, weight: 6, opacity: 0.9, lineCap: 'round', lineJoin: 'round' }}>
              <Popup>
                <div style={{ minWidth: 160, fontFamily: "'Space Grotesk',sans-serif", padding: '10px 12px', background: '#F4F4F0' }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
                    <span style={{ fontSize:10, fontWeight:900, textTransform:'uppercase', letterSpacing:'0.10em', color:'#000' }}>Segment</span>
                    <span style={{ fontSize:8, fontWeight:900, textTransform:'uppercase', letterSpacing:'0.08em', background:color, color:'#000', padding:'2px 6px', border:'1.5px solid #000', boxShadow:'1px 1px 0 #000' }}>
                      {getComfortLabel(edge.utci_score)}
                    </span>
                  </div>
                  <div style={{ display:'grid', gridTemplateColumns:'1fr auto', gap:'3px 12px', fontSize:10, color:'#555' }}>
                    <span>Feels Like</span><span style={{ fontWeight:900, color:'#000', textAlign:'right' }}>{edge.raw_utci}°C</span>
                    <span>Wind</span><span style={{ fontWeight:900, color:'#000', textAlign:'right' }}>{Math.round(edge.wind_score*5)}/5</span>
                    <span>Shade</span><span style={{ fontWeight:900, color:'#000', textAlign:'right' }}>{Math.round(edge.shade_score*100)}%</span>
                    <span>Nature</span><span style={{ fontWeight:900, color:'#000', textAlign:'right' }}>{Math.round(edge.veg_score*100)}%</span>
                  </div>
                </div>
              </Popup>
            </Polyline>
          );
        })}

        {/* ── POI waypoints resolved from the prompt ────────────────── */}
        {show('pois') && routeResult?.poi_waypoints?.map((poi, idx) => (
          <Marker key={`poi-${idx}`} position={[poi.lat, poi.lon]} icon={poiMarker(poi)} zIndexOffset={1000}>
            <Popup>
              <div style={{ fontFamily:"'Space Grotesk',sans-serif", padding:'8px 12px', background:'#F4F4F0', minWidth:130 }}>
                <div style={{ fontSize:18, marginBottom:4, lineHeight:1 }}>{poi.emoji}</div>
                <div style={{ fontSize:11, fontWeight:900, textTransform:'uppercase', letterSpacing:'0.06em', color:'#000' }}>{poi.name}</div>
                <div style={{ fontSize:8, fontWeight:700, textTransform:'uppercase', letterSpacing:'0.12em', color:'#888', marginTop:3, borderTop:'1.5px solid #ddd', paddingTop:3 }}>
                  {poi.poi_type.replace(/_/g,' ')}
                </div>
              </div>
            </Popup>
          </Marker>
        ))}

      </MapContainer>
    </div>
  );
};

export default MapPanel;
