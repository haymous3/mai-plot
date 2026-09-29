'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import { NIGERIAN_BANKS, bankName } from '@/lib/nigerian-banks';
import type { PayoutAccount } from '@/lib/payout-account';
import {
  cleanAccountNumber,
  isCompleteAccountNumber,
  payoutErrorMessage,
} from '@/lib/payout-account';

/**
 * Payout bank account — view and set/change (SCRUM-223). Role-agnostic: the
 * seller page uses it now, the realtor profile next.
 *
 * The flow is built around one idea: the person must SEE the bank's name for
 * the number they typed, and say "that's me", before anything is saved.
 *   1. bank + 10-digit number
 *   2. we ask the bank who owns it (GET resolve) — automatically, once both are
 *      complete; a wrong digit shows up here as a stranger's name or "not found"
 *   3. "This is my account" + the password (a stolen session alone cannot
 *      redirect a payout)
 *   4. save — the server resolves again and stores the bank's name, never ours
 * After a save an email goes to the account holder; the success note says so,
 * so that email is expected rather than alarming.
 */

type Resolution =
  | { state: 'idle' }
  | { state: 'checking' }
  | { state: 'resolved'; name: string }
  | { state: 'error'; message: string };

const CONTROL =
  'mt-2 block h-12 w-full rounded-xl border border-line bg-white px-4 text-sm text-ink-900 outline-none transition placeholder:text-ink-400 focus:border-emerald-deep focus:ring-2 focus:ring-emerald-deep/20 disabled:cursor-not-allowed disabled:bg-surface-muted';

export function PayoutAccountForm({ initial }: { initial: PayoutAccount | null }) {
  const router = useRouter();
  const [account, setAccount] = useState<PayoutAccount | null>(initial);
  const [editing, setEditing] = useState(initial === null);
  const [bankCode, setBankCode] = useState('');
  const [number, setNumber] = useState('');
  const [resolution, setResolution] = useState<Resolution>({ state: 'idle' });
  const [confirmed, setConfirmed] = useState(false);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedNote, setSavedNote] = useState<string | null>(null);
  // Only the latest lookup may land: typing quickly past a bank change must
  // never show the name for a number that is no longer in the field.
  const lookup = useRef(0);

  useEffect(() => {
    setConfirmed(false);
    if (!bankCode || !isCompleteAccountNumber(number)) {
      setResolution({ state: 'idle' });
      return;
    }
    const id = ++lookup.current;
    setResolution({ state: 'checking' });
    const qs = new URLSearchParams({ account_number: number, bank_code: bankCode });
    fetch(`/api/settings/payout-account/resolve?${qs}`, { cache: 'no-store' })
      .then(async (resp) => {
        const body = (await resp.json().catch(() => ({}))) as {
          account_name?: string;
          error_code?: string;
        };
        if (id !== lookup.current) return;
        if (resp.ok && body.account_name) {
          setResolution({ state: 'resolved', name: body.account_name });
        } else {
          setResolution({ state: 'error', message: payoutErrorMessage(body.error_code) });
        }
      })
      .catch(() => {
        if (id === lookup.current) {
          setResolution({ state: 'error', message: payoutErrorMessage('RECIPIENT_UNAVAILABLE') });
        }
      });
  }, [bankCode, number]);

  function startEditing() {
    setEditing(true);
    setSavedNote(null);
    setError(null);
  }

  function cancel() {
    setEditing(false);
    setBankCode('');
    setNumber('');
    setPassword('');
    setError(null);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch('/api/settings/payout-account', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ account_number: number, bank_code: bankCode, password }),
      });
      const body = (await resp.json().catch(() => ({}))) as PayoutAccount & {
        error_code?: string;
      };
      if (!resp.ok) {
        setError(payoutErrorMessage(body.error_code));
        if (body.error_code === 'PASSWORD_INCORRECT') setPassword('');
        return;
      }
      const firstTime = account === null;
      setAccount(body);
      setEditing(false);
      setBankCode('');
      setNumber('');
      setPassword('');
      setSavedNote(
        `Payout account ${firstTime ? 'added' : 'changed'}. We’ve emailed you to confirm the change.`,
      );
      // Server components (the dashboard nudge) read the account on render.
      router.refresh();
    } catch {
      setError(payoutErrorMessage('RECIPIENT_UNAVAILABLE'));
    } finally {
      setBusy(false);
    }
  }

  const canSave = resolution.state === 'resolved' && confirmed && password !== '' && !busy;

  return (
    <div className="space-y-4">
      {savedNote && (
        <p
          role="status"
          className="rounded-xl bg-emerald-deep/10 px-4 py-3 text-sm font-medium text-emerald-deep"
        >
          {savedNote}
        </p>
      )}

      {account && !editing && (
        <div className="rounded-2xl border border-line bg-surface-card p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
                Payouts go to
              </p>
              <p className="mt-2 text-lg font-semibold text-ink-900">{account.account_name}</p>
              <p className="mt-1 text-sm text-ink-600">
                {bankName(account.bank_code)} · {account.account_number_masked}
              </p>
              <span
                className={`mt-3 inline-block rounded-full px-2.5 py-1 text-xs font-medium ${
                  account.recipient_ready
                    ? 'bg-emerald-deep/10 text-emerald-deep'
                    : 'bg-amber-50 text-amber-700'
                }`}
              >
                {account.recipient_ready ? 'Ready for payouts' : 'Being set up with the bank'}
              </span>
            </div>
            <button
              type="button"
              onClick={startEditing}
              className="rounded-lg border border-line px-4 py-2 text-sm font-semibold text-ink-700 transition hover:border-emerald-deep hover:text-emerald-deep"
            >
              Change account
            </button>
          </div>
        </div>
      )}

      {editing && (
        <div className="rounded-2xl border border-line bg-surface-card p-6">
          <h2 className="text-base font-semibold text-ink-900">
            {account ? 'Change payout account' : 'Add your payout account'}
          </h2>
          <p className="mt-1 text-sm text-ink-500">
            An account in your own name. We check it with your bank before saving.
          </p>

          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <label className="block text-sm font-medium text-ink-700">
              Bank
              <select
                value={bankCode}
                onChange={(e) => setBankCode(e.target.value)}
                disabled={busy}
                className={CONTROL}
              >
                <option value="">Select your bank</option>
                {NIGERIAN_BANKS.map((b) => (
                  <option key={b.code} value={b.code}>
                    {b.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm font-medium text-ink-700">
              Account number
              <input
                value={number}
                onChange={(e) => setNumber(cleanAccountNumber(e.target.value))}
                inputMode="numeric"
                autoComplete="off"
                placeholder="10-digit NUBAN"
                disabled={busy}
                className={`${CONTROL} tracking-[0.08em]`}
              />
            </label>
          </div>

          <div className="mt-4" aria-live="polite">
            {resolution.state === 'checking' && (
              <p className="rounded-xl bg-surface-muted px-4 py-3 text-sm text-ink-600">
                Checking with your bank…
              </p>
            )}
            {resolution.state === 'error' && (
              <p className="rounded-xl bg-red-50 px-4 py-3 text-sm font-medium text-status-danger">
                {resolution.message}
              </p>
            )}
            {resolution.state === 'resolved' && (
              <div className="rounded-xl border border-emerald-deep/30 bg-emerald-deep/5 px-4 py-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
                  Name on this account, from your bank
                </p>
                <p className="mt-1 text-lg font-semibold text-ink-900">{resolution.name}</p>
                <label className="mt-3 flex items-start gap-3 text-sm text-ink-700">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                    disabled={busy}
                    className="mt-0.5 h-4 w-4 flex-none accent-emerald-deep"
                  />
                  <span>
                    This is my account. If the name isn&rsquo;t yours, check the number — payouts
                    sent here can&rsquo;t be recalled.
                  </span>
                </label>
              </div>
            )}
          </div>

          {resolution.state === 'resolved' && (
            <label className="mt-4 block text-sm font-medium text-ink-700">
              Confirm with your password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && canSave) void save();
                }}
                autoComplete="current-password"
                disabled={busy}
                className={CONTROL}
              />
              <span className="mt-1.5 block text-xs text-ink-500">
                So that nobody with access to your screen can redirect your money.
              </span>
            </label>
          )}

          {error && (
            <p
              role="alert"
              className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm font-medium text-status-danger"
            >
              {error}
            </p>
          )}

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void save()}
              disabled={!canSave}
              className="rounded-lg bg-emerald-deep px-5 py-2.5 text-sm font-semibold text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:bg-line disabled:text-ink-400"
            >
              {busy ? 'Saving…' : 'Save payout account'}
            </button>
            {account && (
              <button
                type="button"
                onClick={cancel}
                disabled={busy}
                className="rounded-lg px-4 py-2.5 text-sm font-semibold text-ink-500 transition hover:text-ink-700"
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
