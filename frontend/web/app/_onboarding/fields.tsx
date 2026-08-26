/**
 * Form controls for the post-verification onboarding steps — SCRUM-185.
 *
 * Measured on `buyers-flow-after-email-verification-1.png` (1577, 1:1):
 *   field    672px wide, 68px tall, 16px radius
 *   fill     #fafafa — stock Tailwind `neutral-50`, so no new token
 *   border   1px at ~60% of `line`
 *
 * ⚠️ `buyers-flow-2` draws the same controls at 878×78 on a 1366 artboard, and
 * that reconciles to no scale factor against any other export — not 1577/1366,
 * not the 768 column, not the 68px control height. Treated as artboard drift
 * rather than intent: reproducing it would make the two buyer steps jump ~200px
 * wider mid-flow. Everything here uses the 672/68 system.
 */

import type { ReactNode } from 'react';

/** Label above a control. Required fields get the design's red asterisk. */
export function FieldLabel({
  htmlFor,
  children,
  required,
  hint,
}: {
  htmlFor: string;
  children: ReactNode;
  required?: boolean;
  /** Rendered in muted grey after the label, e.g. "(National Identification Number)". */
  hint?: string;
}) {
  return (
    <label htmlFor={htmlFor} className="block text-base font-bold leading-6 text-ink-buyer">
      {children}
      {hint && <span className="ml-1.5 font-semibold text-ink-500">{hint}</span>}
      {required && (
        <span className="ml-1 text-status-danger" aria-hidden>
          *
        </span>
      )}
    </label>
  );
}

const CONTROL =
  'mt-3 block h-[68px] w-full rounded-2xl border border-line/60 bg-neutral-50 px-6 text-base text-ink-buyer outline-none transition placeholder:text-ink-400 focus:border-emerald-deep focus:ring-2 focus:ring-emerald-deep/20 disabled:cursor-not-allowed disabled:opacity-60';

export function TextField({
  id,
  value,
  onChange,
  placeholder,
  inputMode,
  maxLength,
  autoComplete,
  disabled,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  inputMode?: 'text' | 'numeric';
  maxLength?: number;
  autoComplete?: string;
  disabled?: boolean;
}) {
  return (
    <input
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      inputMode={inputMode}
      maxLength={maxLength}
      autoComplete={autoComplete}
      disabled={disabled}
      className={CONTROL}
    />
  );
}

export function SelectField({
  id,
  value,
  onChange,
  options,
  placeholder,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  options: readonly { value: string; label: string }[];
  placeholder: string;
}) {
  return (
    <div className="relative">
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`${CONTROL} appearance-none pr-14`}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {/* The design draws its own chevron; `appearance-none` removes the native one. */}
      <span className="pointer-events-none absolute right-6 top-[46px] text-ink-500" aria-hidden>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </span>
    </div>
  );
}

/**
 * The reassurance line under an identity field — a shield glyph plus
 * "Your data is encrypted and used only for verification".
 *
 * The claim is accurate: CLAUDE.md §4 requires BVN and NIN to be stored only as
 * bcrypt hashes after verification, and neither is ever logged or returned.
 */
export function SecureNote({ children }: { children: ReactNode }) {
  return (
    <p className="mt-3 flex items-center gap-2 text-[15px] leading-5 text-ink-500">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 flex-none" aria-hidden>
        <path d="M12 21s7-3.2 7-9V6l-7-3-7 3v6c0 5.8 7 9 7 9Z" />
      </svg>
      {children}
    </p>
  );
}

/** Inline error, shown under a control after a failed submit. */
export function FieldError({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="mt-3 text-[15px] leading-5 text-status-danger">
      {children}
    </p>
  );
}

/**
 * Dashed upload target — 180px tall on both the seller PoA and realtor
 * credentials exports, at the same 16px radius as every other control.
 *
 * A real <input type="file"> inside a <label>, not a div with a click handler,
 * so it stays keyboard reachable and works with the OS file picker unaided.
 * Once a file is chosen the zone shows its name, which is the only feedback
 * available — there is no upload preview endpoint.
 */
export function UploadDropzone({
  id,
  file,
  onFile,
  title,
  subtitle,
  accept,
  disabled,
}: {
  id: string;
  file: File | null;
  onFile: (f: File | null) => void;
  title: string;
  subtitle: string;
  accept?: string;
  disabled?: boolean;
}) {
  return (
    <label
      htmlFor={id}
      className={`mt-3 flex h-[180px] w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border border-dashed px-6 text-center transition focus-within:border-emerald-deep focus-within:ring-2 focus-within:ring-emerald-deep/20 ${
        file ? 'border-emerald-deep bg-emerald-deep/[0.04]' : 'border-line-strong hover:border-ink-400'
      } ${disabled ? 'pointer-events-none opacity-60' : ''}`}
    >
      <input
        id={id}
        type="file"
        accept={accept}
        disabled={disabled}
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
        className="sr-only"
      />
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-8 w-8 text-ink-500" aria-hidden>
        <path d="M12 16V4" />
        <path d="m7 9 5-5 5 5" />
        <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
      </svg>
      <span className="text-base font-bold leading-6 text-ink-buyer">{file ? file.name : title}</span>
      <span className="text-[15px] font-semibold leading-5 text-ink-500">
        {file ? 'Choose a different file' : subtitle}
      </span>
    </label>
  );
}
