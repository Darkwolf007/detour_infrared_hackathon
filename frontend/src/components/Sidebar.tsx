import React, { useState, useEffect } from 'react';
import {
  Compass, Sun, Moon, MapPin, Clock, User, Zap,
  Sliders, Sparkles, Loader2, Plus, Trash2, AlertTriangle, CloudRain,
} from 'lucide-react';
import { useRouterStore } from '../store/routerStore';
import { usePersonas } from '../hooks/usePersonas';
import { useRoute } from '../hooks/useRoute';
import { LocationInput } from './LocationInput';
import type { WeightVector } from '../types';

// ─── data ─────────────────────────────────────────────────────────────────────

const CITIES = [
  { id: 'barcelona', label: 'BCN' },
  { id: 'dubai',     label: 'DXB' },
  { id: 'chennai',   label: 'CHN' },
] as const;

const TIME_SLOTS = [
  { id: 'early_morning', label: '6–9 am'  },
  { id: 'morning',       label: '9–12'    },
  { id: 'afternoon',     label: '12–4 pm' },
  { id: 'evening',       label: '4–8 pm'  },
  { id: 'night',         label: '8–12 pm' },
];

const AGE_GROUPS = [
  { id: 'under_18', label: 'Under 18' },
  { id: '18_35',    label: '18–35'    },
  { id: '36_55',    label: '36–55'    },
  { id: '56_70',    label: '56–70'    },
  { id: '70_plus',  label: '70+'      },
];

const ROUTE_TYPES = [
  { id: 'typical', label: 'A→B'   },
  { id: 'multi',   label: 'Stops' },
  { id: 'loop',    label: 'Loop'  },
] as const;

const LOOP_DISTANCES = [
  { label: '1 km', value: 1000 }, { label: '2 km', value: 2000 },
  { label: '5 km', value: 5000 }, { label: '30 min', value: 2400 },
];

const REASONS: Record<string, { label: string; sym: string; subs: { id: string; name: string }[] }> = {
  commute:    { label: 'Commute',  sym: '→', subs: [{ id: 'office', name: 'Office' }, { id: 'home', name: 'Evening' }, { id: 'transit', name: 'Transit' }, { id: 'errands', name: 'Errands' }] },
  stroll:     { label: 'Stroll',   sym: '○', subs: [{ id: 'kid', name: 'Parent+Child' }, { id: 'couple', name: 'Couple' }, { id: 'dog', name: 'Dog Walk' }] },
  exercise:   { label: 'Exercise', sym: '△', subs: [{ id: 'running', name: 'Running' }, { id: 'walking', name: 'Fitness' }, { id: 'cycling', name: 'Cycling' }] },
  experience: { label: 'Explore',  sym: '◇', subs: [{ id: 'tourist', name: 'Tourist' }, { id: 'shopping', name: 'Shopping' }, { id: 'hopping', name: 'Bar Hop' }] },
};

const SUB_WEIGHTS: Record<string, WeightVector> = {
  office:   { w_speed: 0.70, w_shade: 0.10, w_nature: 0.05, w_discovery: 0.15 },
  home:     { w_speed: 0.45, w_shade: 0.30, w_nature: 0.15, w_discovery: 0.10 },
  transit:  { w_speed: 0.65, w_shade: 0.15, w_nature: 0.05, w_discovery: 0.15 },
  errands:  { w_speed: 0.35, w_shade: 0.20, w_nature: 0.10, w_discovery: 0.35 },
  kid:      { w_speed: 0.05, w_shade: 0.45, w_nature: 0.40, w_discovery: 0.10 },
  couple:   { w_speed: 0.10, w_shade: 0.30, w_nature: 0.30, w_discovery: 0.30 },
  dog:      { w_speed: 0.15, w_shade: 0.25, w_nature: 0.50, w_discovery: 0.10 },
  running:  { w_speed: 0.65, w_shade: 0.20, w_nature: 0.10, w_discovery: 0.05 },
  walking:  { w_speed: 0.35, w_shade: 0.35, w_nature: 0.20, w_discovery: 0.10 },
  cycling:  { w_speed: 0.75, w_shade: 0.10, w_nature: 0.10, w_discovery: 0.05 },
  tourist:  { w_speed: 0.05, w_shade: 0.20, w_nature: 0.20, w_discovery: 0.55 },
  shopping: { w_speed: 0.10, w_shade: 0.20, w_nature: 0.10, w_discovery: 0.60 },
  hopping:  { w_speed: 0.05, w_shade: 0.15, w_nature: 0.10, w_discovery: 0.70 },
};

const SLIDER_META = [
  { id: 'speed'  as const, label: 'Speed',     color: '#3B82F6' },
  { id: 'shade'  as const, label: 'Shade',     color: '#F59E0B' },
  { id: 'nature' as const, label: 'Nature',    color: '#10B981' },
  { id: 'disc'   as const, label: 'Discovery', color: '#8B5CF6' },
];

function detectTimeSlot(): string {
  const h = new Date().getHours();
  if (h >= 6  && h < 9)  return 'early_morning';
  if (h >= 9  && h < 12) return 'morning';
  if (h >= 12 && h < 16) return 'afternoon';
  if (h >= 16 && h < 20) return 'evening';
  return 'night';
}
function dotCls(i: number, n: number) {
  if (i === 0)     return 'bg-emerald-500';
  if (i === n - 1) return 'bg-red-500';
  return 'bg-slate-400';
}

// ─── theme ────────────────────────────────────────────────────────────────────

interface Theme { bg: string; card: string; bd: string; tx: string; mu: string; fa: string }
const LT: Theme = { bg: '#F4F4F0', card: '#FFFFFF', bd: '#000', tx: '#0a0a0a', mu: '#666', fa: '#ccc' };
const DK: Theme = { bg: '#111',    card: '#1C1C1C', bd: '#ddd', tx: '#f5f5f5', mu: '#888', fa: '#444' };
const ACCENT = '#FFE600';
const BRAND  = '#E3411E';

// ─── standalone helpers (outside component — stable identity) ─────────────────

const Block: React.FC<{ t: Theme; children: React.ReactNode; className?: string; style?: React.CSSProperties }> = ({ t, children, className = '', style }) => (
  <div className={className} style={{ background: t.card, border: `2px solid ${t.bd}`, boxShadow: `3px 3px 0 ${t.bd}`, ...style }}>
    {children}
  </div>
);

const SecLabel: React.FC<{ t: Theme; icon: React.ElementType; text: string }> = ({ t, icon: Icon, text }) => (
  <div className="flex items-center gap-1">
    <Icon size={10} style={{ color: t.mu }} />
    <span className="text-[8px] font-black uppercase tracking-[0.16em]" style={{ color: t.mu }}>{text}</span>
  </div>
);

const Chip: React.FC<{ t: Theme; active: boolean; onClick: () => void; children: React.ReactNode }> = ({ t, active, onClick, children }) => (
  <button type="button" onClick={onClick}
    className="px-2 py-0.5 text-[9px] font-black uppercase tracking-wide transition-all"
    style={{
      background: active ? ACCENT : t.card,
      color: active ? '#000' : t.mu,
      border: `2px solid ${t.bd}`,
      boxShadow: active ? `2px 2px 0 ${t.bd}` : 'none',
    }}>
    {children}
  </button>
);

const NeoSel: React.FC<{ t: Theme; value: string; onChange: (v: string) => void; children: React.ReactNode }> = ({ t, value, onChange, children }) => (
  <div className="relative">
    <select value={value} onChange={e => onChange(e.target.value)}
      className="w-full appearance-none text-[10px] font-semibold py-1 pl-2 pr-6 outline-none cursor-pointer"
      style={{ background: t.card, color: t.tx, border: `2px solid ${t.bd}` }}>
      {children}
    </select>
    <span className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-[8px]"
      style={{ color: t.mu }}>▾</span>
  </div>
);

// ─── component ────────────────────────────────────────────────────────────────

export const Sidebar: React.FC = () => {
  const {
    city, setCity, ageGroup, setAgeGroup,
    reason, setReason, subReason, setSubReason,
    routeType, setRouteType, stops, addStop, removeStop,
    timeSlot, setTimeSlot, maxDistanceM, setMaxDistanceM,
    setCustomWeights, setPersonaId, setActivePersona, activePersona,
    poiQuery, setPoiQuery,
    isLoading, error,
  } = useRouterStore();

  const { data: personas } = usePersonas(city);
  const { submitRoute } = useRoute();

  const [dark, setDark] = useState(() => window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false);
  const [sv, setSv] = useState(7);
  const [ssh, setSsh] = useState(1);
  const [sn, setSn] = useState(1);
  const [sd, setSd] = useState(2);
  const [pLabel, setPLabel] = useState('');
  const [inferring, setInferring] = useState(false);

  const T = dark ? DK : LT;

  // Auto-detect time once
  useEffect(() => { setTimeSlot(detectTimeSlot()); }, []); // eslint-disable-line

  // Sync sliders with active persona
  useEffect(() => {
    if (!activePersona) return;
    setSv(Math.round(activePersona.w_speed * 10));
    setSsh(Math.round(activePersona.w_shade * 10));
    setSn(Math.round(activePersona.w_nature * 10));
    setSd(Math.round(activePersona.w_discovery * 10));
  }, [activePersona]);

  // Apply weights on activity change
  useEffect(() => {
    const m = personas?.find(p => p.reason === reason && p.sub_reason === subReason)
           ?? personas?.find(p => p.reason === reason);
    if (m) { setPersonaId(m.id); setActivePersona(m); setCustomWeights(null); }
    else {
      setPersonaId(null);
      const w = SUB_WEIGHTS[subReason] ?? { w_speed: 0.65, w_shade: 0.10, w_nature: 0.10, w_discovery: 0.15 };
      setCustomWeights(w);
      setSv(Math.round(w.w_speed * 10));    setSsh(Math.round(w.w_shade * 10));
      setSn(Math.round(w.w_nature * 10));   setSd(Math.round(w.w_discovery * 10));
    }
  }, [reason, subReason, personas]); // eslint-disable-line

  const handleSlider = (id: typeof SLIDER_META[number]['id'], val: number) => {
    const s  = id === 'speed'  ? val : sv;
    const sh = id === 'shade'  ? val : ssh;
    const n  = id === 'nature' ? val : sn;
    const d  = id === 'disc'   ? val : sd;
    if (id === 'speed')  setSv(val);
    if (id === 'shade')  setSsh(val);
    if (id === 'nature') setSn(val);
    if (id === 'disc')   setSd(val);
    const t = s + sh + n + d; if (!t) return;
    setPersonaId(null); setActivePersona(null);
    setCustomWeights({
      w_speed: parseFloat((s/t).toFixed(4)), w_shade: parseFloat((sh/t).toFixed(4)),
      w_nature: parseFloat((n/t).toFixed(4)), w_discovery: parseFloat((d/t).toFixed(4)),
    });
  };

  const applyPrompt = async () => {
    if (!poiQuery.trim()) return;
    setInferring(true);
    try {
      const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8001/api/v1';
      const res = await fetch(`${API_BASE}/personas/custom`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: poiQuery.trim(), city }),
      });
      if (!res.ok) throw new Error();
      const { inferred_persona: p } = await res.json();
      setPersonaId(null); setActivePersona(null);
      setCustomWeights({ w_speed: p.w_speed, w_shade: p.w_shade, w_nature: p.w_nature, w_discovery: p.w_discovery });
      setSv(Math.round(p.w_speed*10)); setSsh(Math.round(p.w_shade*10));
      setSn(Math.round(p.w_nature*10)); setSd(Math.round(p.w_discovery*10));
      setPLabel(p.name ?? '');
    } catch { /* keep */ } finally { setInferring(false); }
  };

  const canSubmit   = !isLoading && stops.every(s => s.lat && s.lon);
  const warnDubai   = city === 'dubai'   && timeSlot === 'afternoon';
  const warnChennai = city === 'chennai' && timeSlot === 'afternoon';
  const sliderVals  = { speed: sv, shade: ssh, nature: sn, disc: sd };

  return (
    <div className="w-[360px] h-full flex flex-col shrink-0"
      style={{ background: T.bg, borderRight: `3px solid ${T.bd}`, fontFamily: "'Space Grotesk', 'Inter', sans-serif", overflow: 'hidden' }}>

      {/* ── HEADER ──────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-4 py-2 shrink-0"
        style={{ background: T.card, borderBottom: `3px solid ${T.bd}`, boxShadow: `0 3px 0 ${T.bd}` }}>
        {/* Logo */}
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 flex items-center justify-center shrink-0"
            style={{ background: BRAND, border: `2px solid ${T.bd}`, boxShadow: `2px 2px 0 ${T.bd}` }}>
            <Compass size={14} color="#fff" />
          </div>
          <div>
            <div className="text-[13px] font-black tracking-tight leading-none" style={{ color: T.tx }}>DETOUR</div>
            <div className="text-[7px] font-bold uppercase tracking-[0.18em] leading-none mt-0.5" style={{ color: T.mu }}>road less taken</div>
          </div>
        </div>
        {/* Theme toggle only */}
        <button type="button" onClick={() => setDark(d => !d)}
          className="w-6 h-6 flex items-center justify-center"
          style={{ background: dark ? ACCENT : T.card, border: `2px solid ${T.bd}`, boxShadow: `2px 2px 0 ${T.bd}` }}>
          {dark ? <Sun size={11} color="#000" /> : <Moon size={11} color={T.tx} />}
        </button>
      </header>

      {/* ── FORM ────────────────────────────────────────────────────────── */}
      <form onSubmit={e => { e.preventDefault(); submitRoute.mutate(); }}
        className="flex-1 flex flex-col min-h-0" style={{ overflow: 'hidden' }}>

        {/* form sections — fills height, no scroll */}
        <div className="flex-1 flex flex-col justify-between px-2 py-2 min-h-0" style={{ overflow: 'hidden' }}>

          {/* ── CITY ──────────────────────────────────────────────────── */}
          <Block t={T} className="px-2 py-1.5">
            <div className="flex items-center justify-between">
              <SecLabel t={T} icon={Compass} text="City" />
              <div className="flex gap-1">
                {CITIES.map(c => <Chip key={c.id} t={T} active={city === c.id} onClick={() => setCity(c.id)}>{c.label}</Chip>)}
              </div>
            </div>
          </Block>

          {/* ── ROUTE ─────────────────────────────────────────────────── */}
          <Block t={T}>
            {/* Header row */}
            <div className="flex items-center justify-between px-2 py-1"
              style={{ borderBottom: `2px solid ${T.bd}` }}>
              <SecLabel t={T} icon={MapPin} text="Route" />
              <div className="flex gap-1">
                {ROUTE_TYPES.map(rt => (
                  <Chip key={rt.id} t={T} active={routeType === rt.id} onClick={() => setRouteType(rt.id)}>
                    {rt.label}
                  </Chip>
                ))}
              </div>
            </div>

            {/* Stops */}
            <div className="px-2 pt-1">
              {routeType === 'typical' && (
                <>
                  <LocationInput index={0} placeholder="Starting point" dotClass="bg-emerald-500" dark={dark} />
                  <LocationInput index={1} placeholder="Destination" dotClass="bg-red-500" isLast dark={dark} />
                </>
              )}
              {routeType === 'loop' && (
                <>
                  <LocationInput index={0} placeholder="Start & return" dotClass="bg-emerald-500" isLast dark={dark} />
                  <div className="flex flex-wrap gap-1 my-1">
                    {LOOP_DISTANCES.map(d => (
                      <Chip key={d.value} t={T} active={maxDistanceM === d.value} onClick={() => setMaxDistanceM(d.value)}>
                        {d.label}
                      </Chip>
                    ))}
                  </div>
                </>
              )}
              {routeType === 'multi' && (
                <>
                  <div className="max-h-[72px] overflow-y-auto">
                    {stops.map((stop, idx) => (
                      <div key={stop.id} className="flex items-start gap-0.5">
                        <div className="flex-1 min-w-0">
                          <LocationInput index={idx}
                            placeholder={idx === 0 ? 'Start' : idx === stops.length-1 ? 'End' : `Stop ${idx}`}
                            dotClass={dotCls(idx, stops.length)} isLast={idx === stops.length-1} dark={dark} />
                        </div>
                        {stops.length > 2 && (
                          <button type="button" onClick={() => removeStop(idx)}
                            className="mt-1.5 p-0.5 opacity-30 hover:opacity-60" style={{ color: T.tx }}>
                            <Trash2 size={10} />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                  {stops.length < 5 && (
                    <button type="button" onClick={addStop}
                      className="w-full py-1 text-[9px] font-bold flex items-center justify-center gap-1 mb-1"
                      style={{ border: `1.5px dashed ${T.fa}`, color: T.mu }}>
                      <Plus size={9} /> Add stop
                    </button>
                  )}
                </>
              )}
            </div>

            {/* ── AI Prompt sub-block ── */}
            <div className="mx-2 mb-1.5 mt-0.5" style={{ border: `2px solid ${T.bd}`, boxShadow: `2px 2px 0 ${T.bd}` }}>
              <div className="flex items-stretch">
                <div className="flex items-center justify-center w-7 shrink-0"
                  style={{ background: dark ? '#2a2a2a' : '#f0f0ec', borderRight: `2px solid ${T.bd}` }}>
                  <Sparkles size={11} style={{ color: T.mu }} />
                </div>
                <input type="text" value={poiQuery}
                  onChange={e => { setPoiQuery(e.target.value); if (pLabel) setPLabel(''); }}
                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), applyPrompt())}
                  placeholder="Describe your ideal walk…"
                  className="flex-1 min-w-0 text-[10px] font-medium px-2 py-1.5 outline-none bg-transparent"
                  style={{ color: T.tx }} />
                <button type="button" onClick={applyPrompt} disabled={!poiQuery.trim() || inferring}
                  className="shrink-0 px-2.5 text-[10px] font-black transition-all disabled:opacity-30"
                  style={{ background: poiQuery.trim() ? ACCENT : (dark ? '#2a2a2a' : '#f0f0ec'), borderLeft: `2px solid ${T.bd}`, color: '#000' }}>
                  {inferring ? <Loader2 size={10} className="animate-spin" /> : '→'}
                </button>
              </div>
              {pLabel && (
                <div className="px-2 py-0.5 text-[8px] font-black uppercase tracking-wide"
                  style={{ background: ACCENT, borderTop: `2px solid ${T.bd}`, color: '#000' }}>
                  ✦ {pLabel}
                </div>
              )}
            </div>
          </Block>

          {/* ── WHEN + WHO ────────────────────────────────────────────── */}
          <Block t={T} className="px-2 py-1.5">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="flex items-center justify-between mb-0.5">
                  <SecLabel t={T} icon={Clock} text="When" />
                  <span className="text-[7px] font-black" style={{ color: BRAND }}>AUTO</span>
                </div>
                <NeoSel t={T} value={timeSlot} onChange={setTimeSlot}>
                  {TIME_SLOTS.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
                </NeoSel>
              </div>
              <div>
                <div className="mb-0.5"><SecLabel t={T} icon={User} text="Who" /></div>
                <NeoSel t={T} value={ageGroup} onChange={setAgeGroup}>
                  {AGE_GROUPS.map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
                </NeoSel>
              </div>
            </div>
          </Block>

          {/* ── ACTIVITY ──────────────────────────────────────────────── */}
          <Block t={T} className="px-2 py-1.5">
            <div className="flex items-center justify-between mb-1">
              <SecLabel t={T} icon={Zap} text="Activity" />
              <NeoSel t={T} value={subReason} onChange={setSubReason}>
                {REASONS[reason]?.subs.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </NeoSel>
            </div>
            <div className="grid grid-cols-4 gap-0.5">
              {Object.keys(REASONS).map(r => (
                <button key={r} type="button"
                  onClick={() => { setReason(r); setSubReason(REASONS[r].subs[0].id); }}
                  className="flex flex-col items-center py-0.5 text-[8px] font-black uppercase tracking-wide gap-0.5 transition-all"
                  style={{
                    background: reason === r ? ACCENT : T.card,
                    color: reason === r ? '#000' : T.mu,
                    border: `2px solid ${T.bd}`,
                    boxShadow: reason === r ? `2px 2px 0 ${T.bd}` : 'none',
                  }}>
                  <span className="text-[10px] font-normal">{REASONS[r].sym}</span>
                  {REASONS[r].label}
                </button>
              ))}
            </div>
          </Block>

          {/* ── STATUS ───────────────────────────────────────────────── */}
          <Block t={T} className="px-2 py-1">
            <div className="mb-1"><SecLabel t={T} icon={AlertTriangle} text="Status" /></div>
            <div className="h-[22px] px-2 py-1 text-[9px] font-semibold overflow-hidden"
              style={{
                border: `1.5px solid ${error ? BRAND : T.fa}`,
                background: error ? '#FFE8E3' : (dark ? '#1a1a1a' : '#f9f9f7'),
                color: error ? '#000' : T.mu,
              }}>
              {error ? error : ''}
            </div>
          </Block>

          {/* ── PRIORITIES ────────────────────────────────────────────── */}
          <Block t={T} className="px-2 py-1.5">
            <div className="flex items-center justify-between mb-1">
              <SecLabel t={T} icon={Sliders} text="Priorities" />
              <span className="text-[8px] font-bold uppercase px-1.5 py-px"
                style={{ border: `1.5px solid ${T.fa}`, color: T.mu }}>
                {REASONS[reason]?.subs.find(s => s.id === subReason)?.name}
              </span>
            </div>
            <div className="space-y-0.5">
              {SLIDER_META.map(s => (
                <div key={s.id} className="flex items-center gap-2">
                  <span className="text-[9px] font-semibold w-14 shrink-0" style={{ color: T.mu }}>{s.label}</span>
                  <input type="range" min="0" max="10" value={sliderVals[s.id]}
                    onChange={e => handleSlider(s.id, +e.target.value)}
                    className={`flex-1 cursor-pointer ${dark ? 'dark-thumb' : ''}`}
                    style={{ color: s.color, accentColor: s.color }} />
                  <span className="text-[9px] font-black w-3.5 text-right tabular-nums shrink-0" style={{ color: s.color }}>
                    {sliderVals[s.id]}
                  </span>
                </div>
              ))}
            </div>
          </Block>

          {/* Warnings */}
          {(warnDubai || warnChennai) && (
            <div className="px-2.5 py-1.5 flex items-center gap-1.5 text-[9px] font-semibold"
              style={{ border: `2px solid ${T.bd}`, background: warnDubai ? '#FFF3CD' : '#D0E8FF', color: '#000' }}>
              {warnDubai ? <AlertTriangle size={11} /> : <CloudRain size={11} />}
              {warnDubai ? 'Peak heat 12–4 pm. Try morning or evening.' : 'Monsoon season — paths may be wet.'}
            </div>
          )}
        </div>{/* end scrollable area */}

        {/* ── SUBMIT — always pinned ─────────────────────────────────── */}
        <div className="shrink-0 px-2 py-2" style={{ borderTop: `3px solid ${T.bd}` }}>
          <button type="submit" disabled={!canSubmit}
            className="w-full py-2 text-[12px] font-black uppercase tracking-widest flex items-center justify-center gap-2 transition-all disabled:opacity-40 disabled:cursor-not-allowed active:translate-x-0.5 active:translate-y-0.5 active:shadow-none"
            style={{
              background: canSubmit && !isLoading ? BRAND : T.card,
              color: canSubmit && !isLoading ? '#fff' : T.mu,
              border: `2.5px solid ${T.bd}`,
              boxShadow: canSubmit && !isLoading ? `4px 4px 0 ${T.bd}` : 'none',
            }}>
            {isLoading
              ? <><Loader2 size={14} className="animate-spin" /> Calculating…</>
              : <><Compass size={14} /> Find Route</>}
          </button>
        </div>

      </form>
    </div>
  );
};
