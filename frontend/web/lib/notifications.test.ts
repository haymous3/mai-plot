import { describe, expect, it } from 'vitest';

import { relativeTime } from './notifications';

describe('relativeTime', () => {
  const now = new Date('2026-06-25T12:00:00Z');

  it('shows "just now" under a minute (and for future skew)', () => {
    expect(relativeTime('2026-06-25T11:59:30Z', now)).toBe('just now');
    expect(relativeTime('2026-06-25T12:00:10Z', now)).toBe('just now');
  });

  it('shows minutes, hours, and days within a week', () => {
    expect(relativeTime('2026-06-25T11:55:00Z', now)).toBe('5m ago');
    expect(relativeTime('2026-06-25T09:00:00Z', now)).toBe('3h ago');
    expect(relativeTime('2026-06-23T12:00:00Z', now)).toBe('2d ago');
  });

  it('falls back to an absolute date past a week', () => {
    expect(relativeTime('2026-06-10T12:00:00Z', now)).toBe('10 Jun 2026');
  });
});
