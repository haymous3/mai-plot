'use client';

import type { ReactNode } from 'react';

/**
 * Shared chrome for the Settings tabs — SCRUM-188.
 *
 * Measured on `design/buyer-profile-page/` (1577 artboard, 1:1):
 *   page bg        #fbfbfb
 *   container      182..1396 = 1216, the same width the landing page uses
 *   sidebar card   278 wide
 *   content card   904 wide, 32px gutter between them
 *   nav item       246x48
 *   field          48px tall, #fafafa fill (stock `neutral-50`)
 *
 * Controls here are 48px, NOT the 68px used by the onboarding flow. That is a
 * genuine difference between the two designs, not drift: onboarding is a
 * full-screen single-purpose funnel, Settings is a dense two-column form.
 */

export const SETTINGS_TABS = ['profile', 'financial', 'notifications', 'security'] as const;
export type SettingsTab = (typeof SETTINGS_TABS)[number];

const CONTROL =
  'mt-2 block h-12 w-full rounded-xl border border-line/60 bg-neutral-50 px-4 text-sm text-ink-buyer outline-none transition placeholder:text-ink-400 focus:border-emerald-deep focus:ring-2 focus:ring-emerald-deep/20 disabled:cursor-not-allowed disabled:text-ink-500';

/** White card with the measured 1px #e5e7eb hairline. */
export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-line bg-white p-8 ${className}`}>
      {children}
    </section>
  );
}

export function CardHeading({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-7">
      <h2 className="text-xl font-bold leading-7 text-ink-buyer">{title}</h2>
      {subtitle && <p className="mt-1.5 text-sm leading-5 text-ink-500">{subtitle}</p>}
    </div>
  );
}

export function Field({
  id,
  label,
  children,
  required,
  hint,
  note,
}: {
  id: string;
  label: string;
  children: ReactNode;
  required?: boolean;
  hint?: string;
  note?: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-bold leading-5 text-ink-buyer">
        {label}
        {hint && <span className="ml-1 font-semibold text-ink-500">{hint}</span>}
        {required && (
          <span className="ml-1 text-status-danger" aria-hidden>
            *
          </span>
        )}
      </label>
      {children}
      {note}
    </div>
  );
}

export function TextInput({
  id,
  value,
  onChange,
  placeholder,
  disabled,
  inputMode,
  maxLength,
  icon,
  autoComplete,
}: {
  id: string;
  value: string;
  onChange?: (v: string) => void;
  placeholder?: string;
  disabled?: boolean;
  inputMode?: 'text' | 'numeric' | 'email' | 'tel';
  maxLength?: number;
  /** Leading glyph, as the design draws on the Profile fields. */
  icon?: ReactNode;
  autoComplete?: string;
}) {
  return (
    <div className="relative">
      {icon && (
        <span aria-hidden className="pointer-events-none absolute left-4 top-[22px] text-ink-400">
          {icon}
        </span>
      )}
      <input
        id={id}
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        placeholder={placeholder}
        disabled={disabled || !onChange}
        readOnly={!onChange}
        inputMode={inputMode}
        maxLength={maxLength}
        autoComplete={autoComplete}
        className={`${CONTROL} ${icon ? 'pl-11' : ''}`}
      />
    </div>
  );
}

export function SelectInput({
  id,
  value,
  onChange,
  options,
  placeholder,
  disabled,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  options: readonly { value: string; label: string }[];
  placeholder: string;
  disabled?: boolean;
}) {
  return (
    <div className="relative">
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className={`${CONTROL} appearance-none pr-11`}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <span className="pointer-events-none absolute right-4 top-[22px] text-ink-500" aria-hidden>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-4 w-4"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </span>
    </div>
  );
}

/** Reassurance line under an identity field, with the design's shield glyph. */
export function SecureNote({ children }: { children: ReactNode }) {
  return (
    <p className="mt-2 flex items-center gap-1.5 text-xs leading-4 text-ink-500">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-3.5 w-3.5 flex-none"
        aria-hidden
      >
        <path d="M12 21s7-3.2 7-9V6l-7-3-7 3v6c0 5.8 7 9 7 9Z" />
      </svg>
      {children}
    </p>
  );
}

export function PrimaryButton({
  children,
  onClick,
  disabled,
  tone = 'brand',
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  tone?: 'brand' | 'danger';
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex h-11 items-center justify-center gap-2 rounded-xl px-5 text-sm font-semibold text-white transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-line disabled:text-ink-400 ${
        tone === 'danger'
          ? 'bg-status-urgent hover:brightness-105 focus-visible:ring-status-urgent'
          : 'bg-emerald-deep hover:brightness-110 focus-visible:ring-emerald-deep'
      }`}
    >
      {children}
    </button>
  );
}

export function GhostButton({ children, onClick }: { children: ReactNode; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-11 items-center rounded-xl border border-line-strong px-5 text-sm font-semibold text-ink-700 transition hover:border-ink-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep"
    >
      {children}
    </button>
  );
}

/**
 * Row toggle for the Notifications tab.
 *
 * A real checkbox under the switch, so it is keyboard reachable and announced
 * as a checkbox rather than a decorated div.
 */
export function ToggleRow({
  id,
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label
      htmlFor={id}
      className={`flex items-center justify-between gap-6 rounded-xl bg-surface-page px-5 py-4 ${
        disabled ? 'opacity-60' : 'cursor-pointer'
      }`}
    >
      <span>
        <span className="block text-sm font-bold leading-5 text-ink-buyer">{label}</span>
        <span className="mt-1 block text-sm leading-5 text-ink-500">{description}</span>
      </span>
      <input
        id={id}
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="peer sr-only"
      />
      {/*
        The knob is an ::after on the track, not a child <span>. `peer-checked:`
        compiles to `.peer:checked ~ .target`, a SIBLING combinator — it cannot
        reach a descendant of the sibling, so `peer-checked:left-6` on a nested
        span would have silently done nothing and the knob would never move.
        Styling the track's own pseudo-element keeps the target a sibling.

        No `after:content-['']` here on purpose: Tailwind emits nothing for it
        (checked in the built CSS), and it is not needed — every `after:*`
        utility already declares `content:var(--tw-content)`, which preflight
        defaults to `""`. Adding the class back would look load-bearing while
        compiling to nothing, the exact trap `csscheck.js` exists to catch.
      */}
      <span
        aria-hidden
        className="relative h-7 w-12 flex-none rounded-full bg-ink-300 transition after:absolute after:left-1 after:top-1 after:h-5 after:w-5 after:rounded-full after:bg-white after:transition-transform peer-checked:bg-emerald-deep peer-checked:after:translate-x-5 peer-focus-visible:ring-2 peer-focus-visible:ring-emerald-deep peer-focus-visible:ring-offset-2"
      />
    </label>
  );
}

export function StatusNote({ tone, children }: { tone: 'ok' | 'error'; children: ReactNode }) {
  return (
    <p
      role={tone === 'error' ? 'alert' : 'status'}
      className={`mt-4 text-sm leading-5 ${
        tone === 'error' ? 'text-status-danger' : 'text-emerald-deep'
      }`}
    >
      {children}
    </p>
  );
}
