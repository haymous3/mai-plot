'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import {
  ACCESSIBILITY_OPTIONS,
  AMENITY_OPTIONS,
  CONDITION_OPTIONS,
  composeDiscrepancies,
  composeRemarks,
  DOCUMENT_CHECK_ITEMS,
  DOC_STATUS_LABELS,
  emptyReportForm,
  isStepComplete,
  MIN_PHOTOS,
  PHOTO_MAX_BYTES,
  type DocCheckStatus,
  type ReportForm,
} from '@/lib/inspection-report';

const STEPS = ['Property', 'Condition', 'Documents', 'Media', 'Remarks'] as const;

const SUBMIT_ERRORS: Record<string, string> = {
  MIN_PHOTOS_REQUIRED: `At least ${MIN_PHOTOS} photos are required.`,
  GPS_OUT_OF_RANGE: "Your location isn't within 1km of the property — capture GPS on site.",
  REPORT_TOO_EARLY: "The report can't be submitted before the confirmed inspection date.",
  REPORT_NOT_SUBMITTABLE: 'This inspection has already been reported, or is not accepted.',
  CONDITION_INVALID: 'Please choose a valid property condition.',
  NOT_ASSIGNED_REALTOR: 'This inspection is not assigned to you.',
  COORDINATES_INVALID: 'The captured GPS coordinates are invalid — recapture and retry.',
  STORAGE_UNAVAILABLE: 'Photo storage is temporarily unavailable. Please retry.',
};

/** 5-step inspection report wizard (SCRUM-140, PR3). Captures the checklist +
 * GPS + photos and posts multipart to /api/realtor/inspections/[id]/report. The
 * rich answers are composed onto the backend's fixed report fields. */
export function ReportWizard({ inspectionId }: { inspectionId: string }) {
  const [form, setForm] = useState<ReportForm>(emptyReportForm);
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gpsBusy, setGpsBusy] = useState(false);
  const [gpsError, setGpsError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const previews = useMemo(() => form.photos.map((p) => URL.createObjectURL(p)), [form.photos]);
  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews]);

  function patch(p: Partial<ReportForm>) {
    setForm((f) => ({ ...f, ...p }));
  }

  function addPhotos(files: FileList | null) {
    if (!files) return;
    const accepted: File[] = [];
    let rejected = false;
    for (const f of Array.from(files)) {
      if (!f.type.startsWith('image/') || f.size > PHOTO_MAX_BYTES) rejected = true;
      else accepted.push(f);
    }
    setError(rejected ? 'Some files were skipped — photos must be images under 5MB.' : null);
    patch({ photos: [...form.photos, ...accepted] });
  }

  function removePhoto(idx: number) {
    patch({ photos: form.photos.filter((_, i) => i !== idx) });
  }

  function captureGps() {
    setGpsError(null);
    if (!('geolocation' in navigator)) {
      setGpsError('Geolocation is not available on this device.');
      return;
    }
    setGpsBusy(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        patch({ gps: { lat: pos.coords.latitude, lng: pos.coords.longitude } });
        setGpsBusy(false);
      },
      () => {
        setGpsError('Could not read your location. Enable location access and try again.');
        setGpsBusy(false);
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }

  async function submit() {
    if (!form.gps) return;
    setBusy(true);
    setError(null);
    const fd = new FormData();
    fd.append('gps_lat', String(form.gps.lat));
    fd.append('gps_lng', String(form.gps.lng));
    fd.append('property_condition', form.condition);
    for (const a of form.amenities) fd.append('amenities', a);
    const discrepancies = composeDiscrepancies(form);
    if (discrepancies) fd.append('discrepancies', discrepancies);
    const remarks = composeRemarks(form);
    if (remarks) fd.append('remarks', remarks);
    for (const p of form.photos) fd.append('photos', p);

    try {
      const resp = await fetch(`/api/realtor/inspections/${inspectionId}/report`, {
        method: 'POST',
        body: fd,
      });
      if (resp.ok) {
        setSubmitted(true);
        return;
      }
      const body = (await resp.json().catch(() => ({}))) as { error_code?: string };
      setError(SUBMIT_ERRORS[body.error_code ?? ''] ?? 'Could not submit the report. Please retry.');
      setBusy(false);
    } catch {
      setError('Network error. Please retry.');
      setBusy(false);
    }
  }

  if (submitted) return <SuccessScreen />;

  const canAdvance = isStepComplete(step, form);

  return (
    <div className="mt-6">
      <ProgressRail step={step} />

      <div className="mt-4 rounded-2xl border border-ink-300/25 bg-white p-6">
        {step === 1 && <StepProperty form={form} patch={patch} />}
        {step === 2 && <StepCondition form={form} patch={patch} />}
        {step === 3 && <StepDocuments form={form} patch={patch} />}
        {step === 4 && (
          <StepMedia form={form} previews={previews} addPhotos={addPhotos} removePhoto={removePhoto} />
        )}
        {step === 5 && (
          <StepRemarks
            form={form}
            patch={patch}
            captureGps={captureGps}
            gpsBusy={gpsBusy}
            gpsError={gpsError}
          />
        )}

        {error && (
          <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
        )}

        <div className="mt-6 flex items-center justify-between">
          <button
            type="button"
            onClick={() => setStep((s) => Math.max(1, s - 1))}
            disabled={step === 1 || busy}
            className="rounded-lg border border-ink-300/50 px-4 py-2.5 text-sm font-medium text-ink-700 transition hover:border-ink-500 disabled:opacity-40"
          >
            Back
          </button>
          {step < STEPS.length ? (
            <button
              type="button"
              onClick={() => setStep((s) => s + 1)}
              disabled={!canAdvance}
              className="rounded-lg bg-emerald-deep px-5 py-2.5 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:opacity-40"
            >
              Continue
            </button>
          ) : (
            <button
              type="button"
              onClick={submit}
              disabled={!canAdvance || busy}
              className="rounded-lg bg-emerald-deep px-5 py-2.5 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:opacity-40"
            >
              {busy ? 'Submitting…' : 'Submit Report'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ProgressRail({ step }: { step: number }) {
  return (
    <ol className="flex items-center gap-2">
      {STEPS.map((label, i) => {
        const n = i + 1;
        const done = n < step;
        const active = n === step;
        return (
          <li key={label} className="flex flex-1 flex-col items-center gap-1">
            <div className="flex w-full items-center">
              <span
                className={`flex h-7 w-7 flex-none items-center justify-center rounded-full text-xs font-semibold ${
                  done
                    ? 'bg-emerald-deep text-bone'
                    : active
                      ? 'bg-emerald-deep/15 text-emerald-deep ring-2 ring-emerald-deep'
                      : 'bg-ink-300/20 text-ink-500'
                }`}
              >
                {done ? '✓' : n}
              </span>
              {i < STEPS.length - 1 && (
                <span className={`h-0.5 flex-1 ${n < step ? 'bg-emerald-deep' : 'bg-ink-300/30'}`} />
              )}
            </div>
            <span className={`text-[11px] ${active ? 'font-medium text-ink-900' : 'text-ink-500'}`}>
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

type PatchFn = (p: Partial<ReportForm>) => void;

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-ink-800">{label}</span>
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

const textareaCls =
  'w-full rounded-lg border border-ink-300/50 px-3 py-2 text-sm text-ink-900 outline-none focus:border-emerald-deep';

function StepProperty({ form, patch }: { form: ReportForm; patch: PatchFn }) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-xl text-ink-900">Property Verification</h2>
        <p className="mt-1 text-sm text-ink-500">Confirm the property exists and matches the listing.</p>
      </div>
      <div className="flex gap-3">
        {(['yes', 'no'] as const).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => patch({ propertyMatches: v })}
            className={`flex-1 rounded-xl border px-4 py-3 text-sm font-medium capitalize transition ${
              form.propertyMatches === v
                ? 'border-emerald-deep bg-emerald-deep/5 text-emerald-deep'
                : 'border-ink-300/50 text-ink-700 hover:border-ink-500'
            }`}
          >
            {v === 'yes' ? 'Yes, it matches' : 'No, there are issues'}
          </button>
        ))}
      </div>
      <Field label="Notes (optional)">
        <textarea
          rows={3}
          value={form.propertyNotes}
          onChange={(e) => patch({ propertyNotes: e.target.value })}
          placeholder="Anything notable about the property vs. the listing…"
          className={textareaCls}
        />
      </Field>
    </div>
  );
}

function StepCondition({ form, patch }: { form: ReportForm; patch: PatchFn }) {
  function toggleAmenity(a: string) {
    patch({
      amenities: form.amenities.includes(a)
        ? form.amenities.filter((x) => x !== a)
        : [...form.amenities, a],
    });
  }
  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-xl text-ink-900">Condition Assessment</h2>
        <p className="mt-1 text-sm text-ink-500">Rate the overall condition and confirm amenities.</p>
      </div>
      <Field label="Overall condition">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {CONDITION_OPTIONS.map((o) => (
            <button
              key={o.value}
              type="button"
              onClick={() => patch({ condition: o.value })}
              className={`rounded-lg border px-3 py-2 text-sm font-medium transition ${
                form.condition === o.value
                  ? 'border-emerald-deep bg-emerald-deep/5 text-emerald-deep'
                  : 'border-ink-300/50 text-ink-700 hover:border-ink-500'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      </Field>
      <Field label="Amenities present">
        <div className="flex flex-wrap gap-2">
          {AMENITY_OPTIONS.map((a) => (
            <button
              key={a}
              type="button"
              onClick={() => toggleAmenity(a)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                form.amenities.includes(a)
                  ? 'border-emerald-deep bg-emerald-deep/10 text-emerald-deep'
                  : 'border-ink-300/50 text-ink-600 hover:border-ink-500'
              }`}
            >
              {form.amenities.includes(a) ? '✓ ' : ''}
              {a}
            </button>
          ))}
        </div>
      </Field>
      <Field label="Accessibility">
        <select
          value={form.accessibility}
          onChange={(e) => patch({ accessibility: e.target.value })}
          className="w-full rounded-lg border border-ink-300/50 bg-white px-3 py-2 text-sm text-ink-900 outline-none focus:border-emerald-deep"
        >
          <option value="">Not assessed</option>
          {ACCESSIBILITY_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Environmental notes (optional)">
        <textarea
          rows={2}
          value={form.environmentalNotes}
          onChange={(e) => patch({ environmentalNotes: e.target.value })}
          placeholder="Surroundings, flooding risk, neighbourhood…"
          className={textareaCls}
        />
      </Field>
    </div>
  );
}

function StepDocuments({ form, patch }: { form: ReportForm; patch: PatchFn }) {
  function setDoc(item: string, status: DocCheckStatus) {
    patch({ docChecks: { ...form.docChecks, [item]: status } });
  }
  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-xl text-ink-900">Document Cross-Check</h2>
        <p className="mt-1 text-sm text-ink-500">
          Confirm each document against what you saw on site.
        </p>
      </div>
      <div className="space-y-2">
        {DOCUMENT_CHECK_ITEMS.map((item) => (
          <div
            key={item}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-bone px-3 py-2"
          >
            <span className="text-sm text-ink-900">{item}</span>
            <div className="flex gap-1">
              {(Object.keys(DOC_STATUS_LABELS) as DocCheckStatus[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setDoc(item, s)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                    form.docChecks[item] === s
                      ? s === 'verified'
                        ? 'bg-emerald-deep text-bone'
                        : 'bg-red-500 text-white'
                      : 'bg-white text-ink-600 hover:bg-ink-300/10'
                  }`}
                >
                  {DOC_STATUS_LABELS[s]}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      <Field label="Document notes (optional)">
        <textarea
          rows={2}
          value={form.docNotes}
          onChange={(e) => patch({ docNotes: e.target.value })}
          placeholder="Any mismatches or missing paperwork…"
          className={textareaCls}
        />
      </Field>
    </div>
  );
}

function StepMedia({
  form,
  previews,
  addPhotos,
  removePhoto,
}: {
  form: ReportForm;
  previews: string[];
  addPhotos: (files: FileList | null) => void;
  removePhoto: (idx: number) => void;
}) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-xl text-ink-900">Media Upload</h2>
        <p className="mt-1 text-sm text-ink-500">
          Add at least {MIN_PHOTOS} photos of the property (images under 5MB each).
        </p>
      </div>

      <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-ink-300/60 bg-bone/60 px-6 py-8 text-center transition hover:border-emerald-deep">
        <span className="text-2xl" aria-hidden>
          📷
        </span>
        <span className="mt-2 text-sm font-medium text-ink-800">Tap to add photos</span>
        <span className="mt-0.5 text-xs text-ink-500">
          {form.photos.length} added · {MIN_PHOTOS} minimum
        </span>
        <input
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => addPhotos(e.target.files)}
        />
      </label>

      {previews.length > 0 && (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {previews.map((url, i) => (
            <div key={url} className="relative aspect-square overflow-hidden rounded-lg bg-bone">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={url} alt={`Photo ${i + 1}`} className="h-full w-full object-cover" />
              <button
                type="button"
                onClick={() => removePhoto(i)}
                aria-label={`Remove photo ${i + 1}`}
                className="absolute right-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-ink-900/70 text-xs text-white"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-ink-500">
        Video upload is coming soon — photos are required for now.
      </p>
    </div>
  );
}

function StepRemarks({
  form,
  patch,
  captureGps,
  gpsBusy,
  gpsError,
}: {
  form: ReportForm;
  patch: PatchFn;
  captureGps: () => void;
  gpsBusy: boolean;
  gpsError: string | null;
}) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-xl text-ink-900">Final Remarks</h2>
        <p className="mt-1 text-sm text-ink-500">
          Add your summary and capture your on-site GPS location to submit.
        </p>
      </div>

      <Field label="Report summary">
        <textarea
          rows={4}
          value={form.finalRemarks}
          onChange={(e) => patch({ finalRemarks: e.target.value })}
          placeholder="Your overall assessment and recommendation…"
          className={textareaCls}
        />
      </Field>

      <div className="rounded-xl bg-bone px-4 py-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-ink-800">On-site GPS</span>
          {form.gps ? (
            <span className="text-xs font-medium text-emerald-deep">
              ✓ {form.gps.lat.toFixed(5)}, {form.gps.lng.toFixed(5)}
            </span>
          ) : (
            <span className="text-xs text-ink-500">Not captured</span>
          )}
        </div>
        <button
          type="button"
          onClick={captureGps}
          disabled={gpsBusy}
          className="mt-3 w-full rounded-lg border border-emerald-deep/40 px-4 py-2.5 text-sm font-semibold text-emerald-deep transition hover:bg-emerald-deep/5 disabled:opacity-60"
        >
          {gpsBusy ? 'Capturing…' : form.gps ? 'Re-capture location' : 'Capture GPS location'}
        </button>
        <p className="mt-2 text-xs text-ink-500">
          Your location must be within 1km of the property — capture it while on site.
        </p>
        {gpsError && <p className="mt-1 text-xs text-red-600">{gpsError}</p>}
      </div>
    </div>
  );
}

function SuccessScreen() {
  return (
    <div className="mt-8 rounded-2xl border border-emerald-deep/20 bg-white p-10 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-full bg-emerald-deep/10 text-3xl">
        ✓
      </span>
      <h2 className="mt-4 font-display text-2xl text-ink-900">Report Submitted Successfully</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-ink-500">
        Thank you — your inspection report has been submitted and is now visible to the buyer,
        seller, and our team. Your commission is accrued once the deal completes.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <Link
          href="/realtor/inspections"
          className="rounded-lg bg-emerald-deep px-5 py-2.5 text-sm font-semibold text-bone transition hover:bg-emerald-accent"
        >
          Back to inspections
        </Link>
        <Link
          href="/realtor/reports"
          className="rounded-lg border border-emerald-deep/40 px-5 py-2.5 text-sm font-semibold text-emerald-deep transition hover:bg-emerald-deep/5"
        >
          View report history
        </Link>
      </div>
    </div>
  );
}
