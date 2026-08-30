import { describe, expect, it } from 'vitest';

import { caretAfterGrouping, digitsOnly, groupDigits, nairaToKobo } from './money-input';

describe('groupDigits', () => {
  it('groups in threes', () => {
    expect(groupDigits('10000000')).toBe('10,000,000');
    expect(groupDigits('1000')).toBe('1,000');
    expect(groupDigits('45000000')).toBe('45,000,000');
  });

  it('leaves short amounts alone', () => {
    expect(groupDigits('1')).toBe('1');
    expect(groupDigits('999')).toBe('999');
  });

  it('adds the first separator at exactly four digits', () => {
    expect(groupDigits('999')).toBe('999');
    expect(groupDigits('1000')).toBe('1,000');
  });

  it('is idempotent, so re-formatting its own output is safe', () => {
    // The input's displayed value is fed back in on every keystroke.
    expect(groupDigits(groupDigits('10000000'))).toBe('10,000,000');
  });

  it('renders empty input as empty, not as "0"', () => {
    // A field showing 0 the moment it is cleared would fight the user.
    expect(groupDigits('')).toBe('');
    expect(groupDigits('abc')).toBe('');
  });

  it('strips anything a user pastes in', () => {
    expect(groupDigits('₦10,000,000')).toBe('10,000,000');
    expect(groupDigits('10 000 000')).toBe('10,000,000');
    expect(groupDigits('10000000.00')).toBe('1,000,000,000');
  });
});

describe('digitsOnly', () => {
  it('drops a leading-zero run', () => {
    // "007" is never a meant amount.
    expect(digitsOnly('007')).toBe('7');
    expect(digitsOnly('000')).toBe('0');
  });

  it('keeps a single zero', () => {
    expect(digitsOnly('0')).toBe('0');
  });
});

describe('nairaToKobo', () => {
  it('multiplies by 100 on an integer, never a parsed float', () => {
    expect(nairaToKobo('45000000')).toBe(4500000000);
    expect(nairaToKobo('1')).toBe(100);
  });

  it('accepts the grouped form too, so a caller cannot get it wrong', () => {
    // The bug this prevents: Number("10,000,000") is NaN, and a NaN amount
    // reaching a payment field is the worst possible failure (§4).
    expect(nairaToKobo('10,000,000')).toBe(1000000000);
    expect(nairaToKobo('₦45,000,000')).toBe(4500000000);
  });

  it('returns 0 for empty rather than NaN', () => {
    expect(nairaToKobo('')).toBe(0);
    expect(Number.isNaN(nairaToKobo('abc'))).toBe(false);
  });

  it('stays an exact integer at listing-sized amounts', () => {
    const kobo = nairaToKobo('250000000');
    expect(Number.isSafeInteger(kobo)).toBe(true);
    expect(kobo).toBe(25000000000);
  });
});

describe('caretAfterGrouping', () => {
  it('keeps the caret at the end while typing forwards', () => {
    // Typing "1000": raw "1000", caret 4, formatted "1,000" -> caret 5.
    expect(caretAfterGrouping('1000', 4, '1,000')).toBe(5);
  });

  it('holds position when editing mid-number', () => {
    // Caret after "10" in "10000000" is 2 digits in; in "10,000,000" that is
    // index 2. Without this the caret would snap to the end and the next
    // keystroke would land in the wrong place.
    expect(caretAfterGrouping('10000000', 2, '10,000,000')).toBe(2);
  });

  it('counts digits, not characters, when the raw value already has commas', () => {
    // Caret after "10,0" is THREE digits in. In "100,000" that lands at index
    // 3 — immediately before the separator, so the caret sits between "100"
    // and ",000". Counting characters instead would put it at 4, one place too
    // far right, which is exactly the drift this function exists to prevent.
    expect(caretAfterGrouping('10,0000', 4, '100,000')).toBe(3);
  });

  it('stays at the start when no digit precedes the caret', () => {
    expect(caretAfterGrouping('1000', 0, '1,000')).toBe(0);
  });

  it('never runs past the formatted string', () => {
    expect(caretAfterGrouping('1000', 99, '1,000')).toBe(5);
  });

  it('handles an emptied field', () => {
    expect(caretAfterGrouping('', 0, '')).toBe(0);
  });
});
