import { describe, expect, it } from 'vitest';

import { slaStatus } from './sla';

const submitted = '2026-06-15T00:00:00Z';

describe('slaStatus', () => {
  it('reports time left within the 48h window', () => {
    // 12h after submission -> 36h left.
    const s = slaStatus(submitted, new Date('2026-06-15T12:00:00Z'));
    expect(s.overdue).toBe(false);
    expect(Math.round(s.hoursRemaining)).toBe(36);
    expect(s.label).toBe('36h 0m left');
  });

  it('flags overdue once past 48h', () => {
    // 50h after submission -> 2h overdue.
    const s = slaStatus(submitted, new Date('2026-06-17T02:00:00Z'));
    expect(s.overdue).toBe(true);
    expect(s.label).toBe('2h 0m overdue');
  });

  it('treats the exact deadline as overdue', () => {
    const s = slaStatus(submitted, new Date('2026-06-17T00:00:00Z'));
    expect(s.overdue).toBe(true);
  });

  it('handles an invalid date gracefully', () => {
    const s = slaStatus('not-a-date', new Date('2026-06-15T12:00:00Z'));
    expect(s.label).toBe('—');
    expect(s.overdue).toBe(false);
  });
});
