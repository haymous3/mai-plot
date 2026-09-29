'use client';

import { useState } from 'react';

import { areasIn, describeBase, isInNigeria, nearestArea, states } from '@/lib/nigeria-areas';

/**
 * A realtor's base location — state → area, or "use my current location"
 * (SCRUM-214). Controlled: the parent owns the coordinates and decides when to
 * save; this only produces them.
 *
 * Nothing leaves the browser until the parent saves. The geolocation button
 * asks the browser (which asks the person); a position outside Nigeria is
 * refused here with the same bounds the server uses, so the realtor is told
 * straight away rather than after a round trip.
 */

export type BaseLocation = { lat: number; lng: number };

export function BaseLocationPicker({
  value,
  onChange,
  controlClassName,
  disabled,
  idPrefix = 'base',
}: {
  value: BaseLocation | null;
  onChange: (next: BaseLocation | null) => void;
  /** The host surface's select styling (onboarding vs portal). */
  controlClassName: string;
  disabled?: boolean;
  idPrefix?: string;
}) {
  // Start the selects on the area nearest the current value, so editing an
  // existing base opens where it already is.
  const initial = value ? nearestArea(value.lat, value.lng) : null;
  const [state, setState] = useState(initial?.state ?? '');
  const [area, setArea] = useState(initial && initial.km < 2 ? initial.area : '');
  const [locating, setLocating] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);

  function pickState(next: string) {
    setState(next);
    setArea('');
    setGeoError(null);
    onChange(null);
  }

  function pickArea(next: string) {
    setArea(next);
    setGeoError(null);
    const found = areasIn(state).find((a) => a.area === next);
    onChange(found ? { lat: found.lat, lng: found.lng } : null);
  }

  function useMyLocation() {
    if (!('geolocation' in navigator)) {
      setGeoError('Your browser can’t share its location. Pick your area instead.');
      return;
    }
    setLocating(true);
    setGeoError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        const { latitude: lat, longitude: lng } = pos.coords;
        if (!isInNigeria(lat, lng)) {
          setGeoError(
            'That location is outside Nigeria — perhaps a VPN. Pick your area instead.',
          );
          return;
        }
        // Reflect it in the selects too, so the person can see and adjust it.
        const near = nearestArea(lat, lng);
        setState(near.state);
        setArea('');
        onChange({ lat, lng });
      },
      (err) => {
        setLocating(false);
        setGeoError(
          err.code === err.PERMISSION_DENIED
            ? 'Location permission was declined. Pick your area instead.'
            : 'We couldn’t get your location. Pick your area instead.',
        );
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
    );
  }

  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2">
        <select
          id={`${idPrefix}-state`}
          aria-label="State"
          value={state}
          onChange={(e) => pickState(e.target.value)}
          disabled={disabled}
          className={controlClassName}
        >
          <option value="">Select state</option>
          {states().map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          id={`${idPrefix}-area`}
          aria-label="Area"
          value={area}
          onChange={(e) => pickArea(e.target.value)}
          disabled={disabled || !state}
          className={controlClassName}
        >
          <option value="">{state ? 'Select area' : 'Select a state first'}</option>
          {areasIn(state).map((a) => (
            <option key={a.area} value={a.area}>
              {a.area}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <button
          type="button"
          onClick={useMyLocation}
          disabled={disabled || locating}
          className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-deep underline-offset-4 hover:underline disabled:opacity-60"
        >
          <svg viewBox="0 0 20 20" fill="none" aria-hidden className="h-4 w-4">
            <circle cx="10" cy="10" r="3" stroke="currentColor" strokeWidth="1.7" />
            <path
              d="M10 2v3M10 15v3M2 10h3M15 10h3"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
            />
          </svg>
          {locating ? 'Finding you…' : 'Use my current location'}
        </button>
        {value && (
          <span className="text-sm text-ink-600" aria-live="polite">
            📍 {describeBase(value.lat, value.lng)}
          </span>
        )}
      </div>

      {geoError && (
        <p role="alert" className="mt-2 text-sm text-status-danger">
          {geoError}
        </p>
      )}
    </div>
  );
}
