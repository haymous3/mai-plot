'use client';

import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';

import type { BankPartner, FinancingSummary } from '@/lib/api';
import { formatNaira } from '@/lib/format';
import { bpsToPercent, monthlyPaymentKobo, totalInterestKobo, totalRepaymentKobo } from '@/lib/loan-math';

const TENURE_OPTIONS = [6, 12, 18, 24];

/** Compact naira for headline figures, e.g. 22_500_000_00 -> "₦22.5M". */
function compactNaira(kobo: number): string {
  const naira = kobo / 100;
  if (naira >= 1_000_000) return `₦${(naira / 1_000_000).toFixed(naira % 1_000_000 === 0 ? 0 : 1)}M`;
  if (naira >= 1_000) return `₦${(naira / 1_000).toFixed(0)}K`;
  return formatNaira(kobo);
}

export function FinancingCalculator({
  summary,
  partners,
}: {
  summary: FinancingSummary;
  partners: BankPartner[];
}) {
  const router = useRouter();
  const price = summary.agreed_price_kobo;
  const maxLoan = summary.max_loan_kobo; // 50% cap
  const minLoan = Math.round(price * 0.1); // 10% floor, matching the design scale
  const step = Math.max(1, Math.round(price / 200));

  const [amount, setAmount] = useState(maxLoan);
  const [bankId, setBankId] = useState(partners[0]?.id ?? '');
  const bank = partners.find((p) => p.id === bankId) ?? partners[0];

  const allowedTenures = useMemo(
    () =>
      TENURE_OPTIONS.filter(
        (t) => !bank || (t >= bank.min_tenure_months && t <= bank.max_tenure_months),
      ),
    [bank],
  );
  const [tenure, setTenure] = useState(
    allowedTenures.includes(12) ? 12 : allowedTenures[0] ?? 12,
  );
  const effectiveTenure = allowedTenures.includes(tenure) ? tenure : allowedTenures[0] ?? tenure;

  const rateBps = bank?.interest_rate_bps ?? 0;
  const monthly = monthlyPaymentKobo(amount, rateBps, effectiveTenure);
  const totalInterest = totalInterestKobo(amount, rateBps, effectiveTenure);
  const total = totalRepaymentKobo(amount, rateBps, effectiveTenure);
  const contribution = price - amount;

  const eligible =
    !!bank && amount >= bank.loan_min_kobo && amount <= bank.loan_max_kobo && amount <= maxLoan;

  function start() {
    if (!bank) return;
    const q = new URLSearchParams({
      bank: bank.id,
      amount: String(amount),
      tenure: String(effectiveTenure),
    });
    router.push(`/loans/apply/${summary.transaction_id}?${q.toString()}`);
  }

  return (
    <div>
      <header className="border-b border-ink-300/30 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-6xl items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-md bg-emerald-deep text-bone">
            <WalletIcon />
          </span>
          <div>
            <h1 className="font-display text-lg text-ink-900">Property Financing</h1>
            <p className="text-xs text-ink-500">Get a loan for your property purchase</p>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-6 px-6 py-8 lg:grid-cols-[1.7fr_1fr]">
        <div className="space-y-6">
          {/* Property summary */}
          <section className="rounded-xl border border-ink-300/25 bg-white p-6">
            <h2 className="font-display text-lg text-ink-900">Property Summary</h2>
            <div className="mt-4 flex gap-4">
              {summary.property.primary_image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={summary.property.primary_image_url}
                  alt=""
                  className="h-24 w-32 flex-none rounded-lg object-cover"
                />
              ) : (
                <div className="flex h-24 w-32 flex-none items-center justify-center rounded-lg bg-bone text-ink-300">
                  <HomeIcon />
                </div>
              )}
              <div>
                <p className="font-medium text-ink-900">{summary.property.title}</p>
                <p className="mt-1 text-sm text-ink-500">
                  {summary.property.lga}, {summary.property.state}
                </p>
                <p className="mt-2">
                  <span className="font-display text-xl text-ink-900">{compactNaira(price)}</span>{' '}
                  <span className="text-xs text-ink-500">Total Price</span>
                </p>
              </div>
            </div>
          </section>

          {/* Calculator */}
          <section className="rounded-xl border border-ink-300/25 bg-white p-6">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="font-display text-lg text-ink-900">Calculate Your Loan</h2>
                <p className="text-sm text-ink-500">Finance up to 50% of the property value</p>
              </div>
              {eligible && (
                <span className="rounded-full bg-emerald-deep/10 px-3 py-1 text-xs font-semibold text-emerald-deep">
                  ✓ Eligible
                </span>
              )}
            </div>

            <div className="mt-6">
              <div className="flex items-end justify-between">
                <label htmlFor="amount" className="text-sm font-medium text-ink-700">
                  Loan Amount
                </label>
                <div className="text-right">
                  <span className="font-display text-2xl text-ink-900">{compactNaira(amount)}</span>
                  <p className="text-xs text-ink-500">
                    {Math.round((amount / price) * 100)}% of property value
                  </p>
                </div>
              </div>
              <input
                id="amount"
                type="range"
                min={minLoan}
                max={maxLoan}
                step={step}
                value={amount}
                onChange={(e) => setAmount(Number(e.target.value))}
                className="mt-4 w-full accent-emerald-deep"
              />
              <div className="mt-1 flex justify-between text-xs text-ink-500">
                <span>{compactNaira(minLoan)} (10%)</span>
                <span>{compactNaira(maxLoan)} (50%)</span>
              </div>
            </div>

            <div className="mt-6">
              <p className="text-sm font-medium text-ink-700">Repayment Period</p>
              <div className="mt-3 grid grid-cols-4 gap-3">
                {TENURE_OPTIONS.map((t) => {
                  const allowed = allowedTenures.includes(t);
                  const active = t === effectiveTenure;
                  return (
                    <button
                      key={t}
                      type="button"
                      disabled={!allowed}
                      onClick={() => setTenure(t)}
                      className={`rounded-lg border py-3 text-center transition ${
                        active
                          ? 'border-emerald-deep bg-emerald-deep/5'
                          : allowed
                            ? 'border-ink-300/40 hover:border-ink-500'
                            : 'cursor-not-allowed border-ink-300/20 opacity-40'
                      }`}
                    >
                      <span className="block font-display text-lg text-ink-900">{t}</span>
                      <span className="block text-xs text-ink-500">months</span>
                    </button>
                  );
                })}
              </div>
            </div>

            <dl className="mt-6 grid grid-cols-3 gap-4 rounded-lg bg-bone px-5 py-4">
              <Stat label="Monthly Payment" value={compactNaira(monthly)} />
              <Stat label="Interest Rate" value={`${bpsToPercent(rateBps)} p.a.`} />
              <Stat label="Total Repayment" value={compactNaira(total)} />
            </dl>
            <p className="sr-only">Total interest {formatNaira(totalInterest)}</p>
          </section>

          {/* Bank selection */}
          <section className="rounded-xl border border-ink-300/25 bg-white p-6">
            <h2 className="font-display text-lg text-ink-900">Select Your Bank</h2>
            {partners.length === 0 ? (
              <p className="mt-4 text-sm text-ink-500">No bank partners are available right now.</p>
            ) : (
              <ul className="mt-4 space-y-3">
                {partners.map((p) => {
                  const active = p.id === bankId;
                  return (
                    <li key={p.id}>
                      <button
                        type="button"
                        onClick={() => setBankId(p.id)}
                        className={`flex w-full items-center justify-between rounded-lg border px-5 py-4 text-left transition ${
                          active
                            ? 'border-emerald-deep bg-emerald-deep/5'
                            : 'border-ink-300/40 hover:border-ink-500'
                        }`}
                      >
                        <div>
                          <p className="font-medium text-ink-900">{p.name}</p>
                          <p className="mt-1 text-xs text-ink-500">
                            {bpsToPercent(p.interest_rate_bps)} interest · Up to{' '}
                            {p.max_tenure_months} months
                          </p>
                        </div>
                        <span
                          className={`flex h-5 w-5 items-center justify-center rounded-full border text-xs ${
                            active
                              ? 'border-emerald-deep bg-emerald-deep text-white'
                              : 'border-ink-300'
                          }`}
                          aria-hidden
                        >
                          {active ? '✓' : ''}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>

        {/* Right rail */}
        <div className="space-y-6">
          <section className="rounded-xl bg-emerald-deep p-6 text-bone">
            <h2 className="font-display text-lg">Loan Summary</h2>
            <dl className="mt-4 space-y-3 text-sm">
              <SummaryRow label="Property Price" value={compactNaira(price)} />
              <SummaryRow label="Loan Amount" value={compactNaira(amount)} />
              <SummaryRow label="Your Contribution" value={compactNaira(contribution)} />
              <SummaryRow label="Monthly Payment" value={compactNaira(monthly)} />
            </dl>
            <button
              type="button"
              onClick={start}
              disabled={!eligible}
              className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg bg-bone px-4 py-3 text-sm font-semibold text-emerald-deep transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              Start Loan Application →
            </button>
          </section>

          <InfoPanel
            title="Secure & Protected"
            items={[
              'Bank-reviewed application process',
              'Secure and encrypted data transmission',
              'Funds protected via escrow',
              'Transparent terms, no hidden fees',
            ]}
          />

          <section className="rounded-xl border border-ink-300/25 bg-white p-6">
            <h3 className="font-medium text-ink-900">What Happens Next?</h3>
            <ol className="mt-4 space-y-4">
              {[
                ['Submit Application', 'Complete the loan form'],
                ['Bank Review', '3-5 days'],
                ['Get Decision', 'Approval notification'],
                ['Disbursement', 'Funds released to escrow'],
              ].map(([t, d], i) => (
                <li key={t} className="flex gap-3">
                  <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-emerald-deep text-xs font-semibold text-bone">
                    {i + 1}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-ink-900">{t}</p>
                    <p className="text-xs text-ink-500">{d}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </main>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-500">{label}</dt>
      <dd className="mt-1 font-medium text-ink-900">{value}</dd>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-bone/15 pb-3 last:border-0 last:pb-0">
      <dt className="text-bone/70">{label}</dt>
      <dd className="font-semibold">{value}</dd>
    </div>
  );
}

function InfoPanel({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="rounded-xl border border-ink-300/25 bg-white p-6">
      <h3 className="flex items-center gap-2 font-medium text-ink-900">
        <ShieldIcon /> {title}
      </h3>
      <ul className="mt-4 space-y-2 text-sm text-ink-500">
        {items.map((i) => (
          <li key={i} className="flex gap-2">
            <span className="text-emerald-deep" aria-hidden>
              ✓
            </span>
            {i}
          </li>
        ))}
      </ul>
    </section>
  );
}

function WalletIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <path d="M16 12h.01M2 10h20" />
    </svg>
  );
}

function HomeIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M3 9.5 12 3l9 6.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z" />
    </svg>
  );
}
