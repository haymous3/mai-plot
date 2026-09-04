'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { NotesField, OptionPair, Question, ReportSummary, Stepper } from './wizard-parts';
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CameraIcon,
  CheckCircleIcon,
  EyeIcon,
  HouseIcon,
  MapIcon,
  MapPinIcon,
  VideoIcon,
} from '../../../_icons';
import type { RealtorInspection } from '@/lib/api';
import { formatNaira } from '@/lib/format';
import {
  completedSteps,
  composeDiscrepancies,
  composeRemarks,
  CONDITION_OPTIONS,
  emptyReportForm,
  isStepComplete,
  MIN_PHOTOS,
  PHOTO_MAX_BYTES,
  STEPS,
  VIDEO_ACCEPT,
  VIDEO_MAX_BYTES,
  type ReportForm,
} from '@/lib/inspection-report';
import { inspectionLocation, propertyTypeLabel } from '@/lib/realtor-inspection';

const SUBMIT_ERRORS: Record<string, string> = {
  MIN_PHOTOS_REQUIRED: `At least ${MIN_PHOTOS} photos are required.`,
  GPS_OUT_OF_RANGE: "Your location isn't within 1km of the property — capture GPS on site.",
  REPORT_TOO_EARLY: "The report can't be submitted before the confirmed inspection date.",
  REPORT_NOT_SUBMITTABLE: 'This inspection has already been reported, or is not accepted.',
  CONDITION_INVALID: 'Please choose a valid property condition.',
  NOT_ASSIGNED_REALTOR: 'This inspection is not assigned to you.',
  COORDINATES_INVALID: 'The captured GPS coordinates are invalid — recapture and retry.',
  STORAGE_UNAVAILABLE: 'Photo storage is temporarily unavailable. Please retry.',
  VIDEO_INVALID: 'The video must be an MP4, MOV or WebM file.',
  VIDEO_TOO_LARGE: 'The video exceeds the 50MB limit.',
};

/** Inspection report wizard (SCRUM-140, restructured to the designed five
 * sections in SCRUM-204 from Figma 278:3729).
 *
 * GPS: the design has no capture step, but the backend requires gps_lat/gps_lng
 * and rejects a report taken more than 1km from the property. So it is captured
 * silently on reaching Media Upload — by which point the realtor is on site —
 * with a status line and a manual re-capture in Final Remarks for when the
 * first fix fails or is stale. */
export function ReportWizard({ insp }: { insp: RealtorInspection }) {
  const [form, setForm] = useState<ReportForm>(emptyReportForm);
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gpsBusy, setGpsBusy] = useState(false);
  const [gpsError, setGpsError] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const previews = useMemo(() => form.photos.map((p) => URL.createObjectURL(p)), [form.photos]);
  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews]);

  function patch(p: Partial<ReportForm>) {
    setForm((f) => ({ ...f, ...p }));
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
        setForm((f) => ({ ...f, gps: { lat: pos.coords.latitude, lng: pos.coords.longitude } }));
        setGpsBusy(false);
      },
      () => {
        setGpsError('Could not read your location. Enable location access and try again.');
        setGpsBusy(false);
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }

  // Capture once the realtor reaches Media Upload — they are on site by then,
  // and it keeps the designed layout free of a capture step.
  useEffect(() => {
    if (step === 4 && form.gps === null && !gpsBusy && gpsError === null) captureGps();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

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

  async function submit() {
    if (!form.gps) return;
    setBusy(true);
    setError(null);
    const fd = new FormData();
    fd.append('gps_lat', String(form.gps.lat));
    fd.append('gps_lng', String(form.gps.lng));
    fd.append('property_condition', form.condition);
    const discrepancies = composeDiscrepancies(form);
    if (discrepancies) fd.append('discrepancies', discrepancies);
    const remarks = composeRemarks(form);
    if (remarks) fd.append('remarks', remarks);
    for (const p of form.photos) fd.append('photos', p);
    if (form.video) fd.append('video', form.video);

    try {
      const resp = await fetch(`/api/realtor/inspections/${insp.inspection_id}/report`, {
        method: 'POST',
        body: fd,
      });
      if (resp.ok) {
        setSubmitted(true);
        return;
      }
      const body = (await resp.json().catch(() => ({}))) as { error_code?: string };
      setError(SUBMIT_ERRORS[body.error_code ?? ''] ?? 'Could not submit the report. Please retry.');
    } catch {
      setError('Network error. Please retry.');
    }
    setBusy(false);
  }

  if (submitted) return <SuccessScreen insp={insp} />;

  const done = completedSteps(form);
  const canAdvance = isStepComplete(step, form);

  return (
    <div className="flex items-start">
      <div className="min-w-0 flex-1">
        <div className="mx-auto max-w-[896px] px-8 py-8">
          <Link
            href={`/realtor/inspections/${insp.inspection_id}`}
            className="inline-flex items-center gap-2 text-sm font-medium text-ink-600 transition hover:text-ink-900"
          >
            <ArrowLeftIcon className="h-4 w-4" />
            Back to Inspections
          </Link>

          <div className="mt-6 space-y-6">
            <PropertyHeader insp={insp} />
            <Stepper step={step} done={done} />

            <section className="rounded-card-sm border border-line bg-surface-card p-8">
              <h2 className="text-xl font-bold text-ink-900">
                Section {step}: {STEPS[step - 1]}
              </h2>

              <div className="mt-6 space-y-6">
                {step === 1 && <SectionProperty form={form} patch={patch} />}
                {step === 2 && <SectionCondition form={form} patch={patch} />}
                {step === 3 && <SectionDocuments form={form} patch={patch} />}
                {step === 4 && (
                  <SectionMedia
                    form={form}
                    previews={previews}
                    addPhotos={addPhotos}
                    removePhoto={(i) => patch({ photos: form.photos.filter((_, x) => x !== i) })}
                    patch={patch}
                  />
                )}
                {step === 5 && (
                  <SectionRemarks
                    form={form}
                    patch={patch}
                    captureGps={captureGps}
                    gpsBusy={gpsBusy}
                    gpsError={gpsError}
                  />
                )}
              </div>

              {error && (
                <p className="mt-6 rounded-[10px] bg-distress-50 px-4 py-3 text-sm text-distress-700">
                  {error}
                </p>
              )}
            </section>

            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={() => setStep((s) => Math.max(1, s - 1))}
                disabled={step === 1 || busy}
                className="inline-flex h-12 items-center gap-2 rounded-[10px] border-2 border-line-strong px-6 text-base font-medium text-ink-700 transition hover:border-ink-500 disabled:opacity-50 disabled:hover:border-line-strong"
              >
                <ArrowLeftIcon className="h-4 w-4" />
                Previous
              </button>
              {step < STEPS.length ? (
                <button
                  type="button"
                  onClick={() => setStep((s) => s + 1)}
                  disabled={!canAdvance}
                  className="inline-flex h-12 items-center gap-2 rounded-[10px] bg-emerald-deep px-6 text-base font-medium text-white transition hover:bg-emerald-accent disabled:opacity-50 disabled:hover:bg-emerald-deep"
                >
                  Next Section
                  <ArrowRightIcon className="h-4 w-4" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={submit}
                  disabled={!canAdvance || busy}
                  className="inline-flex h-12 items-center gap-2 rounded-[10px] bg-emerald-deep px-6 text-base font-medium text-white transition hover:bg-emerald-accent disabled:opacity-50 disabled:hover:bg-emerald-deep"
                >
                  <CheckCircleIcon className="h-4 w-4" />
                  {busy ? 'Submitting…' : 'Submit Report'}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      <ContextRail
        insp={insp}
        form={form}
        done={done}
        preview={preview}
        setPreview={setPreview}
      />
    </div>
  );
}

/** Property header (Figma 278:3737): thumbnail, title, schedule, badges, then
 * the contact / authority / references strip. The phone arrives already masked
 * from realtor-service — the raw number never reaches the browser (§10). */
function PropertyHeader({ insp }: { insp: RealtorInspection }) {
  const type = propertyTypeLabel(insp.property_type);
  const scheduledAt = insp.confirmed_date ?? insp.proposed_date;

  return (
    <section className="rounded-card-sm border border-line bg-surface-card p-6">
      <div className="flex flex-wrap items-start gap-4">
        {insp.cover_photo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={insp.cover_photo_url}
            alt=""
            className="h-24 w-24 flex-none rounded-[10px] object-cover"
          />
        ) : (
          <div aria-hidden className="h-24 w-24 flex-none rounded-[10px] bg-surface-muted" />
        )}
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold leading-8 text-ink-900">
            {insp.property_title ?? 'Property inspection'}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-600">
            <span className="flex items-center gap-1.5">
              <MapPinIcon className="h-4 w-4 flex-none" />
              {inspectionLocation(insp)}
            </span>
            <span>{new Date(scheduledAt).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}</span>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {type && (
              <span className="inline-flex h-6 items-center rounded-full bg-surface-muted px-3 text-xs font-medium text-ink-700">
                {type}
              </span>
            )}
            {insp.sale_type === 'distress' && (
              <span className="inline-flex h-6 items-center rounded-full bg-distress-100 px-3 text-xs font-medium text-distress-700">
                Distress Sale
              </span>
            )}
            {insp.asking_price_kobo !== null && (
              <span className="inline-flex h-6 items-center rounded-full bg-emerald-deep px-3 text-xs font-medium text-white">
                {formatNaira(insp.asking_price_kobo)}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-6 border-t border-line pt-4 sm:grid-cols-3">
        <Field label="Contact Person">
          {insp.seller_name ? (
            <>
              <p className="text-sm font-medium text-ink-900">{insp.seller_name}</p>
              {insp.seller_phone_masked && (
                <p className="text-xs text-ink-600">{insp.seller_phone_masked}</p>
              )}
            </>
          ) : (
            <p className="text-sm text-ink-500">Not available</p>
          )}
        </Field>
        <Field label="Seller Authority">
          <p className="text-sm font-medium text-ink-900">
            {insp.seller_authority_type === null
              ? 'Not stated'
              : insp.seller_authority_type === 'power_of_attorney'
                ? 'Power of Attorney'
                : 'Property Owner'}
          </p>
        </Field>
        <Field label="Reference IDs">
          <p className="font-mono text-xs text-ink-900">
            Inspection: {insp.inspection_ref.toUpperCase()}
          </p>
          <p className="font-mono text-xs text-ink-900">Buyer: {insp.buyer_ref.toUpperCase()}</p>
        </Field>
      </div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs text-ink-600">{label}</p>
      <div className="mt-1 space-y-0.5">{children}</div>
    </div>
  );
}

type PatchFn = (p: Partial<ReportForm>) => void;

function SectionProperty({ form, patch }: { form: ReportForm; patch: PatchFn }) {
  return (
    <>
      <Question label="Does the property exist at the stated location?">
        <OptionPair
          name="Does the property exist at the stated location?"
          value={form.propertyExists}
          onChange={(v) => patch({ propertyExists: v })}
          yes="Yes"
          no="No"
        />
      </Question>
      <Question label="Does the property description match reality?">
        <OptionPair
          name="Does the property description match reality?"
          value={form.descriptionMatches}
          onChange={(v) => patch({ descriptionMatches: v })}
          yes="Yes, Matches"
          no="No, Discrepancy"
        />
      </Question>
      <NotesField
        label="Additional Notes"
        value={form.propertyNotes}
        onChange={(v) => patch({ propertyNotes: v })}
        placeholder="Provide any additional observations about the property location and description..."
      />
    </>
  );
}

const CONDITION_TONE: Record<string, string> = {
  positive: 'border-done-700 bg-done-50 text-done-700',
  caution: 'border-pending-700 bg-pending-50 text-pending-700',
  negative: 'border-distress-700 bg-distress-50 text-distress-700',
};

function SectionCondition({ form, patch }: { form: ReportForm; patch: PatchFn }) {
  return (
    <>
      <Question label="Physical Condition Rating">
        <div role="radiogroup" aria-label="Physical Condition Rating" className="flex gap-4">
          {CONDITION_OPTIONS.map((o) => {
            const selected = form.condition === o.value;
            return (
              <button
                key={o.value}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => patch({ condition: o.value })}
                className={`flex h-[92px] flex-1 flex-col items-center justify-center gap-1 rounded-[10px] border-2 transition ${
                  selected
                    ? CONDITION_TONE[o.tone]
                    : 'border-line-strong text-ink-900 hover:border-ink-500'
                }`}
              >
                <span className="text-base font-bold">{o.label}</span>
                <span className={`text-xs ${selected ? '' : 'text-ink-600'}`}>{o.hint}</span>
              </button>
            );
          })}
        </div>
      </Question>
      <NotesField
        label="Environmental Notes"
        value={form.environmentalNotes}
        onChange={(v) => patch({ environmentalNotes: v })}
        placeholder="Describe the surrounding environment, access roads, nearby landmarks, etc..."
        rows={3}
      />
      <NotesField
        label="Accessibility"
        value={form.accessibility}
        onChange={(v) => patch({ accessibility: v })}
        placeholder="How easy is it to access this property? Road conditions, public transport, etc..."
        rows={3}
      />
    </>
  );
}

function SectionDocuments({ form, patch }: { form: ReportForm; patch: PatchFn }) {
  return (
    <>
      <p className="rounded-[10px] border border-pending-200 bg-pending-50 px-4 py-3 text-sm text-pending-700">
        <span className="font-semibold">Note:</span> Verify if the seller has physical copies of
        these documents during the inspection.
      </p>
      <Question label="Survey Plan - Physical Document Present?">
        <OptionPair
          name="Survey Plan - Physical Document Present?"
          value={form.surveyPlan}
          onChange={(v) => patch({ surveyPlan: v })}
          yes="Yes, Verified"
          no="Not Present"
        />
      </Question>
      <Question label="Certificate of Occupancy (C of O) - Physical Document Present?">
        <OptionPair
          name="Certificate of Occupancy - Physical Document Present?"
          value={form.certificateOfOccupancy}
          onChange={(v) => patch({ certificateOfOccupancy: v })}
          yes="Yes, Verified"
          no="Not Present"
        />
      </Question>
      <Question label="Do physical documents match uploaded digital copies?">
        <OptionPair
          name="Do physical documents match uploaded digital copies?"
          value={form.documentsMatch}
          onChange={(v) => patch({ documentsMatch: v })}
          yes="Yes, Match"
          no="No, Discrepancy"
        />
      </Question>
    </>
  );
}

function SectionMedia({
  form,
  previews,
  addPhotos,
  removePhoto,
  patch,
}: {
  form: ReportForm;
  previews: string[];
  addPhotos: (files: FileList | null) => void;
  removePhoto: (i: number) => void;
  patch: PatchFn;
}) {
  return (
    <>
      <Question label="Upload Photos from Inspection" required>
        <label className="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-[10px] border border-dashed border-line-strong px-6 py-10 text-center transition hover:border-emerald-deep">
          <CameraIcon className="h-8 w-8 text-ink-500" />
          <span className="mt-2 text-base font-medium text-ink-900">Click to upload photos</span>
          <span className="text-sm text-ink-600">or drag and drop</span>
          <span className="text-xs text-ink-500">
            PNG, JPG up to 5MB each · {form.photos.length} added, {MIN_PHOTOS} minimum
          </span>
          <input
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => addPhotos(e.target.files)}
          />
        </label>
      </Question>

      {previews.length > 0 && (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {previews.map((url, i) => (
            <div key={url} className="relative aspect-square overflow-hidden rounded-[10px] bg-surface-muted">
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

      <Question label="Upload Video (Optional)">
        {form.video ? (
          <div className="flex items-center justify-between gap-3 rounded-[10px] border border-line-strong px-4 py-3">
            <span className="min-w-0 truncate text-sm text-ink-700">{form.video.name}</span>
            <button
              type="button"
              onClick={() => patch({ video: null })}
              className="flex-none text-xs font-medium text-distress-700 hover:underline"
            >
              Remove
            </button>
          </div>
        ) : (
          <label className="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-[10px] border border-dashed border-line-strong px-6 py-10 text-center transition hover:border-emerald-deep">
            <VideoIcon className="h-8 w-8 text-ink-500" />
            <span className="mt-2 text-base font-medium text-ink-900">Click to upload video</span>
            <span className="text-xs text-ink-500">MP4, MOV up to 50MB</span>
            <input
              type="file"
              accept={VIDEO_ACCEPT}
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                patch({ video: f && f.size <= VIDEO_MAX_BYTES ? f : null });
              }}
            />
          </label>
        )}
      </Question>
    </>
  );
}

function SectionRemarks({
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
    <>
      <NotesField
        label="Additional Observations"
        required
        value={form.finalRemarks}
        onChange={(v) => patch({ finalRemarks: v })}
        placeholder="Provide any final observations, concerns, or recommendations about this property..."
        rows={5}
      />

      <ReportSummary form={form} />

      {/* The design has no GPS step; the backend requires a fix within 1km of
          the property, so its state is surfaced here compactly. */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-line bg-surface-page px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink-900">On-site location</p>
          <p className="text-xs text-ink-600">
            {form.gps
              ? `Captured at ${form.gps.lat.toFixed(5)}, ${form.gps.lng.toFixed(5)}`
              : gpsBusy
                ? 'Capturing your location…'
                : 'Required — capture while on site, within 1km of the property.'}
          </p>
          {gpsError && <p className="mt-0.5 text-xs text-distress-700">{gpsError}</p>}
        </div>
        <button
          type="button"
          onClick={captureGps}
          disabled={gpsBusy}
          className="h-10 flex-none rounded-[10px] border-2 border-line px-4 text-sm font-medium text-ink-700 transition hover:border-ink-500 disabled:opacity-50"
        >
          {gpsBusy ? 'Capturing…' : form.gps ? 'Re-capture' : 'Capture location'}
        </button>
      </div>
    </>
  );
}

/** Right rail (Figma 278:3884): 320px, white, left rule. Property context, the
 * verification-impact note, quick actions and the live progress checklist. */
function ContextRail({
  insp,
  form,
  done,
  preview,
  setPreview,
}: {
  insp: RealtorInspection;
  form: ReportForm;
  done: boolean[];
  preview: boolean;
  setPreview: (v: boolean) => void;
}) {
  const type = propertyTypeLabel(insp.property_type);
  const mapQuery = encodeURIComponent(inspectionLocation(insp));

  return (
    <aside className="hidden w-80 flex-none self-stretch border-l border-line bg-surface-card p-6 xl:block">
      <h2 className="text-lg font-bold text-ink-900">Property Context</h2>

      {insp.cover_photo_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={insp.cover_photo_url}
          alt=""
          className="mt-5 h-40 w-full rounded-[10px] object-cover"
        />
      ) : (
        <div aria-hidden className="mt-5 h-40 w-full rounded-[10px] bg-surface-muted" />
      )}

      <p className="mt-4 text-base font-semibold text-ink-900">
        {insp.property_title ?? 'Property inspection'}
      </p>
      {insp.asking_price_kobo !== null && (
        <p className="mt-2 text-2xl font-bold leading-8 text-emerald-deep">
          {formatNaira(insp.asking_price_kobo)}
        </p>
      )}
      <div className="mt-3 space-y-2 text-sm text-ink-600">
        <p className="flex items-center gap-2">
          <MapPinIcon className="h-4 w-4 flex-none" />
          {inspectionLocation(insp)}
        </p>
        {type && (
          <p className="flex items-center gap-2">
            <HouseIcon className="h-4 w-4 flex-none" />
            {type}
            {insp.size_sqm ? ` • ${insp.size_sqm.toLocaleString('en-NG')} sqm` : ''}
          </p>
        )}
      </div>

      <div className="mt-6 rounded-card-sm border border-status-gold/20 bg-surface-warm p-[17px]">
        <p className="text-sm font-semibold text-ink-900">Verification Impact</p>
        <p className="mt-3 text-xs leading-5 text-ink-600">
          This inspection helps validate the property for buyers and contributes to the trust score
          shown in their dashboard.
        </p>
      </div>

      <p className="mt-6 text-sm font-semibold text-ink-900">Quick Actions</p>
      <div className="mt-3 space-y-3">
        <a
          href={`https://www.google.com/maps/search/?api=1&query=${mapQuery}`}
          target="_blank"
          rel="noreferrer noopener"
          className="flex h-10 items-center gap-2 rounded-[10px] border-2 border-line px-4 text-sm font-medium text-ink-700 transition hover:border-ink-500"
        >
          <MapIcon className="h-4 w-4 flex-none" />
          View on Map
        </a>
        <button
          type="button"
          onClick={() => setPreview(!preview)}
          aria-expanded={preview}
          className="flex h-10 w-full items-center gap-2 rounded-[10px] border-2 border-line px-4 text-sm font-medium text-ink-700 transition hover:border-ink-500"
        >
          <EyeIcon className="h-4 w-4 flex-none" />
          Preview Report
        </button>
        {preview && <ReportSummary form={form} />}
      </div>

      <div className="mt-6 rounded-card-sm border border-done-200 bg-done-50 p-[17px]">
        <p className="text-sm font-semibold text-done-800">Progress</p>
        <ul className="mt-2 space-y-2">
          {STEPS.map((label, i) => (
            <li key={label} className="flex items-center gap-2 text-xs">
              <span
                className={`flex h-4 w-4 flex-none items-center justify-center rounded-full border-2 ${
                  done[i] ? 'border-done-700 bg-done-700 text-white' : 'border-line-strong'
                }`}
              >
                {done[i] && (
                  <svg viewBox="0 0 24 24" className="h-2.5 w-2.5" fill="none" aria-hidden>
                    <path
                      d="m5 12.5 5 5L19 7"
                      stroke="currentColor"
                      strokeWidth={3.5}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </span>
              <span className={done[i] ? 'text-done-700' : 'text-ink-600'}>{label}</span>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}

/** Post-submission confirmation (Figma export 9.png). */
function SuccessScreen({ insp }: { insp: RealtorInspection }) {
  return (
    <div className="mx-auto max-w-[672px] px-8 py-16">
      <div className="rounded-card-sm border border-line bg-surface-card p-10 text-center">
        <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-done-100">
          <CheckCircleIcon className="h-8 w-8 text-done-700" strokeWidth={2} />
        </span>
        <h2 className="mt-6 text-2xl font-bold text-ink-900">Report Submitted Successfully!</h2>
        <p className="mt-2 text-sm text-ink-600">
          Your inspection report for{' '}
          <span className="font-semibold text-ink-900">
            {insp.property_title ?? 'this property'}
          </span>{' '}
          has been submitted.
        </p>

        <div className="mt-6 rounded-[10px] border border-pending-200 bg-pending-50 px-4 py-4">
          <p className="text-sm font-semibold text-pending-700">Status: Under Review</p>
          <p className="mt-1 text-sm text-pending-700">
            Your report is being reviewed by admin. You&apos;ll be notified once it&apos;s approved.
          </p>
        </div>

        <div className="mt-4 rounded-[10px] bg-surface-warm px-4 py-4">
          <p className="text-sm font-semibold text-ink-900">Impact of Your Work</p>
          <p className="mt-1 text-sm text-ink-600">
            This inspection helps validate the property for buyers, contributes to listing
            credibility, and powers trust indicators across the platform.
          </p>
        </div>

        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link
            href="/realtor/inspections"
            className="inline-flex h-11 items-center rounded-[10px] border-2 border-line px-5 text-sm font-medium text-ink-700 transition hover:border-ink-500"
          >
            View All Inspections
          </Link>
          <Link
            href="/realtor"
            className="inline-flex h-11 items-center rounded-[10px] bg-emerald-deep px-5 text-sm font-semibold text-white transition hover:bg-emerald-accent"
          >
            Back to Dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
