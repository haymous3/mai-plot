'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import type { SellerPoaStatus } from '@/lib/api';
import { projectedExpiry } from '@/lib/countdown';
import { MoneyInput } from '@/app/_components/money-input';
import { formatNaira } from '@/lib/format';
import { nairaToKobo } from '@/lib/money-input';
import { canJumpToStep } from '@/lib/wizard-nav';

type PropertyType = 'residential' | 'commercial';
type SaleType = 'normal' | 'distress';
type UrgencyTag = '7_days' | '14_days' | '30_days';
type Authority = 'owner' | 'power_of_attorney';

const STEPS = [
  'Property Details',
  'Location',
  'Pricing',
  'Media Upload',
  'Documents',
  'Authority',
  'Review',
];

// 'land' was removed here (SCRUM-199) at the product owner's request. The
// BACKEND still accepts it — listing-service's property_type CHECK and the
// existing land listings are untouched — so this narrows what a seller can
// newly create, not what the platform can hold.
const PROPERTY_TYPES: { value: PropertyType; label: string }[] = [
  { value: 'residential', label: 'Residential' },
  { value: 'commercial', label: 'Commercial' },
];

/**
 * PoA document limits, mirrored from auth-service (SCRUM-199).
 *
 * ⚠️ PDF and JPEG only — NOT PNG. `poa.detect_document_type()` reads magic
 * bytes and accepts exactly those two. The onboarding screen's copy says
 * "PDF, PNG, or JPG (max 5MB)", which is wrong on both counts; it is corrected
 * in the same change.
 */
const MAX_POA_MB = 10;
const POA_ACCEPT = 'application/pdf,image/jpeg';

const POA_ERRORS: Record<string, string> = {
  POA_DOCUMENT_INVALID: 'The document must be a PDF or JPEG file.',
  POA_DOCUMENT_TOO_LARGE: `The document exceeds the ${MAX_POA_MB}MB limit.`,
  POA_ALREADY_SUBMITTED: 'A document is already on file and awaiting review.',
  POA_NOT_ELIGIBLE: 'Only a power-of-attorney seller can upload this document.',
  NO_SESSION: 'Your session expired — please sign in again.',
};

/**
 * Media limits, mirrored from listing-service `app/config.py` (SCRUM-199).
 *
 * These are shown to the seller AND checked before upload, so an over-size file
 * is refused here with a sentence rather than after a 200MB round trip that
 * ends in MEDIA_TOO_LARGE. The server remains the authority — this is a
 * courtesy, not the guard.
 *
 * ⚠️ The accept lists are narrower than the `image/*` and `video/*` they
 * replace, and deliberately so: listing-service validates by MAGIC BYTES and
 * accepts only JPEG, PNG and MP4. `image/*` let a seller pick a GIF or a HEIC
 * the server was always going to reject.
 */
const MAX_PHOTO_MB = 5;
const MAX_VIDEO_MB = 200;
const MAX_PHOTOS = 15;
const PHOTO_ACCEPT = 'image/jpeg,image/png';
const VIDEO_ACCEPT = 'video/mp4';

const URGENCY: { value: UrgencyTag; label: string }[] = [
  { value: '7_days', label: '7 days' },
  { value: '14_days', label: '14 days' },
  { value: '30_days', label: '30 days' },
];

// Required documents; "other" maps to governors_consent (an optional extra).
const DOC_SLOTS: { key: DocKey; type: string; label: string; required: boolean }[] = [
  { key: 'c_of_o', type: 'c_of_o', label: 'Certificate of Occupancy (C of O)', required: true },
  { key: 'survey_plan', type: 'survey_plan', label: 'Survey Plan', required: true },
  { key: 'deed_of_assignment', type: 'deed_of_assignment', label: 'Deed of Assignment', required: true },
  { key: 'other', type: 'governors_consent', label: 'Other Document (optional)', required: false },
];
type DocKey = 'c_of_o' | 'survey_plan' | 'deed_of_assignment' | 'other';

const CREATE_ERRORS: Record<string, string> = {
  // ⚠️ The CODE is still `BVN_REQUIRED`, but listing-service's gate only
  // checks verified_status in (id_verified, fully_verified) — it never cared
  // which identity document set that. Since SCRUM-189 the funnel collects a
  // NIN, so the code name is a misnomer; renaming it is an API-contract
  // change and is deliberately NOT bundled into this copy fix.
  BVN_REQUIRED: 'Complete your identity (NIN) verification before listing a property.',
  POA_NOT_VERIFIED: 'Your power-of-attorney document must be verified before you can publish.',
  SELLER_ROLE_REQUIRED: 'Only seller accounts can create listings.',
  URGENCY_TAG_REQUIRED_FOR_DISTRESS: 'A distress sale needs an urgency window.',
};

// The design shows a map-pin placeholder rather than a real picker; default the
// coordinate to central Lagos so the required geo-point is satisfied.
const DEFAULT_LOCATION = { lat: 6.5244, lng: 3.3792 };

export function CreateListingWizard({ poa }: { poa?: SellerPoaStatus | null }) {
  const router = useRouter();
  const [step, setStep] = useState(0);
  // The furthest step reached, so the stepper knows which numbers are
  // navigable. Distinct from `step`: going back must not shrink it, or the
  // seller would lose the ability to jump forward again to work they had
  // already completed.
  const [maxVisited, setMaxVisited] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  // Property details
  const [title, setTitle] = useState('');
  const [propertyType, setPropertyType] = useState<PropertyType>('residential');
  const [sizeSqm, setSizeSqm] = useState('');
  const [description, setDescription] = useState('');
  // Location
  const [address, setAddress] = useState('');
  const [lga, setLga] = useState('');
  const [state, setState] = useState('');
  // Pricing
  const [priceNaira, setPriceNaira] = useState('');
  const [negotiable, setNegotiable] = useState(false);
  const [saleType, setSaleType] = useState<SaleType>('normal');
  const [urgency, setUrgency] = useState<UrgencyTag>('7_days');
  // Media
  const [images, setImages] = useState<File[]>([]);
  const [video, setVideo] = useState<File | null>(null);
  const [mediaError, setMediaError] = useState<string | null>(null);
  // Documents
  const [docs, setDocs] = useState<Partial<Record<DocKey, File>>>({});
  // Authority
  // Seeded from the ACCOUNT, not left at a default: this is a declared fact
  // about the seller, and showing "Direct Owner" to someone registered under a
  // power of attorney would be telling them something untrue about themselves.
  const [authority, setAuthority] = useState<Authority>(
    poa?.authority_type === 'power_of_attorney' ? 'power_of_attorney' : 'owner',
  );
  const [poaFile, setPoaFile] = useState<File | null>(null);
  const [poaBusy, setPoaBusy] = useState(false);
  const [poaError, setPoaError] = useState<string | null>(null);
  const [poaUploaded, setPoaUploaded] = useState(false);

  const priceKobo = nairaToKobo(priceNaira);
  const expiry = saleType === 'distress' ? projectedExpiry(urgency) : null;

  /**
   * Whether a given step's own requirements are currently met.
   *
   * Addressed BY INDEX rather than reading `step` (SCRUM-200), because the
   * stepper now has to ask about steps the seller is not standing on — "can I
   * jump from 1 to 5?" means checking 1 through 4, not just the current one.
   */
  function stepValid(i: number): boolean {
    if (i === 0) return title.trim().length > 0 && sizeSqm.trim().length > 0;
    if (i === 1) return address.trim().length > 0 && lga.trim().length > 0 && state.trim().length > 0;
    if (i === 2) return Number.isFinite(priceKobo) && priceKobo > 0;
    return true;
  }

  function canAdvance(): boolean {
    return stepValid(step);
  }

  /** Rules live in lib/wizard-nav so they can be tested (SCRUM-200). */
  function canJumpTo(target: number): boolean {
    return canJumpToStep({
      target,
      current: step,
      maxVisited,
      isValid: stepValid,
      busy: submitting,
    });
  }

  function goToStep(target: number) {
    if (!canJumpTo(target)) return;
    setStep(target);
    setMaxVisited((m) => Math.max(m, target));
  }

  async function uploadMedia(listingId: string, file: File, mediaType: 'photo' | 'video', order: number) {
    const form = new FormData();
    form.set('media_type', mediaType);
    form.set('sort_order', String(order));
    form.set('file', file);
    const resp = await fetch(`/api/seller/listings/${listingId}/media`, { method: 'POST', body: form });
    return resp.ok;
  }

  async function uploadDoc(listingId: string, file: File, documentType: string) {
    const form = new FormData();
    form.set('document_type', documentType);
    form.set('file', file);
    const resp = await fetch(`/api/seller/listings/${listingId}/documents`, { method: 'POST', body: form });
    return resp.ok;
  }

  /** Add images, refusing over-size files and anything past the per-listing cap. */
  function addImages(files: File[]) {
    const room = MAX_PHOTOS - images.length;
    if (room <= 0) {
      setMediaError(`You can upload at most ${MAX_PHOTOS} images.`);
      return;
    }
    const tooBig = files.filter((f) => f.size > MAX_PHOTO_MB * 1024 * 1024);
    const ok = files.filter((f) => f.size <= MAX_PHOTO_MB * 1024 * 1024).slice(0, room);
    setImages((prev) => [...prev, ...ok]);
    // Name the files that were dropped. "Some images were too large" leaves the
    // seller guessing which of a multi-select failed.
    const notes: string[] = [];
    if (tooBig.length > 0) {
      notes.push(
        `${tooBig.map((f) => f.name).join(', ')} exceeded ${MAX_PHOTO_MB}MB and ${tooBig.length === 1 ? 'was' : 'were'} not added.`,
      );
    }
    if (files.length - tooBig.length > ok.length) {
      notes.push(`Only ${MAX_PHOTOS} images are allowed, so the rest were not added.`);
    }
    setMediaError(notes.join(' ') || null);
  }

  function pickVideo(file: File | null) {
    if (file && file.size > MAX_VIDEO_MB * 1024 * 1024) {
      setMediaError(`${file.name} exceeds the ${MAX_VIDEO_MB}MB video limit.`);
      return;
    }
    setMediaError(null);
    setVideo(file);
  }

  /**
   * Upload the PoA document (SCRUM-199).
   *
   * Account-level, not per-listing: CLAUDE.md §8.1 gates a PoA seller's ability
   * to publish ANY listing on one verified document, so this posts to the same
   * `/api/auth/seller/poa` the onboarding step uses.
   *
   * `/auth/poa/upload` refuses a caller whose ACCOUNT is not a power_of_attorney
   * seller, so an owner who switches the choice here has to declare that first —
   * hence the authority POST ahead of the file.
   */
  async function uploadPoa() {
    if (!poaFile) return;
    setPoaBusy(true);
    setPoaError(null);
    try {
      if (poa?.authority_type !== 'power_of_attorney') {
        const declared = await fetch('/api/auth/seller/authority', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ authority_type: 'power_of_attorney' }),
        });
        if (!declared.ok) {
          setPoaError('We could not record your authority. Please retry.');
          return;
        }
      }
      const form = new FormData();
      form.append('file', poaFile);
      const resp = await fetch('/api/auth/seller/poa', { method: 'POST', body: form });
      if (!resp.ok) {
        const b = (await resp.json().catch(() => ({}))) as { error_code?: string };
        setPoaError(POA_ERRORS[b.error_code ?? ''] ?? 'We could not upload that document. Please retry.');
        return;
      }
      setPoaUploaded(true);
      setPoaFile(null);
    } catch {
      setPoaError('Could not reach the server. Please try again.');
    } finally {
      setPoaBusy(false);
    }
  }

  async function submit() {
    setSubmitting(true);
    setError(null);
    setWarning(null);
    try {
      const payload = {
        title: title.trim(),
        property_type: propertyType,
        description: description.trim() || null,
        address_text: address.trim(),
        location: DEFAULT_LOCATION,
        lga: lga.trim(),
        state: state.trim(),
        size_sqm: sizeSqm.trim() || null,
        asking_price_kobo: priceKobo,
        sale_type: saleType,
        urgency_tag: saleType === 'distress' ? urgency : null,
      };
      const resp = await fetch('/api/seller/listings', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = (await resp.json().catch(() => ({}))) as {
        listing_id?: string;
        error_code?: string;
      };
      if (!resp.ok || !body.listing_id) {
        setError(CREATE_ERRORS[body.error_code ?? ''] ?? 'Could not create the listing. Please retry.');
        setStep(6);
        setMaxVisited(6);
        return;
      }

      const id = body.listing_id;
      // Best-effort media + documents. The listing already exists; report any
      // failures but still take the seller to My Listings.
      let failures = 0;
      for (let i = 0; i < images.length; i += 1) {
        if (!(await uploadMedia(id, images[i], 'photo', i))) failures += 1;
      }
      if (video && !(await uploadMedia(id, video, 'video', 0))) failures += 1;
      for (const slot of DOC_SLOTS) {
        const file = docs[slot.key];
        if (file && !(await uploadDoc(id, file, slot.type))) failures += 1;
      }

      if (failures > 0) {
        setWarning(
          `Listing created, but ${failures} file(s) failed to upload. You can add them from My Listings.`,
        );
      }
      router.push('/seller/listings');
      router.refresh();
    } catch {
      setError('Could not reach the server. Please retry.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <a href="/seller/listings" className="text-sm text-ink-500 hover:text-ink-800">
        ← Back to Listings
      </a>
      <h1 className="mt-3 font-display text-3xl text-emerald-deep">Create New Listing</h1>
      <p className="mt-1 text-sm text-ink-500">Fill in the details to list your property</p>

      {/* Stepper */}
      <ol className="mt-6 flex flex-wrap gap-y-4 rounded-2xl border border-line bg-surface-card px-4 py-5">
        {STEPS.map((label, i) => {
          const reachable = canJumpTo(i);
          const done = i < step;
          return (
            <li key={label} className="flex flex-1 min-w-[120px] flex-col items-center gap-1.5 text-center">
              {/*
                A real button, not a clickable span (SCRUM-200): the stepper is
                now navigation, so it has to be reachable by keyboard and
                announced as a control. `aria-current` marks the step the seller
                is on; a step they cannot reach yet is disabled rather than
                silently inert, so the cursor and the screen reader agree.
              */}
              <button
                type="button"
                onClick={() => goToStep(i)}
                disabled={!reachable}
                aria-current={i === step ? 'step' : undefined}
                aria-label={`Step ${i + 1}: ${label}${i === step ? ' (current)' : ''}`}
                className={`flex flex-col items-center gap-1.5 rounded-lg px-2 py-1 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep focus-visible:ring-offset-2 ${
                  reachable ? 'cursor-pointer hover:bg-ink-900/5' : 'cursor-default'
                }`}
              >
                <span
                  className={`flex h-9 w-9 items-center justify-center rounded-full text-sm font-medium ${
                    i <= step
                      ? 'bg-emerald-deep text-bone'
                      : 'border border-ink-300/50 text-ink-500'
                  }`}
                >
                  {done ? '✓' : i + 1}
                </span>
                <span className={`text-xs ${i === step ? 'text-ink-900' : 'text-ink-500'}`}>
                  {label}
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      <div className="mt-6 rounded-2xl border border-line bg-surface-card p-6 sm:p-8">
        {step === 0 && (
          <Section title="Property Details">
            <Field label="Listing Title">
              <input className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. 3-Bedroom Duplex, Lekki Phase 1" />
            </Field>
            <Field label="Property Type">
              <select className={inputCls} value={propertyType} onChange={(e) => setPropertyType(e.target.value as PropertyType)}>
                {PROPERTY_TYPES.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </Field>
            <Field label="Size (sqm)">
              <input className={inputCls} value={sizeSqm} onChange={(e) => setSizeSqm(e.target.value)} placeholder="e.g., 1,000" inputMode="decimal" />
            </Field>
            <Field label="Description">
              <textarea className={`${textareaCls} min-h-[169px]`} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Describe your property in detail…" />
            </Field>
          </Section>
        )}

        {step === 1 && (
          <Section title="Location">
            <Field label="Address">
              <input className={inputCls} value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Enter property address" />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Local Government Area (LGA)">
                <input className={inputCls} value={lga} onChange={(e) => setLga(e.target.value)} placeholder="e.g., Eti-Osa" />
              </Field>
              <Field label="State">
                <input className={inputCls} value={state} onChange={(e) => setState(e.target.value)} placeholder="e.g., Lagos" />
              </Field>
            </div>
            <div className="flex items-center justify-center rounded-xl bg-bone/60 py-16 text-sm text-ink-500">
              Map pin selection placeholder
            </div>
          </Section>
        )}

        {step === 2 && (
          <Section title="Pricing">
            <Field label="Price (₦)">
              <MoneyInput
                className={inputCls}
                value={priceNaira}
                onChange={setPriceNaira}
                placeholder="e.g., 45,000,000"
                ariaLabel="Asking price in naira"
              />
            </Field>
            <label className="flex items-center gap-2 text-sm text-ink-700">
              <input type="checkbox" checked={negotiable} onChange={(e) => setNegotiable(e.target.checked)} />
              Price is negotiable
            </label>
            <Field label="Sale Type">
              <div className="grid gap-3 sm:grid-cols-2">
                <Choice active={saleType === 'normal'} onClick={() => setSaleType('normal')} title="Normal Sale" sub="Standard property sale" />
                <Choice active={saleType === 'distress'} onClick={() => setSaleType('distress')} title="Distress Sale" sub="Urgent sale with timer" />
              </div>
            </Field>
            {saleType === 'distress' && (
              <Field label="Urgency window">
                <div className="flex gap-2">
                  {URGENCY.map((u) => (
                    <button key={u.value} type="button" onClick={() => setUrgency(u.value)} className={`rounded-lg px-4 py-2 text-sm ${urgency === u.value ? 'bg-emerald-deep text-bone' : 'border border-ink-300/50 text-ink-700'}`}>
                      {u.label}
                    </button>
                  ))}
                </div>
                {expiry && (
                  <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
                    ⏳ This distress listing will auto-expire on{' '}
                    <span className="font-medium">
                      {expiry.date.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })}
                    </span>{' '}
                    (in {expiry.days} days). You&rsquo;ll be notified 48 hours before it lapses.
                  </p>
                )}
              </Field>
            )}
          </Section>
        )}

        {step === 3 && (
          <Section title="Media Upload">
            <Field label="Property Images">
              <FilePicker
                accept={PHOTO_ACCEPT}
                multiple
                onPick={(files) => addImages(files)}
                hint={`JPEG or PNG, up to ${MAX_PHOTO_MB}MB each · ${MAX_PHOTOS} images max`}
              />
              {images.length > 0 && (
                <ul className="mt-3 space-y-1 text-sm text-ink-600">
                  {images.map((f, i) => (
                    <li key={i} className="flex items-center justify-between rounded-lg bg-bone px-3 py-1.5">
                      <span className="truncate">{f.name}</span>
                      <button type="button" className="text-red-600" onClick={() => setImages((p) => p.filter((_, j) => j !== i))}>
                        remove
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Field>
            <Field label="Video (Optional)">
              <FilePicker
                accept={VIDEO_ACCEPT}
                onPick={(files) => pickVideo(files[0] ?? null)}
                hint={video ? video.name : `MP4, up to ${MAX_VIDEO_MB}MB`}
              />
            </Field>
            {mediaError && (
              <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
                {mediaError}
              </p>
            )}
          </Section>
        )}

        {step === 4 && (
          <Section title="Document Upload">
            <p className="text-sm text-ink-500">
              Upload all required documents for verification. This improves buyer trust and listing performance.
            </p>
            <div className="space-y-3">
              {DOC_SLOTS.map((slot) => (
                <div key={slot.key} className="rounded-xl border border-line p-4">
                  <p className="text-sm font-medium text-ink-800">
                    {slot.label} {slot.required && <span className="text-red-500">*</span>}
                  </p>
                  <div className="mt-2">
                    <FilePicker
                      accept="application/pdf,image/jpeg,image/png"
                      compact
                      onPick={(files) => setDocs((prev) => ({ ...prev, [slot.key]: files[0] }))}
                      hint={docs[slot.key]?.name ?? 'Choose File'}
                    />
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

        {step === 5 && (
          <Section title="Authority Declaration">
            <p className="text-sm text-ink-500">Declare your authority to sell this property</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Choice active={authority === 'owner'} onClick={() => setAuthority('owner')} title="Direct Owner" sub="I am the registered owner" />
              <Choice active={authority === 'power_of_attorney'} onClick={() => setAuthority('power_of_attorney')} title="Power of Attorney" sub="Authorized representative" />
            </div>
            {authority === 'power_of_attorney' && (
              <>
                <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
                  Power-of-attorney sellers must have their PoA document verified before the
                  listing can go live.
                </p>

                {/*
                  Three states, because the upload endpoint has three answers.
                  A document already on file 409s unless it was rejected, so
                  offering an upload in that case would fail every time.
                */}
                {poaUploaded || (poa?.has_document && poa.status !== 'rejected') ? (
                  <p className="rounded-lg bg-emerald-deep/5 px-3 py-2 text-xs text-emerald-deep">
                    {poaUploaded || poa?.status === 'pending'
                      ? 'Your Power of Attorney document is on file and awaiting review.'
                      : 'Your Power of Attorney document has been verified.'}
                  </p>
                ) : (
                  <Field label="Power of Attorney Document">
                    {poa?.status === 'rejected' && (
                      <p className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
                        Your previous document was rejected
                        {poa.rejection_reason ? `: ${poa.rejection_reason}` : ''}. Please upload a
                        replacement.
                      </p>
                    )}
                    <FilePicker
                      accept={POA_ACCEPT}
                      onPick={(files) => {
                        const f = files[0] ?? null;
                        if (f && f.size > MAX_POA_MB * 1024 * 1024) {
                          setPoaError(`${f.name} exceeds the ${MAX_POA_MB}MB limit.`);
                          return;
                        }
                        setPoaError(null);
                        setPoaFile(f);
                      }}
                      hint={poaFile ? poaFile.name : `PDF or JPEG, up to ${MAX_POA_MB}MB`}
                    />
                    <button
                      type="button"
                      disabled={!poaFile || poaBusy}
                      onClick={() => void uploadPoa()}
                      className="mt-3 rounded-lg bg-emerald-deep px-4 py-2 text-sm font-medium text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {poaBusy ? 'Uploading…' : 'Upload document'}
                    </button>
                    {poaError && (
                      <p role="alert" className="mt-2 text-xs text-red-700">
                        {poaError}
                      </p>
                    )}
                  </Field>
                )}
              </>
            )}
          </Section>
        )}

        {step === 6 && (
          <Section title="Review & Submit">
            <div className="rounded-xl bg-bone/70 p-5">
              <p className="text-sm font-medium text-ink-800">Listing Preview</p>
              <p className="text-xs text-ink-500">This is how your listing will appear to buyers</p>
              <div className="mt-3 rounded-lg border border-line bg-surface-card p-4">
                <p className="font-medium text-ink-900">{title || '—'}</p>
                <p className="text-sm text-ink-500">{address || '—'}</p>
                <p className="mt-1 font-display text-lg text-emerald-deep">
                  {priceKobo > 0 ? formatNaira(priceKobo) : '—'}
                </p>
              </div>
            </div>
            <dl className="mt-4 divide-y divide-line text-sm">
              <Row k="Property Type" v={PROPERTY_TYPES.find((p) => p.value === propertyType)?.label ?? '—'} />
              <Row k="Location" v={[lga, state].filter(Boolean).join(', ') || '—'} />
              <Row k="Price" v={priceKobo > 0 ? formatNaira(priceKobo) : '—'} />
              <Row k="Sale Type" v={saleType === 'distress' ? 'Distress Sale' : 'Normal Sale'} />
              <Row k="Authority" v={authority === 'owner' ? 'Direct Owner' : 'Power of Attorney'} />
              <Row k="Images / Documents" v={`${images.length} image(s), ${Object.keys(docs).length} document(s)`} />
            </dl>
            <p className="mt-4 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-700">
              <span className="font-medium">Verification Required.</span> Your listing will be reviewed within
              24–48 hours. You&rsquo;ll be notified once it&rsquo;s approved and live.
            </p>
            {error && <p role="alert" className="mt-3 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
            {warning && <p role="alert" className="mt-3 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-700">{warning}</p>}
          </Section>
        )}
      </div>

      {/* Footer nav */}
      <div className="mt-6 flex items-center justify-between">
        <button
          type="button"
          disabled={step === 0 || submitting}
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          className="rounded-lg bg-ink-300/20 px-5 py-2.5 text-sm font-medium text-ink-600 disabled:opacity-40"
        >
          ← Previous
        </button>
        {step < 6 ? (
          <button
            type="button"
            disabled={!canAdvance()}
            onClick={() =>
              setStep((s) => {
                const next = Math.min(6, s + 1);
                setMaxVisited((m) => Math.max(m, next));
                return next;
              })
            }
            className="rounded-lg bg-emerald-deep px-6 py-2.5 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:opacity-50"
          >
            Next →
          </button>
        ) : (
          <button
            type="button"
            disabled={submitting}
            onClick={submit}
            className="rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-semibold text-emerald-deep transition hover:bg-amber-600 disabled:opacity-60"
          >
            {submitting ? 'Submitting…' : 'Submit for Review ⊙'}
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Form field — Figma node 244:401 (Text Input) / 244:389 (Dropdown).
 *
 * 48px tall, 12px radius, 16px inset, 16px text, on a `#d1d5dc` border. That
 * border is `line-strong`, which SCRUM-164 defined and nothing used until now —
 * it is specifically the input border, distinct from the `#e5e7eb` used on card
 * edges and dividers.
 *
 * Placeholder is `#1a1a1a` at 50%, not a separate grey (node 244:402).
 *
 * The CreateListing artboard reports 48.8px heights and 0.8px borders; those are
 * sub-pixel borders accumulating into the height, not a scale factor — the
 * radii, gaps, insets and type sizes are all clean integers.
 */
const inputCls =
  'h-12 w-full rounded-xl border border-line-strong bg-surface-card px-4 text-base text-ink-900 outline-none transition placeholder:text-ink-900/50 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20';

/** Multi-line variant — 12px vertical padding rather than a fixed height. */
const textareaCls =
  'w-full rounded-xl border border-line-strong bg-surface-card px-4 py-3 text-base leading-6 text-ink-900 outline-none transition placeholder:text-ink-900/50 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    // Heading 2 is 24/32 bold in #0f3d2e; fields sit on a 24px rhythm with an
    // 8px label-to-input gap (nodes 244:385, 244:383, 244:386).
    <div className="space-y-6">
      <h2 className="font-display text-2xl font-bold leading-8 text-emerald-deep">{title}</h2>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    // Label is 14/20 semibold in #364153 (ink-700) with an 8px gap to the
    // control — Figma node 244:388.
    <label className="block space-y-2">
      <span className="block text-sm font-semibold leading-5 text-ink-700">{label}</span>
      {children}
    </label>
  );
}

function Choice({ active, onClick, title, sub }: { active: boolean; onClick: () => void; title: string; sub: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-xl px-4 py-5 text-center transition ${
        active ? 'bg-emerald-deep text-bone' : 'border border-ink-300/40 text-ink-800 hover:border-ink-500'
      }`}
    >
      <p className="font-semibold">{title}</p>
      <p className={`text-xs ${active ? 'text-bone/70' : 'text-ink-500'}`}>{sub}</p>
    </button>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between py-3">
      <dt className="text-ink-500">{k}</dt>
      <dd className="font-medium text-ink-900">{v}</dd>
    </div>
  );
}

function FilePicker({
  accept,
  multiple,
  compact,
  onPick,
  hint,
}: {
  accept: string;
  multiple?: boolean;
  compact?: boolean;
  onPick: (files: File[]) => void;
  hint: string;
}) {
  return (
    <label
      className={`flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-ink-300/50 text-sm text-ink-600 transition hover:border-emerald-accent ${
        compact ? 'bg-bone px-4 py-2' : 'flex-col px-4 py-10'
      }`}
    >
      <span aria-hidden>⭱</span>
      <span className="text-center">{hint}</span>
      <input
        type="file"
        accept={accept}
        multiple={multiple}
        className="hidden"
        onChange={(e) => onPick(Array.from(e.target.files ?? []))}
      />
    </label>
  );
}
