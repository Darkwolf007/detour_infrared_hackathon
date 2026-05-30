import React, { useState, useRef, useEffect } from 'react';
import { X, Loader2, Crosshair } from 'lucide-react';
import { useNominatim } from '../hooks/useNominatim';
import type { GeocodingResult } from '../hooks/useNominatim';
import { useRouterStore } from '../store/routerStore';

interface LocationInputProps {
  index: number;
  placeholder?: string;
  dotClass?: string;
  isLast?: boolean;
  dark?: boolean;
}

function splitDisplayName(name: string): { primary: string; secondary: string } {
  const parts = name.split(', ');
  return { primary: parts[0] ?? name, secondary: parts.length > 1 ? parts.slice(1, 3).join(', ') : '' };
}

export const LocationInput: React.FC<LocationInputProps> = ({
  index, placeholder = 'Search a place…', dotClass = 'bg-slate-400', isLast = true, dark = false,
}) => {
  const { city, stops, updateStop, activeStopIndex, setActiveStopIndex } = useRouterStore();
  const stop = stops[index];
  const [value, setValue] = useState(stop?.label || '');
  const [open, setOpen]   = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef     = useRef<HTMLInputElement>(null);
  const { suggestions, isSearching } = useNominatim(value, city);
  const isPicking = activeStopIndex === index;

  useEffect(() => { setValue(stop?.label || ''); }, [stop?.label]);

  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const select = (item: GeocodingResult) => {
    const label = splitDisplayName(item.display_name).primary;
    updateStop(index, { lat: parseFloat(item.lat), lon: parseFloat(item.lon), label });
    setValue(label); setOpen(false);
  };
  const clear = () => {
    setValue(''); updateStop(index, { lat: 0, lon: 0, label: '' });
    setActiveStopIndex(null); inputRef.current?.focus();
  };
  const toggleMapPick = (e: React.MouseEvent) => {
    e.preventDefault(); setActiveStopIndex(isPicking ? null : index); setOpen(false);
  };

  const bd = dark ? '#fff' : '#000';
  const bg = dark ? '#1C1C1C' : '#fff';
  const tx = dark ? '#fff' : '#000';
  const ph = dark ? '#666' : '#999';

  return (
    <div ref={containerRef} className="flex items-stretch gap-1.5">
      {/* Dot + connector */}
      <div className="flex flex-col items-center shrink-0 w-3.5 mt-2">
        <div className={`w-2.5 h-2.5 rounded-full ${dotClass} border border-black/20`} />
        {!isLast && <div className="flex-1 min-h-[12px] w-px mt-0.5" style={{ background: dark ? '#444' : '#ccc' }} />}
      </div>

      {/* Input */}
      <div className="flex-1 relative pb-1.5">
        <div
          className="flex items-center gap-1.5 px-2.5 py-1.5"
          style={{
            background: bg, border: `2px solid ${isPicking ? '#E3411E' : bd}`,
            boxShadow: isPicking ? `2px 2px 0px #E3411E` : 'none',
          }}
        >
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={e => { setValue(e.target.value); setOpen(true); setActiveStopIndex(null); }}
            onFocus={() => setOpen(true)}
            placeholder={isPicking ? 'Click map to place pin…' : placeholder}
            className="flex-1 bg-transparent outline-none min-w-0 text-[11px] font-medium"
            style={{ color: tx, caretColor: '#E3411E' }}
          />
          <style>{`input::placeholder { color: ${ph}; }`}</style>
          {isSearching ? (
            <Loader2 size={11} className="animate-spin text-brand-500 shrink-0" />
          ) : value ? (
            <button type="button" onClick={clear} className="shrink-0 opacity-40 hover:opacity-80" style={{ color: tx }}>
              <X size={11} />
            </button>
          ) : null}
        </div>

        {open && suggestions.length > 0 && (
          <div
            className="absolute z-[1000] left-0 right-0 mt-0.5 overflow-hidden animate-fade-in"
            style={{ background: bg, border: `2px solid ${bd}`, boxShadow: `4px 4px 0px ${bd}` }}
          >
            {suggestions.map(item => {
              const { primary, secondary } = splitDisplayName(item.display_name);
              return (
                <button key={item.place_id} type="button"
                  onMouseDown={e => { e.preventDefault(); select(item); }}
                  className="w-full text-left px-3 py-2 flex flex-col hover:bg-yellow-400/20 transition-colors"
                  style={{ borderBottom: `1px solid ${dark ? '#333' : '#eee'}`, color: tx }}>
                  <p className="text-[11px] font-semibold truncate">{primary}</p>
                  {secondary && <p className="text-[10px] opacity-50 truncate">{secondary}</p>}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Map-pick */}
      <button type="button" title={isPicking ? 'Cancel' : 'Pick from map'} onClick={toggleMapPick}
        className="shrink-0 self-start mt-1 p-1.5 transition-all"
        style={{
          background: isPicking ? '#FFE600' : bg,
          border: `2px solid ${bd}`,
          boxShadow: isPicking ? `2px 2px 0px ${bd}` : 'none',
          color: bd,
        }}>
        <Crosshair size={12} />
      </button>
    </div>
  );
};
