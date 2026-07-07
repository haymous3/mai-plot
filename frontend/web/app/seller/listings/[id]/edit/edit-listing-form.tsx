'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

type SaleType = 'normal' | 'distress';
type UrgencyTag = '7_days' | '14_days' | '30_days';

const URGENCY: { value: UrgencyTag; label: string }[] = [
  { value: '7_days', label: '7 days' },
  { value: '14_days', label: '14 days' },
  { value: '30_days', label: '30 days' },
];

const inputCls =
  'w-full rounded-lg border border-ink-300/50 bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20';

export interface EditableListing {
  id: string;
  title: string;
  description: string | null;
  asking_price_kobo: number;
  sale_type: string;
  urgency_tag: string | null;
}

/** Compact listing editor (SCRUM-98). Patches the core mutable fields; media +
 * documents are managed from the Documents section. */
export function EditListingForm({ listing }: { listing: EditableListing }) {
  const router = useRouter();
  const [title, setTitle] = useState(listing.title);
  const [description, setDescription] = useState(listing.description ?? '');
  const [priceNaira, setPriceNaira] = useState(String(Math.round(listing.asking_price_kobo / 100)));
  const [saleType, setSaleType] = useState<SaleType>(listing.sale_type === 'distress' ? 'distress' : 'normal');
  const [urgency, setUrgency] = useState<UrgencyTag>(
    (listing.urgency_tag as UrgencyTag) ?? '7_days',
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const priceKobo = Math.round(Number(priceNaira.replace(/[^0-9.]/g, '')) * 100);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const payload = {
        title: title.trim(),
        description: description.trim() || null,
        asking_price_kobo: priceKobo,
        sale_type: saleType,
        urgency_tag: saleType === 'distress' ? urgency : null,
      };
      const resp = await fetch(`/api/seller/listings/${listing.id}`, {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const body = (await resp.json().catch(() => ({}))) as { message?: string };
        setError(body.message ?? 'Could not save changes. Please retry.');
        return;
      }
      router.push('/seller/listings');
      router.refresh();
    } catch {
      setError('Could not reach the server. Please retry.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <a href="/seller/listings" className="text-sm text-ink-500 hover:text-ink-800">
        ← Back to Listings
      </a>
      <h1 className="mt-3 font-display text-3xl text-emerald-deep">Edit Listing</h1>
      <p className="mt-1 text-sm text-ink-500">Update your listing details</p>

      <div className="mt-6 space-y-4 rounded-2xl border border-ink-300/25 bg-white p-6">
        <label className="block space-y-1.5">
          <span className="block text-sm font-medium text-ink-700">Title</span>
          <input className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="block space-y-1.5">
          <span className="block text-sm font-medium text-ink-700">Description</span>
          <textarea className={`${inputCls} min-h-28`} value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <label className="block space-y-1.5">
          <span className="block text-sm font-medium text-ink-700">Price (₦)</span>
          <input className={inputCls} value={priceNaira} onChange={(e) => setPriceNaira(e.target.value)} inputMode="numeric" />
        </label>
        <div className="space-y-1.5">
          <span className="block text-sm font-medium text-ink-700">Sale Type</span>
          <div className="flex gap-2">
            {(['normal', 'distress'] as SaleType[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setSaleType(t)}
                className={`rounded-lg px-4 py-2 text-sm capitalize ${saleType === t ? 'bg-emerald-deep text-bone' : 'border border-ink-300/50 text-ink-700'}`}
              >
                {t} sale
              </button>
            ))}
          </div>
        </div>
        {saleType === 'distress' && (
          <div className="space-y-1.5">
            <span className="block text-sm font-medium text-ink-700">Urgency window</span>
            <div className="flex gap-2">
              {URGENCY.map((u) => (
                <button
                  key={u.value}
                  type="button"
                  onClick={() => setUrgency(u.value)}
                  className={`rounded-lg px-4 py-2 text-sm ${urgency === u.value ? 'bg-emerald-deep text-bone' : 'border border-ink-300/50 text-ink-700'}`}
                >
                  {u.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {error && <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <a href="/seller/listings" className="rounded-lg bg-ink-300/20 px-5 py-2.5 text-sm font-medium text-ink-600">
            Cancel
          </a>
          <button
            type="button"
            disabled={saving || !title.trim() || priceKobo <= 0}
            onClick={save}
            className="rounded-lg bg-emerald-deep px-6 py-2.5 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );
}
