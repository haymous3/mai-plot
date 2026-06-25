import { describe, expect, it } from 'vitest';

import { formatDate, formatDateTime, formatNaira, isPowerOfAttorney } from './format';

describe('formatNaira', () => {
  it('converts kobo to naira with thousands separators', () => {
    expect(formatNaira(850_000_000)).toBe('₦8,500,000');
    expect(formatNaira(5_000_000_000)).toBe('₦50,000,000');
  });

  it('handles zero and rounds fractional kobo to whole naira', () => {
    expect(formatNaira(0)).toBe('₦0');
    expect(formatNaira(150)).toBe('₦2'); // 1.5 naira -> 2
  });
});

describe('formatDate', () => {
  it('formats an ISO timestamp as a short date', () => {
    expect(formatDate('2026-06-15T09:30:00Z')).toBe('15 Jun 2026');
  });

  it('returns an em dash for an invalid date', () => {
    expect(formatDate('not-a-date')).toBe('—');
  });
});

describe('formatDateTime', () => {
  it('formats an ISO timestamp as a precise UTC date+time', () => {
    expect(formatDateTime('2026-06-15T09:30:00Z')).toBe('15 Jun 2026, 09:30');
  });

  it('returns an em dash for an invalid date', () => {
    expect(formatDateTime('nope')).toBe('—');
  });
});

describe('isPowerOfAttorney', () => {
  it('is true only for power_of_attorney', () => {
    expect(isPowerOfAttorney('power_of_attorney')).toBe(true);
    expect(isPowerOfAttorney('owner')).toBe(false);
    expect(isPowerOfAttorney(null)).toBe(false);
    expect(isPowerOfAttorney(undefined)).toBe(false);
  });
});
