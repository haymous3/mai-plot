'use client';

import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';

import type { SellerOffer } from '@/lib/api';
import { formatNaira } from '@/lib/format';

type Tab = 'all' | 'pending' | 'accepted' | 'countered' | 'rejected';
const TABS: { key: Tab; label: string }[] = [
  { key: 'all', label: 'All Offers' },
  { key: 'pending', label: 'Pending' },
  { key: 'accepted', label: 'Accepted' },
  { key: 'countered', label: 'Countered' },
  { key: 'rejected', label: 'Rejected' },
];

const STATUS_BADGE: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-700',
  accepted: 'bg-emerald-deep/10 text-emerald-deep',
  countered: 'bg-blue-100 text-blue-700',
  rejected: 'bg-red-100 text-red-700',
  withdrawn: 'bg-ink-300/20 text-ink-500',
};

function pct(offered: number, asking: number): { text: string; up: boolean } {
  if (asking <= 0) return { text: '0.0%', up: true };
  const diff = ((offered - asking) / asking) * 100;
  return { text: `${Math.abs(diff).toFixed(1)}%`, up: diff >= 0 };
}

export function OffersList({ offers }: { offers: SellerOffer[] }) {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>('all');
  const [openId, setOpenId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [counter, setCounter] = useState('');

  const visible = useMemo(
    () => (tab === 'all' ? offers : offers.filter((o) => o.status === tab)),
    [offers, tab],
  );

  async function act(offer: SellerOffer, action: 'accept' | 'reject' | 'counter') {
    setBusyId(offer.id);
    setError(null);
    try {
      const init: RequestInit = { method: 'POST' };
      if (action === 'counter') {
        const kobo = Math.round(Number(counter.replace(/[^0-9.]/g, '')) * 100);
        if (!(kobo > 0)) {
          setError('Enter a valid counter amount.');
          return;
        }
        init.headers = { 'content-type': 'application/json' };
        init.body = JSON.stringify({ counter_amount_kobo: kobo });
      }
      const resp = await fetch(`/api/seller/offers/${offer.id}/${action}`, init);
      if (!resp.ok) {
        const body = (await resp.json().catch(() => ({}))) as { message?: string };
        setError(body.message ?? 'Could not update the offer. Please retry.');
        return;
      }
      setCounter('');
      setOpenId(null);
      router.refresh();
    } catch {
      setError('Could not reach the server. Please retry.');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <div className="mt-6 flex flex-wrap gap-1 rounded-xl border border-ink-300/25 bg-white p-1">
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

      <div className="mt-4 space-y-3">
        {visible.length === 0 ? (
          <div className="rounded-xl border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center text-sm text-ink-500">
            No offers in this view.
          </div>
        ) : (
          visible.map((o) => {
            const diff = pct(o.offered_price_kobo, o.asking_price_kobo);
            const open = openId === o.id;
            const actionable = o.status === 'pending';
            return (
              <div key={o.id} className="rounded-2xl border border-ink-300/25 bg-white p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-ink-900">
                      {o.property_title}, {o.lga}
                    </p>
                    <p className="text-xs text-ink-500">Buyer: {o.buyer_ref}</p>
                  </div>
                  <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium capitalize ${STATUS_BADGE[o.status] ?? 'bg-ink-300/20 text-ink-500'}`}>
                    {o.status}
                  </span>
                </div>

                <div className="mt-3 flex flex-wrap items-end gap-x-8 gap-y-2 text-sm">
                  <Metric label="Offer Price" value={formatNaira(o.offered_price_kobo)} strong />
                  <Metric label="Asking Price" value={formatNaira(o.asking_price_kobo)} />
                  <div>
                    <p className="text-xs text-ink-500">Difference</p>
                    <p className={`font-medium ${diff.up ? 'text-emerald-deep' : 'text-red-600'}`}>
                      {diff.up ? '▲' : '▼'} {diff.text}
                    </p>
                  </div>
                  {o.counter_price_kobo != null && (
                    <Metric label="You Countered" value={formatNaira(o.counter_price_kobo)} />
                  )}
                </div>

                <div className="mt-3 flex items-center justify-between">
                  <p className="text-xs text-ink-500">{new Date(o.created_at).toLocaleDateString()}</p>
                  <button
                    type="button"
                    onClick={() => setOpenId(open ? null : o.id)}
                    className="text-sm font-medium text-amber-600 hover:underline"
                  >
                    {open ? 'Hide Details ▲' : 'View Details ▼'}
                  </button>
                </div>

                {open && (
                  <div className="mt-3 rounded-xl bg-bone/70 p-4">
                    <p className="text-sm font-medium text-ink-800">Buyer Message</p>
                    <p className="mt-1 rounded-lg bg-white px-3 py-2 text-sm text-ink-700">
                      {o.note?.trim() || 'No message provided.'}
                    </p>

                    {actionable ? (
                      <>
                        <div className="mt-3 grid gap-2 sm:grid-cols-2">
                          <button
                            type="button"
                            disabled={busyId === o.id}
                            onClick={() => act(o, 'accept')}
                            className="rounded-lg bg-emerald-deep px-4 py-2.5 text-sm font-semibold text-white transition hover:brightness-95 disabled:opacity-60"
                          >
                            ✓ Accept Offer
                          </button>
                          <button
                            type="button"
                            disabled={busyId === o.id}
                            onClick={() => act(o, 'reject')}
                            className="rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:brightness-95 disabled:opacity-60"
                          >
                            ✕ Reject Offer
                          </button>
                        </div>
                        <div className="mt-2 flex gap-2">
                          <input
                            value={counter}
                            onChange={(e) => setCounter(e.target.value)}
                            inputMode="numeric"
                            placeholder="Enter counter offer amount (₦)"
                            className="flex-1 rounded-lg border border-ink-300/50 bg-white px-3.5 py-2 text-sm outline-none focus:border-emerald-accent"
                          />
                          <button
                            type="button"
                            disabled={busyId === o.id}
                            onClick={() => act(o, 'counter')}
                            className="rounded-lg bg-amber-500 px-5 py-2 text-sm font-semibold text-emerald-deep transition hover:bg-amber-600 disabled:opacity-60"
                          >
                            Counter
                          </button>
                        </div>
                      </>
                    ) : o.status === 'countered' ? (
                      <p className="mt-3 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700">
                        Counter offer sent{o.counter_price_kobo != null ? ` — ${formatNaira(o.counter_price_kobo)}` : ''}. Awaiting the buyer&rsquo;s response.
                      </p>
                    ) : null}

                    {error && busyId === null && openId === o.id && (
                      <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>
                    )}
                  </div>
                )}
              </div>
            );
          })
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
