import { describe, expect, it } from 'vitest';

import type { RealtorInspection } from './api';
import {
  acceptanceWindow,
  countInspections,
  inspectionLocation,
  inspectionMatchesQuery,
  inspectionStatusMeta,
  isAwaitingAcceptance,
  isSameMonth,
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
    buyer_ref: 'b1a2c3d4',
    inspection_ref: 'i1a2c3d4',
    property_title: 'Plot 5, Lekki',
    address_text: '1 Admiralty Way',
    lga: 'Eti-Osa',
    state: 'Lagos',
    property_type: 'land',
    sale_type: 'normal',
    size_sqm: 1000,
    asking_price_kobo: 5000000000,
    cover_photo_url: null,
    seller_authority_type: 'owner',
    seller_name: 'Mr. Adebayo',
    seller_phone_masked: '+234 *** **** 824',
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

describe('inspectionMatchesQuery', () => {
  it('matches on property title and location, case-insensitively', () => {
    const i = insp({ property_title: 'Lekki Duplex', address_text: '1 Admiralty Way' });
    expect(inspectionMatchesQuery(i, 'lekki')).toBe(true);
    expect(inspectionMatchesQuery(i, 'ADMIRALTY')).toBe(true);
    expect(inspectionMatchesQuery(i, 'ikoyi')).toBe(false);
  });

  it('matches everything on an empty query', () => {
    expect(inspectionMatchesQuery(insp(), '   ')).toBe(true);
  });
});

describe('isSameMonth', () => {
  const now = Date.parse('2026-07-10T00:00:00Z');

  it('is true within the same calendar month', () => {
    expect(isSameMonth('2026-07-01T23:00:00Z', now)).toBe(true);
    expect(isSameMonth('2026-06-30T23:00:00Z', now)).toBe(false);
    expect(isSameMonth('2025-07-10T00:00:00Z', now)).toBe(false);
  });

  it('is false for null or unparseable input', () => {
    expect(isSameMonth(null, now)).toBe(false);
    expect(isSameMonth('nonsense', now)).toBe(false);
  });
});

describe('acceptanceWindow', () => {
  const now = Date.parse('2026-07-10T12:00:00Z');

  it('shows h+m while over an hour remains', () => {
    const w = acceptanceWindow('2026-07-10T13:23:00Z', now);
    expect(w).toEqual({ expired: false, label: '1h 23m left', urgent: false });
  });

  it('shows m+s and flags urgent in the final 15 minutes', () => {
    const w = acceptanceWindow('2026-07-10T12:04:07Z', now);
    expect(w.label).toBe('4m 07s left');
    expect(w.urgent).toBe(true);
    expect(w.expired).toBe(false);
  });

  it('is expired once the window has elapsed', () => {
    expect(acceptanceWindow('2026-07-10T11:59:59Z', now)).toEqual({
      expired: true,
      label: 'Window elapsed',
      urgent: true,
    });
  });
});
