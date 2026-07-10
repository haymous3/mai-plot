/**
 * Inspection-report wizard helpers (SCRUM-140, PR3) — pure + dependency-free so
 * the 5-step form's option lists, validation, and the mapping onto the backend's
 * report fields are unit-testable without React.
 *
 * The backend (POST /inspections/{id}/report, SCRUM-73) stores a fixed set of
 * fields — property_condition (enum), amenities[], discrepancies, remarks, GPS,
 * photos — so the wizard's richer answers are composed down to those here rather
 * than requiring a backend contract change.
 */

import type { RealtorInspection } from '@/lib/api';

export const MIN_PHOTOS = 3;
export const PHOTO_MAX_BYTES = 5 * 1024 * 1024;

/** property_condition enum accepted by the backend (_VALID_CONDITIONS). */
export const CONDITION_OPTIONS = [
  { value: 'excellent', label: 'Excellent' },
  { value: 'good', label: 'Good' },
  { value: 'fair', label: 'Fair' },
  { value: 'poor', label: 'Poor' },
] as const;

/** Property amenities the realtor confirms on site → `amenities[]`. */
export const AMENITY_OPTIONS = [
  'Water',
  'Electricity',
  'Road access',
  'Fenced / Walled',
  'Security',
  'Drainage',
] as const;

export const ACCESSIBILITY_OPTIONS = [
  { value: 'easy', label: 'Easy access' },
  { value: 'moderate', label: 'Moderate access' },
  { value: 'difficult', label: 'Difficult access' },
] as const;

/** Documents cross-checked on site; each gets a status → composed into
 * `discrepancies` when anything is amiss. */
export const DOCUMENT_CHECK_ITEMS = [
  'Certificate of Occupancy',
  'Survey Plan',
  'Deed of Assignment',
  "Governor's Consent",
  'Purchase Receipt',
] as const;

export type DocCheckStatus = 'verified' | 'not_present' | 'mismatch';

export const DOC_STATUS_LABELS: Record<DocCheckStatus, string> = {
  verified: 'Verified',
  not_present: 'Not present',
  mismatch: 'Mismatch',
};

export interface ReportForm {
  propertyMatches: 'yes' | 'no' | null;
  propertyNotes: string;
  condition: string;
  amenities: string[];
  environmentalNotes: string;
  accessibility: string;
  docChecks: Record<string, DocCheckStatus>;
  docNotes: string;
  photos: File[];
  finalRemarks: string;
  gps: { lat: number; lng: number } | null;
}

export function emptyReportForm(): ReportForm {
  const docChecks: Record<string, DocCheckStatus> = {};
  for (const item of DOCUMENT_CHECK_ITEMS) docChecks[item] = 'verified';
  return {
    propertyMatches: null,
    propertyNotes: '',
    condition: '',
    amenities: [],
    environmentalNotes: '',
    accessibility: '',
    docChecks,
    docNotes: '',
    photos: [],
    finalRemarks: '',
    gps: null,
  };
}

/** Whether the given wizard step (1-5) is complete enough to advance / submit. */
export function isStepComplete(step: number, form: ReportForm): boolean {
  switch (step) {
    case 1:
      return form.propertyMatches !== null;
    case 2:
      return form.condition !== '';
    case 3:
      return true; // doc checks default to Verified; realtor adjusts as needed
    case 4:
      return form.photos.length >= MIN_PHOTOS;
    case 5:
      return form.gps !== null;
    default:
      return false;
  }
}

/** Human-readable discrepancies string from the property-match answer + the
 * document cross-check — or null when nothing is amiss (backend field is
 * optional). */
export function composeDiscrepancies(form: ReportForm): string | null {
  const lines: string[] = [];
  if (form.propertyMatches === 'no') {
    lines.push(
      `Property does not match the listing${form.propertyNotes.trim() ? `: ${form.propertyNotes.trim()}` : '.'}`,
    );
  }
  for (const item of DOCUMENT_CHECK_ITEMS) {
    const status = form.docChecks[item];
    if (status === 'not_present') lines.push(`${item}: not present.`);
    else if (status === 'mismatch') lines.push(`${item}: does not match records.`);
  }
  if (form.docNotes.trim()) lines.push(form.docNotes.trim());
  return lines.length > 0 ? lines.join('\n') : null;
}

/** Free-text remarks composed from the environmental notes, accessibility, and
 * the realtor's final remarks — or null when all empty. */
export function composeRemarks(form: ReportForm): string | null {
  const lines: string[] = [];
  if (form.finalRemarks.trim()) lines.push(form.finalRemarks.trim());
  if (form.environmentalNotes.trim()) lines.push(`Environment: ${form.environmentalNotes.trim()}`);
  if (form.accessibility) {
    const label = ACCESSIBILITY_OPTIONS.find((o) => o.value === form.accessibility)?.label;
    if (label) lines.push(`Accessibility: ${label}.`);
  }
  return lines.length > 0 ? lines.join('\n') : null;
}

export type SubmittableCheck =
  | { ok: true }
  | { ok: false; reason: 'not_accepted' | 'too_early'; opensAt?: string };

/** Whether a report can be submitted for this inspection right now — it must be
 * accepted and on/after the confirmed inspection date (mirrors the backend
 * guards so the UI can explain the gate instead of surprising the realtor with a
 * 409/422). */
export function reportSubmittable(insp: RealtorInspection, now: number = Date.now()): SubmittableCheck {
  if (insp.status === 'completed') return { ok: false, reason: 'not_accepted' };
  if (insp.status !== 'accepted' && insp.status !== 'rescheduled') {
    return { ok: false, reason: 'not_accepted' };
  }
  if (insp.confirmed_date && now < Date.parse(insp.confirmed_date)) {
    return { ok: false, reason: 'too_early', opensAt: insp.confirmed_date };
  }
  return { ok: true };
}
