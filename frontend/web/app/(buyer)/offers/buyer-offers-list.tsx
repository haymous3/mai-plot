'use client';

import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';

import type { BuyerOffer } from '@/lib/api';
import { formatNaira } from '@/lib/format';

type Tab = 'all' | 'pending' | 'countered' | 'accepted' | 'rejected';
const TABS: { key: Tab; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'pending', label: 'Pending' },
  { key: 'countered', label: 'Countered' },
  { key: 'accepted', label: 'Accepted' },
  { key: 'rejected', label: 'Rejected' },
];

const STATUS_BADGE: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-700',
  accepted: 'bg-emerald-deep/10 text-emerald-deep',
  countered: 'bg-blue-100 text-blue-700',
  rejected: 'bg-red-100 text-red-700',
  withdrawn: 'bg-ink-300/20 text-ink-500',
};

export function BuyerOffersList({ offers }: { offers: BuyerOffer[] }) {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>('all');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const visible = useMemo(
    () => (tab === 'all' ? offers : offers.filter((o) => o.status === tab)),
    [offers, tab],
  );

  async function respond(offer: BuyerOffer, action: 'accept' | 'reject') {
    setBusyId(offer.id);
    setError(null);
    try {
      const resp = await fetch(`/api/buyer/offers/${offer.id}/respond`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ action }),
      });
      const body = (await resp.json().catch(() => ({}))) as {
        transaction_id?: string;
        message?: string;
      };
      if (!resp.ok) {
        setError(body.message ?? 'Could not respond. Please retry.');
        return;
      }
      // Accepting a counter creates a deal — take the buyer to it.
      if (action === 'accept' && body.transaction_id) {
        router.push(`/deals/${body.transaction_id}`);
        return;
      }
      router.refresh();
    } catch {
      setError('Could not reach the server. Please retry.');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap gap-1 rounded-xl border border-ink-300/25 bg-white p-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
              tab === t.key ? 'bg-emerald-deep text-bone' : 'text-ink-600 hover:bg-bone'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}

      <div className="mt-4 space-y-3">
        {visible.length === 0 ? (
          <div className="rounded-xl border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-500">
            {tab === 'all' ? 'You haven’t placed any offers yet.' : 'No offers in this view.'}
          </div>
        ) : (
          visible.map((o) => (
            <div key={o.id} className="rounded-2xl border border-ink-300/25 bg-white p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <a href={`/listings/${o.listing_id}`} className="font-medium text-ink-900 hover:underline">
                    {o.property_title}
                  </a>
                  <p className="text-xs text-ink-500">📍 {o.lga}, {o.state}</p>
                </div>
                <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium capitalize ${STATUS_BADGE[o.status] ?? 'bg-ink-300/20 text-ink-500'}`}>
                  {o.status}
                </span>
              </div>

              <div className="mt-3 flex flex-wrap items-end gap-x-8 gap-y-2 text-sm">
                <Metric label="Your Offer" value={formatNaira(o.offered_price_kobo)} strong />
                <Metric label="Asking Price" value={formatNaira(o.asking_price_kobo)} />
                {o.counter_price_kobo != null && (
                  <Metric label="Seller Countered" value={formatNaira(o.counter_price_kobo)} />
                )}
              </div>

              {o.status === 'countered' && (
                <div className="mt-3 rounded-xl bg-blue-50 p-3">
                  <p className="text-sm text-blue-800">
                    The seller countered at {o.counter_price_kobo != null ? formatNaira(o.counter_price_kobo) : 'a new price'}. Accept to proceed, or reject.
                  </p>
                  <div className="mt-2 flex gap-2">
                    <button
                      type="button"
                      disabled={busyId === o.id}
                      onClick={() => respond(o, 'accept')}
                      className="rounded-lg bg-emerald-deep px-4 py-2 text-sm font-semibold text-white transition hover:brightness-95 disabled:opacity-60"
                    >
                      ✓ Accept Counter
                    </button>
                    <button
                      type="button"
                      disabled={busyId === o.id}
                      onClick={() => respond(o, 'reject')}
                      className="rounded-lg border border-ink-300/50 px-4 py-2 text-sm font-medium text-ink-700 transition hover:border-ink-500 disabled:opacity-60"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              )}

              <p className="mt-2 text-xs text-ink-500">{new Date(o.created_at).toLocaleDateString()}</p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function Metric({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div>
      <p className="text-xs text-ink-500">{label}</p>
      <p className={strong ? 'font-display text-emerald-deep' : 'text-ink-700'}>{value}</p>
    </div>
  );
}
