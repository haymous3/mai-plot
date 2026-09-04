import { describe, expect, it } from 'vitest';

import type { RealtorInspection } from './api';
import {
  completedSteps,
  composeDiscrepancies,
  composeRemarks,
  emptyReportForm,
  isStepComplete,
  reportSubmittable,
  reportSummary,
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

/** A form filled the way a clean inspection would be. */
function clean(overrides: Partial<ReportForm> = {}): ReportForm {
  return {
    ...emptyReportForm(),
    propertyExists: 'yes',
    descriptionMatches: 'yes',
    condition: 'good',
    surveyPlan: 'yes',
    certificateOfOccupancy: 'yes',
    documentsMatch: 'yes',
    photos: fakePhotos(3),
    finalRemarks: 'All in order.',
    gps: { lat: 6.5, lng: 3.4 },
    ...overrides,
  };
}

describe('emptyReportForm', () => {
  it('starts with every answer unset — nothing defaults to a passing verification', () => {
    const f = emptyReportForm();
    expect(f.propertyExists).toBeNull();
    expect(f.descriptionMatches).toBeNull();
    expect(f.surveyPlan).toBeNull();
    expect(f.certificateOfOccupancy).toBeNull();
    expect(f.documentsMatch).toBeNull();
    expect(f.condition).toBe('');
    expect(f.photos).toEqual([]);
    expect(f.video).toBeNull();
    expect(f.gps).toBeNull();
  });
});

describe('isStepComplete', () => {
  it('step 1 needs BOTH property questions', () => {
    const f = emptyReportForm();
    expect(isStepComplete(1, f)).toBe(false);
    expect(isStepComplete(1, { ...f, propertyExists: 'yes' })).toBe(false);
    expect(isStepComplete(1, { ...f, propertyExists: 'yes', descriptionMatches: 'no' })).toBe(true);
  });

  it('step 2 needs a condition', () => {
    expect(isStepComplete(2, emptyReportForm())).toBe(false);
    expect(isStepComplete(2, { ...emptyReportForm(), condition: 'fair' })).toBe(true);
  });

  it('step 3 needs all three document answers — none default to verified', () => {
    const f = emptyReportForm();
    expect(isStepComplete(3, f)).toBe(false);
    expect(isStepComplete(3, { ...f, surveyPlan: 'yes', certificateOfOccupancy: 'yes' })).toBe(
      false,
    );
    expect(
      isStepComplete(3, {
        ...f,
        surveyPlan: 'yes',
        certificateOfOccupancy: 'no',
        documentsMatch: 'yes',
      }),
    ).toBe(true);
  });

  it('step 4 needs the photo minimum', () => {
    expect(isStepComplete(4, { ...emptyReportForm(), photos: fakePhotos(2) })).toBe(false);
    expect(isStepComplete(4, { ...emptyReportForm(), photos: fakePhotos(3) })).toBe(true);
  });

  it('step 5 needs observations AND a GPS fix', () => {
    const base = emptyReportForm();
    expect(isStepComplete(5, { ...base, finalRemarks: 'x' })).toBe(false);
    expect(isStepComplete(5, { ...base, gps: { lat: 1, lng: 2 } })).toBe(false);
    expect(isStepComplete(5, { ...base, finalRemarks: 'x', gps: { lat: 1, lng: 2 } })).toBe(true);
  });

  it('treats whitespace-only observations as unfilled', () => {
    expect(
      isStepComplete(5, { ...emptyReportForm(), finalRemarks: '   ', gps: { lat: 1, lng: 2 } }),
    ).toBe(false);
  });
});

describe('completedSteps', () => {
  it('flags every satisfied step regardless of which is on screen', () => {
    expect(completedSteps(clean())).toEqual([true, true, true, true, true]);
    expect(completedSteps(emptyReportForm())).toEqual([false, false, false, false, false]);
  });
});

describe('composeDiscrepancies', () => {
  it('is null when nothing is amiss', () => {
    expect(composeDiscrepancies(clean())).toBeNull();
  });

  it('names each failing check', () => {
    const out = composeDiscrepancies(
      clean({ propertyExists: 'no', certificateOfOccupancy: 'no', documentsMatch: 'no' }),
    );
    expect(out).toContain('Property does not exist at the stated location.');
    expect(out).toContain('Certificate of Occupancy (C of O): physical document not present.');
    expect(out).toContain('do not match the uploaded digital copies');
    // A passing check is never mentioned.
    expect(out).not.toContain('Survey Plan');
  });

  it('appends the note only when something is actually wrong', () => {
    expect(composeDiscrepancies(clean({ propertyNotes: 'Fence is new.' }))).toBeNull();
    expect(
      composeDiscrepancies(clean({ descriptionMatches: 'no', propertyNotes: 'Fence is new.' })),
    ).toContain('Fence is new.');
  });
});

describe('composeRemarks', () => {
  it('is null when everything is empty', () => {
    expect(composeRemarks(emptyReportForm())).toBeNull();
  });

  it('carries the note into remarks when it was not a discrepancy', () => {
    expect(composeRemarks(clean({ propertyNotes: 'Fence is new.' }))).toContain(
      'Notes: Fence is new.',
    );
  });

  it('does not duplicate the note that already went to discrepancies', () => {
    const form = clean({ descriptionMatches: 'no', propertyNotes: 'Fence is new.' });
    expect(composeDiscrepancies(form)).toContain('Fence is new.');
    expect(composeRemarks(form)).not.toContain('Notes: Fence is new.');
  });

  it('labels the environment and accessibility free text', () => {
    const out = composeRemarks(
      clean({ environmentalNotes: 'Near a creek.', accessibility: 'Tarred road.' }),
    );
    expect(out).toContain('Environment: Near a creek.');
    expect(out).toContain('Accessibility: Tarred road.');
  });
});

describe('reportSummary', () => {
  it('reads em-dashes and neutral tone before anything is answered', () => {
    const rows = reportSummary(emptyReportForm());
    expect(rows.map((r) => r.value)).toEqual(['—', '—', '—', '0', '—']);
    expect(rows.every((r) => r.tone === 'neutral')).toBe(true);
  });

  it('summarises a clean inspection', () => {
    const rows = reportSummary(clean());
    expect(rows.map((r) => `${r.label}=${r.value}`)).toEqual([
      'Property Exists=Yes',
      'Description Matches=Yes',
      'Condition Rating=Good',
      'Photos Uploaded=3',
      'Documents Verified=Match',
    ]);
    expect(rows.every((r) => r.tone === 'positive')).toBe(true);
  });

  it('reports a document discrepancy once every question is answered', () => {
    const docs = reportSummary(clean({ surveyPlan: 'no' })).find(
      (r) => r.label === 'Documents Verified',
    );
    expect(docs).toEqual({ label: 'Documents Verified', value: 'Discrepancy', tone: 'negative' });
  });

  it('stays neutral on documents while any question is unanswered', () => {
    const rows = reportSummary(clean({ documentsMatch: null }));
    expect(rows.find((r) => r.label === 'Documents Verified')?.value).toBe('—');
  });

  it('carries the condition tone so Fair reads amber, not green', () => {
    expect(
      reportSummary(clean({ condition: 'fair' })).find((r) => r.label === 'Condition Rating'),
    ).toEqual({ label: 'Condition Rating', value: 'Fair', tone: 'caution' });
    expect(
      reportSummary(clean({ condition: 'poor' })).find((r) => r.label === 'Condition Rating'),
    ).toEqual({ label: 'Condition Rating', value: 'Poor', tone: 'negative' });
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
