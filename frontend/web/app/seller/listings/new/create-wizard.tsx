'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { projectedExpiry } from '@/lib/countdown';
import { formatNaira } from '@/lib/format';

type PropertyType = 'land' | 'residential' | 'commercial';
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

const PROPERTY_TYPES: { value: PropertyType; label: string }[] = [
  { value: 'land', label: 'Land' },
  { value: 'residential', label: 'Residential' },
  { value: 'commercial', label: 'Commercial' },
];

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
  BVN_REQUIRED: 'Complete your identity (BVN) verification before listing a property.',
  POA_NOT_VERIFIED: 'Your power-of-attorney document must be verified before you can publish.',
  SELLER_ROLE_REQUIRED: 'Only seller accounts can create listings.',
  URGENCY_TAG_REQUIRED_FOR_DISTRESS: 'A distress sale needs an urgency window.',
};

// The design shows a map-pin placeholder rather than a real picker; default the
// coordinate to central Lagos so the required geo-point is satisfied.
const DEFAULT_LOCATION = { lat: 6.5244, lng: 3.3792 };

export function CreateListingWizard() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  // Property details
  const [title, setTitle] = useState('');
  const [propertyType, setPropertyType] = useState<PropertyType>('land');
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
  // Documents
  const [docs, setDocs] = useState<Partial<Record<DocKey, File>>>({});
  // Authority
  const [authority, setAuthority] = useState<Authority>('owner');

  const priceKobo = Math.round(Number(priceNaira.replace(/[^0-9.]/g, '')) * 100);
  const expiry = saleType === 'distress' ? projectedExpiry(urgency) : null;

  function canAdvance(): boolean {
    if (step === 0) return title.trim().length > 0 && sizeSqm.trim().length > 0;
    if (step === 1) return address.trim().length > 0 && lga.trim().length > 0 && state.trim().length > 0;
    if (step === 2) return Number.isFinite(priceKobo) && priceKobo > 0;
    return true;
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
      <ol className="mt-6 flex flex-wrap gap-y-4 rounded-2xl border border-ink-300/25 bg-white px-4 py-5">
        {STEPS.map((label, i) => (
          <li key={label} className="flex flex-1 min-w-[120px] flex-col items-center gap-1.5 text-center">
            <span
              className={`flex h-9 w-9 items-center justify-center rounded-full text-sm font-medium ${
                i < step
                  ? 'bg-emerald-deep text-bone'
                  : i === step
                    ? 'bg-emerald-deep text-bone'
                    : 'border border-ink-300/50 text-ink-500'
              }`}
            >
              {i < step ? '✓' : i + 1}
            </span>
            <span className={`text-xs ${i === step ? 'text-ink-900' : 'text-ink-500'}`}>{label}</span>
          </li>
        ))}
      </ol>

      <div className="mt-6 rounded-2xl border border-ink-300/25 bg-white p-6 sm:p-8">
        {step === 0 && (
          <Section title="Property Details">
            <Field label="Listing Title">
              <input className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. 2 Plots of Land, Lekki Phase 1" />
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
              <textarea className={`${inputCls} min-h-32`} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Describe your property in detail…" />
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
              <input className={inputCls} value={priceNaira} onChange={(e) => setPriceNaira(e.target.value)} placeholder="e.g., 45,000,000" inputMode="numeric" />
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
                accept="image/*"
                multiple
                onPick={(files) => setImages((prev) => [...prev, ...files])}
                hint="Drag and drop images here, or browse"
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
                accept="video/*"
                onPick={(files) => setVideo(files[0] ?? null)}
                hint={video ? video.name : 'Upload Video'}
              />
            </Field>
          </Section>
        )}

        {step === 4 && (
          <Section title="Document Upload">
            <p className="text-sm text-ink-500">
              Upload all required documents for verification. This improves buyer trust and listing performance.
            </p>
            <div className="space-y-3">
              {DOC_SLOTS.map((slot) => (
                <div key={slot.key} className="rounded-xl border border-ink-300/30 p-4">
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
              <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
                Power-of-attorney sellers must have their PoA document verified before the listing can go live.
              </p>
            )}
          </Section>
        )}

        {step === 6 && (
          <Section title="Review & Submit">
            <div className="rounded-xl bg-bone/70 p-5">
              <p className="text-sm font-medium text-ink-800">Listing Preview</p>
              <p className="text-xs text-ink-500">This is how your listing will appear to buyers</p>
              <div className="mt-3 rounded-lg border border-ink-300/30 bg-white p-4">
                <p className="font-medium text-ink-900">{title || '—'}</p>
                <p className="text-sm text-ink-500">{address || '—'}</p>
                <p className="mt-1 font-display text-lg text-emerald-deep">
                  {priceKobo > 0 ? formatNaira(priceKobo) : '—'}
                </p>
              </div>
            </div>
            <dl className="mt-4 divide-y divide-ink-300/20 text-sm">
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
            onClick={() => setStep((s) => Math.min(6, s + 1))}
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

const inputCls =
  'w-full rounded-lg border border-ink-300/50 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-4">
      <h2 className="font-display text-xl text-emerald-deep">{title}</h2>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-sm font-medium text-ink-700">{label}</span>
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
