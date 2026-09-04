/**
 * Inspection-report wizard helpers (SCRUM-140, restructured to the designed
 * five sections in SCRUM-204 from Figma 278:3729) — pure + dependency-free so
 * the option lists, validation, and the mapping onto the backend's report
 * fields are unit-testable without React.
 *
 * The backend (POST /inspections/{id}/report, SCRUM-73) stores a fixed set of
 * fields — property_condition (enum), amenities[], discrepancies, remarks, GPS,
 * photos, video — so the wizard's richer answers are composed down to those
 * here rather than requiring a backend contract change.
 */

import type { RealtorInspection } from '@/lib/api';

export const MIN_PHOTOS = 3;

/** The backend caps photos at 5MB (`inspection_photo_max_bytes`). The design
 * says "PNG, JPG up to 10MB each" — we show the real limit, because a UI that
 * promises 10MB just produces uploads the server rejects. */
export const PHOTO_MAX_BYTES = 5 * 1024 * 1024;
export const VIDEO_MAX_BYTES = 50 * 1024 * 1024;

/** The backend sniffs an ISO-BMFF `ftyp` box or WebM magic, which covers MP4,
 * MOV and WebM — so the design's "MP4, MOV up to 50MB" is accurate. */
export const VIDEO_ACCEPT = 'video/mp4,video/quicktime,video/webm';

export type YesNo = 'yes' | 'no';

/** Physical condition rating (Figma 278:3729 Section 2). The backend enum also
 * accepts 'excellent', but the design draws three options and sublabels Good as
 * "Excellent condition" — so excellent is folded into good and left unused
 * rather than shown as a fourth button the design does not have. */
export const CONDITION_OPTIONS = [
  { value: 'good', label: 'Good', hint: 'Excellent condition', tone: 'positive' },
  { value: 'fair', label: 'Fair', hint: 'Acceptable condition', tone: 'caution' },
  { value: 'poor', label: 'Poor', hint: 'Needs work', tone: 'negative' },
] as const;

export type ConditionTone = (typeof CONDITION_OPTIONS)[number]['tone'];

/** The two documents the realtor confirms a physical copy of on site. Keyed so
 * the composed `discrepancies` text names them exactly as the form asked. */
export const DOCUMENT_CHECKS = [
  { key: 'surveyPlan', label: 'Survey Plan' },
  { key: 'certificateOfOccupancy', label: 'Certificate of Occupancy (C of O)' },
] as const;

export type DocumentCheckKey = (typeof DOCUMENT_CHECKS)[number]['key'];

/** Amenities the realtor confirms on site → the backend's `amenities[]`.
 *
 * The design has no amenities picker — it gives Section 2 to the condition
 * rating plus two free-text fields. Kept at the product owner's direction
 * (SCRUM-204): dropping it would silently reduce what the platform captures,
 * and the field is already stored, returned by GET /inspections/{id}/report and
 * rendered on the report detail page. It sits under the condition rating, which
 * is the section it belongs to. */
export const AMENITY_OPTIONS = [
  'Water',
  'Electricity',
  'Road access',
  'Fenced / Walled',
  'Security',
  'Drainage',
] as const;

export interface ReportForm {
  // Section 1 — Property Verification
  propertyExists: YesNo | null;
  descriptionMatches: YesNo | null;
  propertyNotes: string;
  // Section 2 — Condition Assessment
  condition: string;
  amenities: string[];
  environmentalNotes: string;
  accessibility: string;
  // Section 3 — Document Cross-Check
  surveyPlan: YesNo | null;
  certificateOfOccupancy: YesNo | null;
  documentsMatch: YesNo | null;
  // Section 4 — Media Upload
  photos: File[];
  video: File | null;
  // Section 5 — Final Remarks
  finalRemarks: string;
  gps: { lat: number; lng: number } | null;
}

export function emptyReportForm(): ReportForm {
  return {
    propertyExists: null,
    descriptionMatches: null,
    propertyNotes: '',
    condition: '',
    amenities: [],
    environmentalNotes: '',
    accessibility: '',
    surveyPlan: null,
    certificateOfOccupancy: null,
    documentsMatch: null,
    photos: [],
    video: null,
    finalRemarks: '',
    gps: null,
  };
}

export const STEPS = [
  'Property Verification',
  'Condition Assessment',
  'Document Cross-Check',
  'Media Upload',
  'Final Remarks',
] as const;

/** Whether the given wizard step (1-5) is complete enough to advance / submit.
 *
 * Every document question must be answered rather than defaulting to verified:
 * this is a verification document, and a blank answer that reads as "checked"
 * is worse than a blocked Next button. */
export function isStepComplete(step: number, form: ReportForm): boolean {
  switch (step) {
    case 1:
      return form.propertyExists !== null && form.descriptionMatches !== null;
    case 2:
      return form.condition !== '';
    case 3:
      return (
        form.surveyPlan !== null &&
        form.certificateOfOccupancy !== null &&
        form.documentsMatch !== null
      );
    case 4:
      return form.photos.length >= MIN_PHOTOS;
    case 5:
      // The design marks Additional Observations required; GPS is the backend's
      // own precondition (it rejects a report outside 1km of the property).
      return form.finalRemarks.trim() !== '' && form.gps !== null;
    default:
      return false;
  }
}

/** Steps 1-N-1 that are already satisfied — drives the progress checklist and
 * the completed stepper nodes independently of which step is on screen. */
export function completedSteps(form: ReportForm): boolean[] {
  return STEPS.map((_, i) => isStepComplete(i + 1, form));
}

/** Human-readable discrepancies from every negative answer — or null when
 * nothing is amiss (the backend field is optional). */
export function composeDiscrepancies(form: ReportForm): string | null {
  const lines: string[] = [];
  if (form.propertyExists === 'no') {
    lines.push('Property does not exist at the stated location.');
  }
  if (form.descriptionMatches === 'no') {
    lines.push('Property description does not match reality.');
  }
  for (const { key, label } of DOCUMENT_CHECKS) {
    if (form[key] === 'no') lines.push(`${label}: physical document not present.`);
  }
  if (form.documentsMatch === 'no') {
    lines.push('Physical documents do not match the uploaded digital copies.');
  }
  // The note only belongs in discrepancies when something is actually wrong;
  // otherwise it is an observation and rides along in remarks.
  if (lines.length > 0 && form.propertyNotes.trim()) lines.push(form.propertyNotes.trim());
  return lines.length > 0 ? lines.join('\n') : null;
}

/** Free-text remarks composed from the final observations, environment,
 * accessibility, and any notes that were not discrepancies — or null when all
 * are empty. */
export function composeRemarks(form: ReportForm): string | null {
  const lines: string[] = [];
  if (form.finalRemarks.trim()) lines.push(form.finalRemarks.trim());
  if (composeDiscrepancies(form) === null && form.propertyNotes.trim()) {
    lines.push(`Notes: ${form.propertyNotes.trim()}`);
  }
  if (form.environmentalNotes.trim()) lines.push(`Environment: ${form.environmentalNotes.trim()}`);
  if (form.accessibility.trim()) lines.push(`Accessibility: ${form.accessibility.trim()}`);
  return lines.length > 0 ? lines.join('\n') : null;
}

export interface SummaryRow {
  label: string;
  value: string;
  tone: 'positive' | 'caution' | 'negative' | 'neutral';
}

/** The Report Summary panel (Figma Section 5, and the rail's Preview Report).
 * Reads only what has been filled so far, so it is meaningful mid-wizard. */
export function reportSummary(form: ReportForm): SummaryRow[] {
  const yesNo = (v: YesNo | null, good: YesNo = 'yes'): SummaryRow['tone'] =>
    v === null ? 'neutral' : v === good ? 'positive' : 'negative';
  const condition = CONDITION_OPTIONS.find((o) => o.value === form.condition);
  const docsAnswered =
    form.surveyPlan !== null && form.certificateOfOccupancy !== null && form.documentsMatch !== null;
  const docsClean =
    form.surveyPlan === 'yes' && form.certificateOfOccupancy === 'yes' && form.documentsMatch === 'yes';

  return [
    {
      label: 'Property Exists',
      value: form.propertyExists === null ? '—' : form.propertyExists === 'yes' ? 'Yes' : 'No',
      tone: yesNo(form.propertyExists),
    },
    {
      label: 'Description Matches',
      value:
        form.descriptionMatches === null ? '—' : form.descriptionMatches === 'yes' ? 'Yes' : 'No',
      tone: yesNo(form.descriptionMatches),
    },
    {
      label: 'Condition Rating',
      value: condition?.label ?? '—',
      tone: condition?.tone ?? 'neutral',
    },
    {
      label: 'Photos Uploaded',
      value: String(form.photos.length),
      tone: form.photos.length >= MIN_PHOTOS ? 'positive' : 'neutral',
    },
    {
      label: 'Documents Verified',
      value: !docsAnswered ? '—' : docsClean ? 'Match' : 'Discrepancy',
      tone: !docsAnswered ? 'neutral' : docsClean ? 'positive' : 'negative',
    },
  ];
}

export type SubmittableCheck =
  | { ok: true }
  | { ok: false; reason: 'not_accepted' | 'too_early'; opensAt?: string };

/** Whether a report can be submitted for this inspection right now — it must be
 * accepted and on/after the confirmed inspection date (mirrors the backend
 * guards so the UI can explain the gate instead of surprising the realtor with a
 * 409/422). */
export function reportSubmittable(
  insp: RealtorInspection,
  now: number = Date.now(),
): SubmittableCheck {
  if (insp.status === 'completed') return { ok: false, reason: 'not_accepted' };
  if (insp.status !== 'accepted' && insp.status !== 'rescheduled') {
    return { ok: false, reason: 'not_accepted' };
  }
  if (insp.confirmed_date && now < Date.parse(insp.confirmed_date)) {
    return { ok: false, reason: 'too_early', opensAt: insp.confirmed_date };
  }
  return { ok: true };
}
