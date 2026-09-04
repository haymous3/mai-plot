import { describe, expect, it } from 'vitest';

import type { RealtorInspection } from './api';
import {
  composeDiscrepancies,
  composeRemarks,
  emptyReportForm,
  isStepComplete,
  reportSubmittable,
  type ReportForm,
} from './inspection-report';

function fakePhotos(n: number): File[] {
  // isStepComplete only reads .length, so lightweight stand-ins suffice.
  return Array.from({ length: n }, () => ({}) as File);
}

function insp(overrides: Partial<RealtorInspection> = {}): RealtorInspection {
  return {
    inspection_id: 'i1',
    transaction_id: 't1',
    status: 'accepted',
    proposed_date: '2026-07-10T09:00:00Z',
    confirmed_date: '2026-07-10T09:00:00Z',
    assignment_expires_at: '2026-07-09T11:00:00Z',
    created_at: '2026-07-09T09:00:00Z',
    report_submitted_at: null,
    buyer_ref: 'b1a2c3d4',
    inspection_ref: 'i1a2c3d4',
    property_title: 'Plot 5',
    address_text: '1 Way',
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

describe('emptyReportForm', () => {
  it('defaults every document check to verified and starts with no photos/GPS', () => {
    const f = emptyReportForm();
    expect(Object.values(f.docChecks).every((s) => s === 'verified')).toBe(true);
    expect(f.photos).toEqual([]);
    expect(f.gps).toBeNull();
  });
});

describe('isStepComplete', () => {
  it('gates step 1 on the property-match answer', () => {
    expect(isStepComplete(1, emptyReportForm())).toBe(false);
    expect(isStepComplete(1, { ...emptyReportForm(), propertyMatches: 'yes' })).toBe(true);
  });

  it('requires at least 3 photos on step 4', () => {
    expect(isStepComplete(4, { ...emptyReportForm(), photos: fakePhotos(2) })).toBe(false);
    expect(isStepComplete(4, { ...emptyReportForm(), photos: fakePhotos(3) })).toBe(true);
  });

  it('requires captured GPS on step 5', () => {
    expect(isStepComplete(5, emptyReportForm())).toBe(false);
    expect(isStepComplete(5, { ...emptyReportForm(), gps: { lat: 6.5, lng: 3.4 } })).toBe(true);
  });
});

describe('composeDiscrepancies', () => {
  it('is null when the property matches and all documents are verified', () => {
    expect(composeDiscrepancies({ ...emptyReportForm(), propertyMatches: 'yes' })).toBeNull();
  });

  it('captures a property mismatch and per-document problems', () => {
    const form: ReportForm = {
      ...emptyReportForm(),
      propertyMatches: 'no',
      propertyNotes: 'Wrong plot size',
      docChecks: {
        ...emptyReportForm().docChecks,
        'Survey Plan': 'not_present',
        'Deed of Assignment': 'mismatch',
      },
    };
    const out = composeDiscrepancies(form);
    expect(out).toContain('Property does not match the listing: Wrong plot size');
    expect(out).toContain('Survey Plan: not present.');
    expect(out).toContain('Deed of Assignment: does not match records.');
  });
});

describe('composeRemarks', () => {
  it('is null when nothing was written', () => {
    expect(composeRemarks(emptyReportForm())).toBeNull();
  });

  it('joins final remarks, environment, and accessibility', () => {
    const out = composeRemarks({
      ...emptyReportForm(),
      finalRemarks: 'Solid buy',
      environmentalNotes: 'Quiet street',
      accessibility: 'easy',
    });
    expect(out).toContain('Solid buy');
    expect(out).toContain('Environment: Quiet street');
    expect(out).toContain('Accessibility: Easy access.');
  });
});

describe('reportSubmittable', () => {
  const now = Date.parse('2026-07-11T00:00:00Z');

  it('allows an accepted inspection on/after the confirmed date', () => {
    expect(reportSubmittable(insp(), now)).toEqual({ ok: true });
  });

  it('blocks before the confirmed date as too_early', () => {
    const r = reportSubmittable(insp({ confirmed_date: '2026-07-20T09:00:00Z' }), now);
    expect(r).toEqual({ ok: false, reason: 'too_early', opensAt: '2026-07-20T09:00:00Z' });
  });

  it('blocks a pending or completed inspection as not_accepted', () => {
    expect(reportSubmittable(insp({ status: 'pending' }), now).ok).toBe(false);
    expect(reportSubmittable(insp({ status: 'completed' }), now)).toEqual({
      ok: false,
      reason: 'not_accepted',
    });
  });
});
