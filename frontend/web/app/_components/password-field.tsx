'use client';

import { useId, useState } from 'react';

/**
 * Password input with a show/hide toggle — SCRUM-187.
 *
 * Used by every place a password is typed: sign-in (buyer/seller/realtor),
 * registration (password + confirm) and admin sign-in. One component so the
 * four cannot drift; they were already four copies of the same class string.
 *
 * Behaviour that matters:
 *
 *  - The toggle is `type="button"`. Without it the browser treats a bare
 *    <button> inside a <form> as a SUBMIT button, so clicking the eye would
 *    submit the login form instead of revealing the password.
 *  - Visibility resets to hidden on every mount and is never persisted. A
 *    revealed password should not survive navigating away and back.
 *  - `autoComplete` is passed through, not hard-coded: sign-in needs
 *    `current-password` and registration needs `new-password`, and getting that
 *    wrong makes password managers offer the wrong thing.
 *  - Toggling `type` between password/text is the standard approach and keeps
 *    password managers working; rendering a separate text input would not.
 *
 * Accessibility: the button carries an `aria-label` that states the ACTION
 * ("Show password" / "Hide password") and `aria-pressed` for the current state,
 * so a screen reader announces both. The glyph itself is `aria-hidden` — it
 * would otherwise be read as a meaningless graphic.
 */

const FIELD =
  'w-full rounded-md border border-ink-300/60 bg-white py-2.5 pl-3.5 pr-11 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20';

export function PasswordField({
  id,
  name,
  value,
  onChange,
  autoComplete,
  placeholder,
  required,
  disabled,
}: {
  id?: string;
  name?: string;
  value: string;
  onChange: (v: string) => void;
  /** 'current-password' when signing in, 'new-password' when setting one. */
  autoComplete: 'current-password' | 'new-password';
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
}) {
  const [visible, setVisible] = useState(false);
  // Callers that pass no id still need a stable one to hang the toggle's
  // aria-controls off.
  const generated = useId();
  const inputId = id ?? generated;

  return (
    <div className="relative">
      <input
        id={inputId}
        name={name}
        type={visible ? 'text' : 'password'}
        autoComplete={autoComplete}
        required={required}
        disabled={disabled}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={FIELD}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? 'Hide password' : 'Show password'}
        aria-pressed={visible}
        aria-controls={inputId}
        disabled={disabled}
        className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-md text-ink-500 transition hover:text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        {visible ? <EyeOffIcon /> : <EyeIcon />}
      </button>
    </div>
  );
}

function EyeIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4"
      aria-hidden
    >
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4"
      aria-hidden
    >
      <path d="M10.6 6.1A8.9 8.9 0 0 1 12 6c6 0 9.5 6 9.5 6a15.6 15.6 0 0 1-2.9 3.6" />
      <path d="M6.6 6.9A15.6 15.6 0 0 0 2.5 12S6 18 12 18a8.7 8.7 0 0 0 4.2-1" />
      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
      <path d="m3 3 18 18" />
    </svg>
  );
}
