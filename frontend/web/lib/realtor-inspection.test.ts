import { describe, expect, it } from 'vitest';

import type { RealtorInspection } from './api';
import {
  acceptanceWindow,
  countInspections,
  filterInspections,
  inspectionLocation,
  inspectionLocationLines,
  inspectionMatchesQuery,
  inspectionStatusMeta,
  isAwaitingAcceptance,
  isDistressSale,
  isSameMonth,
  propertyTypeLabel,
  relativeTime,
  upcomingInspections,
  upcomingTodayCount,
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


// -- SCRUM-204: the designed table's helpers ---------------------------------

describe('inspectionStatusMeta labels (SCRUM-204)', () => {
  it('uses the three labels the design draws', () => {
    expect(inspectionStatusMeta('pending').label).toBe('Pending');
    expect(inspectionStatusMeta('accepted').label).toBe('Scheduled');
    expect(inspectionStatusMeta('completed').label).toBe('Completed');
  });

  it('keeps Rescheduled distinct but counts it as Scheduled', () => {
    const meta = inspectionStatusMeta('rescheduled');
    expect(meta.label).toBe('Rescheduled');
    expect(meta.bucket).toBe('scheduled');
    // Same treatment as accepted, so the tiles still read as four states.
    expect(meta.pill).toBe(inspectionStatusMeta('accepted').pill);
  });

  it('never emits a stock amber/blue/green class', () => {
    // Those render Tailwind v3.4 values; the design is drawn against v4.
    for (const s of ['pending', 'accepted', 'rescheduled', 'completed', 'nonsense']) {
      expect(inspectionStatusMeta(s).pill).not.toMatch(/\b(amber|blue|green)-\d/);
    }
  });
});

describe('inspectionLocationLines', () => {
  it('splits the address from the LGA + state', () => {
    expect(inspectionLocationLines(insp())).toEqual({
      primary: '1 Admiralty Way',
      secondary: 'Eti-Osa, Lagos',
    });
  });

  it('omits an absent secondary line rather than trailing a comma', () => {
    expect(inspectionLocationLines(insp({ lga: null, state: null }))).toEqual({
      primary: '1 Admiralty Way',
      secondary: '',
    });
  });

  it('falls back only when the listing has no location at all', () => {
    expect(
      inspectionLocationLines(insp({ address_text: null, lga: null, state: null })),
    ).toEqual({ primary: 'Location unavailable', secondary: '' });
  });

  it('leaves the primary blank when only the LGA is known', () => {
    // The row still reads correctly — it just shows one line, not a placeholder.
    expect(inspectionLocationLines(insp({ address_text: null }))).toEqual({
      primary: '',
      secondary: 'Eti-Osa, Lagos',
    });
  });
});

describe('propertyTypeLabel', () => {
  it('maps the backend vocabulary', () => {
    expect(propertyTypeLabel('land')).toBe('Land');
    expect(propertyTypeLabel('residential')).toBe('House');
    expect(propertyTypeLabel('commercial')).toBe('Commercial');
  });

  it('passes an unknown type through instead of inventing one', () => {
    expect(propertyTypeLabel('villa')).toBe('villa');
  });

  it('is null when the listing is gone', () => {
    expect(propertyTypeLabel(null)).toBeNull();
  });
});

describe('isDistressSale', () => {
  it('is true only for a distress listing', () => {
    expect(isDistressSale(insp({ sale_type: 'distress' }))).toBe(true);
    expect(isDistressSale(insp({ sale_type: 'normal' }))).toBe(false);
    expect(isDistressSale(insp({ sale_type: null }))).toBe(false);
  });
});

describe('inspectionMatchesQuery covers the reference ids', () => {
  it('matches on inspection ref, buyer ref, title and location', () => {
    const i = insp({ inspection_ref: 'a1b2c3d4', buyer_ref: '9f8e7d6c' });
    expect(inspectionMatchesQuery(i, 'a1b2')).toBe(true);
    expect(inspectionMatchesQuery(i, '9F8E')).toBe(true);
    expect(inspectionMatchesQuery(i, 'lekki')).toBe(true);
    expect(inspectionMatchesQuery(i, 'admiralty')).toBe(true);
    expect(inspectionMatchesQuery(i, 'zzz')).toBe(false);
  });
});

describe('filterInspections', () => {
  const items = [
    insp({ status: 'pending', property_title: 'Plot A' }),
    insp({ status: 'accepted', property_title: 'Plot B' }),
    insp({ status: 'rescheduled', property_title: 'Plot C' }),
    insp({ status: 'completed', property_title: 'Villa D' }),
  ];

  it('returns everything by default', () => {
    expect(filterInspections(items, { query: '', status: 'all' })).toHaveLength(4);
  });

  it('groups rescheduled with scheduled', () => {
    const rows = filterInspections(items, { query: '', status: 'scheduled' });
    expect(rows.map((r) => r.property_title)).toEqual(['Plot B', 'Plot C']);
  });

  it('applies the query and the status together', () => {
    expect(filterInspections(items, { query: 'plot', status: 'completed' })).toEqual([]);
    expect(
      filterInspections(items, { query: 'villa', status: 'completed' }).map(
        (r) => r.property_title,
      ),
    ).toEqual(['Villa D']);
  });

  it('preserves the caller ordering', () => {
    const rows = filterInspections(items, { query: 'plot', status: 'all' });
    expect(rows.map((r) => r.property_title)).toEqual(['Plot A', 'Plot B', 'Plot C']);
  });
});


// -- SCRUM-204 PR4: dashboard helpers ---------------------------------------

describe('upcomingTodayCount', () => {
  const now = Date.parse('2026-07-10T12:00:00Z');

  it('counts only inspections scheduled today', () => {
    const items = [
      insp({ status: 'accepted', confirmed_date: '2026-07-10T09:00:00Z' }),
      insp({ status: 'accepted', confirmed_date: '2026-07-10T16:00:00Z' }),
      insp({ status: 'accepted', confirmed_date: '2026-07-11T09:00:00Z' }),
    ];
    expect(upcomingTodayCount(items, now)).toBe(2);
  });

  it('uses the market day, not the runtime timezone', () => {
    // 23:30 UTC on the 10th is already 00:30 on the 11th in Lagos (UTC+1), so
    // it is tomorrow for the realtor no matter where the server runs.
    const i = insp({ status: 'accepted', confirmed_date: '2026-07-10T23:30:00Z' });
    expect(upcomingTodayCount([i], now)).toBe(0);

    // And 23:30 UTC on the 9th is 00:30 on the 10th in Lagos — today.
    const j = insp({ status: 'accepted', confirmed_date: '2026-07-09T23:30:00Z' });
    expect(upcomingTodayCount([j], now)).toBe(1);
  });

  it('prefers the confirmed date over the proposed one', () => {
    // Proposed today but confirmed for tomorrow — the realtor turns up tomorrow.
    const i = insp({
      status: 'accepted',
      proposed_date: '2026-07-10T09:00:00Z',
      confirmed_date: '2026-07-11T09:00:00Z',
    });
    expect(upcomingTodayCount([i], now)).toBe(0);
  });

  it('falls back to the proposed date when nothing is confirmed', () => {
    const i = insp({ status: 'pending', proposed_date: '2026-07-10T09:00:00Z', confirmed_date: null });
    expect(upcomingTodayCount([i], now)).toBe(1);
  });

  it('excludes an inspection already reported — that is not upcoming', () => {
    const i = insp({ status: 'completed', confirmed_date: '2026-07-10T09:00:00Z' });
    expect(upcomingTodayCount([i], now)).toBe(0);
  });

  it('ignores an unparseable date rather than counting it', () => {
    const i = insp({ status: 'accepted', confirmed_date: 'nonsense' });
    expect(upcomingTodayCount([i], now)).toBe(0);
  });
});

describe('relativeTime', () => {
  const now = Date.parse('2026-07-10T12:00:00Z');

  it('describes recent moments in the units the feed uses', () => {
    expect(relativeTime('2026-07-10T11:59:30Z', now)).toBe('just now');
    expect(relativeTime('2026-07-10T11:59:00Z', now)).toBe('1 minute ago');
    expect(relativeTime('2026-07-10T11:30:00Z', now)).toBe('30 minutes ago');
    expect(relativeTime('2026-07-10T10:00:00Z', now)).toBe('2 hours ago');
    expect(relativeTime('2026-07-07T12:00:00Z', now)).toBe('3 days ago');
  });

  it('rolls up to months and years', () => {
    expect(relativeTime('2026-05-10T12:00:00Z', now)).toBe('2 months ago');
    expect(relativeTime('2024-07-10T12:00:00Z', now)).toBe('2 years ago');
  });

  it('never renders a negative age for a clock-skewed future timestamp', () => {
    expect(relativeTime('2026-07-10T12:05:00Z', now)).toBe('just now');
  });

  it('is an em-dash for an unparseable timestamp', () => {
    expect(relativeTime('nonsense', now)).toBe('—');
  });
});
