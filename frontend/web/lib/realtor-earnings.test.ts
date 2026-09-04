import { describe, expect, it } from 'vitest';

import type { CommissionHistoryItem, CommissionSummary } from './api';
import {
  commissionRateLabel,
  commissionStatusMeta,
  commissionsToCsv,
  earningsBalances,
  filterCommissions,
} from './realtor-earnings';

function commission(overrides: Partial<CommissionHistoryItem> = {}): CommissionHistoryItem {
  return {
    commission_id: 'c1a2b3c4-0000-0000-0000-000000000000',
    transaction_id: 't1a2b3c4-0000-0000-0000-000000000000',
    amount_kobo: 5_000_000,
    rate_bps: 200,
    status: 'withdrawn',
    created_at: '2026-07-01T09:00:00Z',
    available_at: '2026-07-04T09:00:00Z',
    disbursed_at: '2026-07-05T09:00:00Z',
    property_title: 'Plot 5, Lekki',
    ...overrides,
  };
}

const summary: CommissionSummary = {
  pending_kobo: 100_000,
  available_kobo: 250_000,
  withdrawn_kobo: 1_000_000,
};

describe('earningsBalances', () => {
  it('totals all three states', () => {
    expect(earningsBalances(summary, []).totalKobo).toBe(1_350_000);
  });

  it('groups available with pending — it is money not yet paid', () => {
    const b = earningsBalances(summary, []);
    expect(b.paidKobo).toBe(1_000_000);
    expect(b.outstandingKobo).toBe(350_000);
    expect(b.availableKobo).toBe(250_000);
  });

  it('counts paid and outstanding rows separately', () => {
    const b = earningsBalances(summary, [
      commission({ status: 'withdrawn' }),
      commission({ commission_id: 'c2', status: 'available' }),
      commission({ commission_id: 'c3', status: 'pending' }),
    ]);
    expect(b.paidCount).toBe(1);
    expect(b.outstandingCount).toBe(2);
  });

  it('is all zeroes when the summary could not be read', () => {
    expect(earningsBalances(null, [])).toEqual({
      totalKobo: 0,
      paidKobo: 0,
      paidCount: 0,
      outstandingKobo: 0,
      outstandingCount: 0,
      availableKobo: 0,
    });
  });
});

describe('commissionStatusMeta', () => {
  it('labels the three real states', () => {
    expect(commissionStatusMeta('withdrawn').label).toBe('Paid');
    expect(commissionStatusMeta('available').label).toBe('Available');
    expect(commissionStatusMeta('pending').label).toBe('Pending');
  });

  it('marks only a withdrawn commission as actually paid out', () => {
    expect(commissionStatusMeta('withdrawn').paid).toBe(true);
    expect(commissionStatusMeta('available').paid).toBe(false);
    expect(commissionStatusMeta('pending').paid).toBe(false);
  });

  it('never emits a stock amber/blue/green class', () => {
    for (const s of ['withdrawn', 'available', 'pending', 'nonsense']) {
      expect(commissionStatusMeta(s).pill).not.toMatch(/\b(amber|blue|green)-\d/);
    }
  });
});

describe('filterCommissions', () => {
  const items = [
    commission({ commission_id: 'a', status: 'withdrawn' }),
    commission({ commission_id: 'b', status: 'available' }),
    commission({ commission_id: 'c', status: 'pending' }),
  ];

  it('returns everything for all', () => {
    expect(filterCommissions(items, 'all')).toHaveLength(3);
  });

  it('selects a single status', () => {
    expect(filterCommissions(items, 'available').map((c) => c.commission_id)).toEqual(['b']);
  });
});

describe('commissionRateLabel', () => {
  it('reads the rate from the rows rather than hard-coding it', () => {
    expect(commissionRateLabel([commission({ rate_bps: 250 })])).toBe('2.50%');
    expect(commissionRateLabel([commission({ rate_bps: 200 })])).toBe('2%');
  });

  it('says Varies when rows disagree', () => {
    expect(
      commissionRateLabel([commission({ rate_bps: 200 }), commission({ rate_bps: 300 })]),
    ).toBe('Varies');
  });

  it('falls back to the platform default with no history', () => {
    expect(commissionRateLabel([])).toBe('2%');
  });
});

describe('commissionsToCsv', () => {
  it('emits a header and one row per commission', () => {
    const lines = commissionsToCsv([commission()]).split('\r\n');
    expect(lines).toHaveLength(2);
    expect(lines[0]).toContain('Amount (NGN)');
    expect(lines[0]).toContain('Amount (kobo)');
  });

  it('keeps kobo alongside naira so the file reconciles exactly', () => {
    const row = commissionsToCsv([commission({ amount_kobo: 5_000_050 })]).split('\r\n')[1];
    expect(row).toContain('50000.50');
    expect(row).toContain('5000050');
  });

  it('quotes a title containing a comma so columns do not shift', () => {
    const row = commissionsToCsv([commission({ property_title: 'Plot 5, Lekki' })]).split('\r\n')[1];
    expect(row).toContain('"Plot 5, Lekki"');
    // 9 columns means 8 separating commas outside the quoted cell.
    expect(row.replace('"Plot 5, Lekki"', 'X').split(',')).toHaveLength(9);
  });

  it('escapes an embedded quote by doubling it', () => {
    const row = commissionsToCsv([commission({ property_title: 'The "Rock" House' })]).split(
      '\r\n',
    )[1];
    expect(row).toContain('"The ""Rock"" House"');
  });

  it('renders a missing title and an undisbursed date as empty cells', () => {
    const row = commissionsToCsv([
      commission({ property_title: null, disbursed_at: null, status: 'pending' }),
    ]).split('\r\n')[1];
    expect(row).toContain(',,');
    expect(row.endsWith(',')).toBe(true);
  });
});
