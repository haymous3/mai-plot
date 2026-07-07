'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { formatNaira } from '@/lib/format';

type Modal = 'bid' | 'interest' | 'deposit' | null;

/** Sticky property-detail action bar + Place-a-Bid / Express-Interest /
 * Make-a-deposit modals (SCRUM-95). `deal` is the buyer's existing transaction
 * for this listing (if any) — it enables Make-a-deposit. */
export function PropertyActions({
  listingId,
  askingPriceKobo,
  deal,
}: {
  listingId: string;
  askingPriceKobo: number;
  deal: { transactionId: string; agreedPriceKobo: number } | null;
}) {
  const [modal, setModal] = useState<Modal>(null);

  return (
    <>
      <div className="sticky bottom-0 z-10 -mx-6 mt-6 flex items-center justify-between gap-3 border-t border-ink-300/25 bg-white/95 px-6 py-3 backdrop-blur">
        <div className="hidden sm:block">
          <p className="text-xs text-ink-500">Starting from</p>
          <p className="font-display text-lg text-emerald-deep">{formatNaira(askingPriceKobo)}</p>
        </div>
        <div className="flex flex-1 gap-2 sm:flex-none">
          {deal && (
            <button
              type="button"
              onClick={() => setModal('deposit')}
              className="flex-1 rounded-lg border border-emerald-deep px-4 py-2.5 text-sm font-semibold text-emerald-deep transition hover:bg-emerald-deep/5 sm:flex-none"
            >
              Make a deposit
            </button>
          )}
          <button
            type="button"
            onClick={() => setModal('bid')}
            className="flex-1 rounded-lg border border-ink-300/50 px-4 py-2.5 text-sm font-semibold text-ink-900 transition hover:border-ink-500 sm:flex-none"
          >
            Place a Bid
          </button>
          <button
            type="button"
            onClick={() => setModal('interest')}
            className="flex-1 rounded-lg bg-emerald-deep px-4 py-2.5 text-sm font-semibold text-bone transition hover:bg-emerald-accent sm:flex-none"
          >
            Express Interest
          </button>
        </div>
      </div>

      {modal === 'bid' && (
        <BidModal
          listingId={listingId}
          askingPriceKobo={askingPriceKobo}
          onClose={() => setModal(null)}
        />
      )}
      {modal === 'interest' && (
        <InterestModal listingId={listingId} onClose={() => setModal(null)} />
      )}
      {modal === 'deposit' && deal && (
        <DepositModal deal={deal} onClose={() => setModal(null)} />
      )}
    </>
  );
}

function Modal({
  title,
  subtitle,
  children,
  onClose,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink-900/40 p-4 sm:items-center">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="font-display text-xl text-ink-900">{title}</h3>
            {subtitle && <p className="mt-1 text-sm text-ink-500">{subtitle}</p>}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="text-ink-400 hover:text-ink-900">
            ✕
          </button>
        </div>
        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
}

function BidModal({
  listingId,
  askingPriceKobo,
  onClose,
}: {
  listingId: string;
  askingPriceKobo: number;
  onClose: () => void;
}) {
  const router = useRouter();
  const [naira, setNaira] = useState(String(Math.round(askingPriceKobo / 100)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const bidKobo = (Number(naira.replace(/\D/g, '')) || 0) * 100;
  const vsAsking = askingPriceKobo > 0 ? ((bidKobo - askingPriceKobo) / askingPriceKobo) * 100 : 0;

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const resp = await fetch('/api/buyer/offers', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ listing_id: listingId, amount_kobo: bidKobo }),
      });
      if (resp.ok) {
        setDone(true);
        return;
      }
      const b = (await resp.json()) as { error_code?: string };
      setError(
        b.error_code === 'CANNOT_OFFER_OWN_LISTING'
          ? 'You cannot bid on your own listing.'
          : b.error_code === 'LISTING_NOT_AVAILABLE'
            ? 'This property is not available for new bids.'
            : 'Could not submit your bid. Please retry.',
      );
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Place Your Bid"
      subtitle="Enter your bid. Once submitted, the seller is notified instantly."
      onClose={onClose}
    >
      {done ? (
        <div className="text-center">
          <p className="text-2xl">✓</p>
          <p className="mt-2 text-sm text-ink-700">Your bid was submitted. You&rsquo;ll be notified when the seller responds.</p>
          <button
            type="button"
            onClick={() => {
              router.refresh();
              onClose();
            }}
            className="mt-4 w-full rounded-lg bg-emerald-deep px-4 py-2.5 text-sm font-semibold text-bone hover:bg-emerald-accent"
          >
            Done
          </button>
        </div>
      ) : (
        <>
          <label className="block text-sm font-medium text-ink-700">Your Bid Amount (₦)</label>
          <input
            inputMode="numeric"
            value={naira}
            onChange={(e) => setNaira(e.target.value.replace(/\D/g, ''))}
            className="mt-1.5 w-full rounded-md border border-ink-300/60 px-3.5 py-2.5 text-sm text-ink-900 outline-none focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
          />
          <div className="mt-3 flex items-center justify-between rounded-lg bg-bone px-3 py-2 text-xs">
            <span className="text-ink-500">Asking {formatNaira(askingPriceKobo)}</span>
            {bidKobo > 0 && (
              <span className={vsAsking < 0 ? 'font-medium text-red-600' : 'font-medium text-emerald-deep'}>
                {vsAsking >= 0 ? '+' : ''}
                {vsAsking.toFixed(1)}% vs asking
              </span>
            )}
          </div>
          {error && <p role="alert" className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          <div className="mt-4 flex gap-2">
            <button type="button" onClick={onClose} className="flex-1 rounded-lg border border-ink-300/50 px-4 py-2.5 text-sm font-medium text-ink-700">
              Cancel
            </button>
            <button
              type="button"
              disabled={busy || bidKobo <= 0}
              onClick={submit}
              className="flex-1 rounded-lg bg-emerald-deep px-4 py-2.5 text-sm font-semibold text-bone hover:bg-emerald-accent disabled:opacity-50"
            >
              {busy ? 'Submitting…' : 'Submit Offer'}
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}

function InterestModal({ listingId, onClose }: { listingId: string; onClose: () => void }) {
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const resp = await fetch(`/api/buyer/listings/${listingId}/interest`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ message: message.trim() || null }),
      });
      if (resp.ok) {
        setDone(true);
        return;
      }
      setError('Could not send your interest. Please retry.');
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Express Interest"
      subtitle="Let the seller know you're interested. A realtor will be assigned to guide you."
      onClose={onClose}
    >
      {done ? (
        <div className="text-center">
          <p className="text-2xl">✓</p>
          <p className="mt-2 text-sm text-ink-700">Interest sent. A realtor will reach out to guide you.</p>
          <button type="button" onClick={onClose} className="mt-4 w-full rounded-lg bg-emerald-deep px-4 py-2.5 text-sm font-semibold text-bone hover:bg-emerald-accent">
            Done
          </button>
        </div>
      ) : (
        <>
          <label className="block text-sm font-medium text-ink-700">Message (optional)</label>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={3}
            placeholder="Add a message for the seller (optional)"
            className="mt-1.5 w-full rounded-md border border-ink-300/60 px-3.5 py-2.5 text-sm text-ink-900 outline-none focus:border-emerald-accent focus:ring-2 focus:ring-emerald-accent/20"
          />
          {error && <p role="alert" className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          <div className="mt-4 flex gap-2">
            <button type="button" onClick={onClose} className="flex-1 rounded-lg border border-ink-300/50 px-4 py-2.5 text-sm font-medium text-ink-700">
              Cancel
            </button>
            <button type="button" disabled={busy} onClick={submit} className="flex-1 rounded-lg bg-emerald-deep px-4 py-2.5 text-sm font-semibold text-bone hover:bg-emerald-accent disabled:opacity-50">
              {busy ? 'Sending…' : 'Send Interest'}
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}

function DepositModal({
  deal,
  onClose,
}: {
  deal: { transactionId: string; agreedPriceKobo: number };
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const resp = await fetch(`/api/buyer/transactions/${deal.transactionId}/deposit`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          idempotency_key: crypto.randomUUID(),
          amount_kobo: deal.agreedPriceKobo,
        }),
      });
      const b = (await resp.json()) as { authorization_url?: string; error_code?: string };
      if (resp.ok && b.authorization_url) {
        window.location.href = b.authorization_url; // Paystack hosted checkout
        return;
      }
      setError(
        b.error_code === 'AMOUNT_MISMATCH'
          ? 'The deposit amount no longer matches this deal (a loan may cover part of it). Refresh and retry.'
          : b.error_code === 'ALREADY_DEPOSITED'
            ? 'This deposit has already been completed.'
            : 'Could not start the deposit. Please retry.',
      );
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Make a Deposit" subtitle="Fund the escrow for your accepted deal." onClose={onClose}>
      <div className="rounded-lg bg-bone px-4 py-3">
        <p className="text-xs text-ink-500">Amount due</p>
        <p className="font-display text-2xl text-emerald-deep">{formatNaira(deal.agreedPriceKobo)}</p>
      </div>
      <p className="mt-3 text-xs text-ink-500">
        You&rsquo;ll be taken to our secure payment partner to complete the deposit into escrow.
      </p>
      {error && <p role="alert" className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      <div className="mt-4 flex gap-2">
        <button type="button" onClick={onClose} className="flex-1 rounded-lg border border-ink-300/50 px-4 py-2.5 text-sm font-medium text-ink-700">
          Cancel
        </button>
        <button type="button" disabled={busy} onClick={submit} className="flex-1 rounded-lg bg-emerald-deep px-4 py-2.5 text-sm font-semibold text-bone hover:bg-emerald-accent disabled:opacity-50">
          {busy ? 'Starting…' : 'Continue to payment'}
        </button>
      </div>
    </Modal>
  );
}
