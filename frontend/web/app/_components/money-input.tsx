'use client';

import { useEffect, useRef } from 'react';

import { caretAfterGrouping, digitsOnly, groupDigits } from '@/lib/money-input';

/**
 * A naira amount field that groups thousands as you type (SCRUM-202).
 *
 * The contract is deliberately narrow: `value` and `onChange` deal in DIGITS
 * ONLY, and the grouped form exists purely on screen. Callers keep their
 * existing `Number(value) * 100` conversions to kobo unchanged, and a comma can
 * never reach the arithmetic — `Number("10,000,000")` is NaN, and a NaN amount
 * on a payment path is the worst failure available (CLAUDE.md §4).
 *
 * Styling is passed in rather than owned here: these fields already live inside
 * four different form idioms, and giving them one look would be a redesign
 * nobody asked for.
 */
export function MoneyInput({
  value,
  onChange,
  className,
  id,
  placeholder,
  disabled,
  ariaLabel,
  onBlur,
}: {
  /** Digits only, e.g. "45000000". */
  value: string;
  /** Receives digits only. */
  onChange: (digits: string) => void;
  className?: string;
  id?: string;
  placeholder?: string;
  disabled?: boolean;
  ariaLabel?: string;
  /** For fields that commit on blur rather than on every keystroke — the price
   * filters, which would otherwise fire a search mid-amount. */
  onBlur?: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  // Where the caret should sit once React has painted the grouped value.
  // Applying it during onChange would be undone by the re-render.
  const caret = useRef<number | null>(null);

  const display = groupDigits(value);

  useEffect(() => {
    if (caret.current === null || !ref.current) return;
    ref.current.setSelectionRange(caret.current, caret.current);
    caret.current = null;
  });

  return (
    <input
      ref={ref}
      id={id}
      // `inputMode` rather than `type="number"`: a number input rejects the
      // commas this field is entirely about, and brings a spinner nobody wants
      // on a property price.
      inputMode="numeric"
      value={display}
      placeholder={placeholder}
      disabled={disabled}
      aria-label={ariaLabel}
      onBlur={onBlur}
      className={className}
      onChange={(e) => {
        const raw = e.target.value;
        const rawCaret = e.target.selectionStart ?? raw.length;
        const digits = digitsOnly(raw);
        caret.current = caretAfterGrouping(raw, rawCaret, groupDigits(digits));
        onChange(digits);
      }}
    />
  );
}
