import { describe, expect, it } from 'vitest';

import type { RealtorInspection } from './api';
import {
  countInspections,
  inspectionLocation,
  inspectionStatusMeta,
  isAwaitingAcceptance,
  upcomingInspections,
} from './realtor-inspection';

function insp(overrides: Partial<RealtorInspection> = {}): RealtorInspection {
  return {
    inspection_id: crypto.randomUUID(),
    transaction_id: crypto.randomUUID(),
    status: 'pending',
    proposed_date: '2026-07-15T09:00:00Z',
    confirmed_date: null,
    assignment_expires_at: '2026-07-10T11:00:00Z',
    created_at: '2026-07-09T09:00:00Z',
    report_submitted_at: null,
    property_title: 'Plot 5, Lekki',
    address_text: '1 Admiralty Way',
    lga: 'Eti-Osa',
    state: 'Lagos',
    ...overrides,
  };
}

describe('inspectionStatusMeta', () => {
  it('maps known statuses to a label + bucket', () => {
    expect(inspectionStatusMeta('pending').bucket).toBe('awaiting');
    expect(inspectionStatusMeta('accepted').bucket).toBe('scheduled');
    expect(inspectionStatusMeta('rescheduled').bucket).toBe('scheduled');
    expect(inspectionStatusMeta('completed').bucket).toBe('completed');
  });

  it('falls back for an unknown status', () => {
    expect(inspectionStatusMeta('weird').label).toBe('Unknown');
  });
});

describe('isAwaitingAcceptance', () => {
  it('is true only for pending assignments', () => {
    expect(isAwaitingAcceptance(insp({ status: 'pending' }))).toBe(true);
    expect(isAwaitingAcceptance(insp({ status: 'accepted' }))).toBe(false);
  });
});

describe('countInspections', () => {
  it('buckets by status and totals', () => {
    const counts = countInspections([
      insp({ status: 'pending' }),
      insp({ status: 'accepted' }),
      insp({ status: 'completed' }),
      insp({ status: 'completed' }),
    ]);
    expect(counts).toEqual({ awaiting: 1, scheduled: 1, completed: 2, total: 4 });
  });
});

describe('upcomingInspections', () => {
  it('drops completed and sorts soonest-first by proposed date', () => {
    const later = insp({ status: 'accepted', proposed_date: '2026-07-20T09:00:00Z' });
    const sooner = insp({ status: 'pending', proposed_date: '2026-07-12T09:00:00Z' });
    const done = insp({ status: 'completed', proposed_date: '2026-07-01T09:00:00Z' });

    const result = upcomingInspections([later, done, sooner]);

    expect(result.map((i) => i.inspection_id)).toEqual([sooner.inspection_id, later.inspection_id]);
  });
});

describe('inspectionLocation', () => {
  it('joins the available property fields', () => {
    expect(inspectionLocation(insp())).toBe('1 Admiralty Way, Eti-Osa, Lagos');
  });

  it('falls back when nothing is available', () => {
    expect(
      inspectionLocation(insp({ address_text: null, lga: null, state: null })),
    ).toBe('Location unavailable');
  });
});
