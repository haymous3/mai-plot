import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound, redirect } from 'next/navigation';

import type { FinancingSummary } from '@/lib/api';
import { transactionServiceUrl } from '@/lib/api';
import { BUYER_LOGIN } from '@/lib/buyer-auth';
import { buyerBackendGet } from '@/lib/buyer-server-api';
import {
  DEAL_MILESTONES,
  DEAL_TOTAL_STEPS,
  dealCompletedSteps,
  isDealActive,
} from '@/lib/deal-stage';
import { formatNaira } from '@/lib/format';

export const metadata: Metadata = { title: 'Deal Progress · Maiplot' };

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-card bg-surface-card p-8 shadow-card ${className}`}>
      {children}
    </section>
  );
}

export default async function DealProgressPage({ params }: { params: { id: string } }) {
  const res = await buyerBackendGet<FinancingSummary>(
    `${transactionServiceUrl()}/transactions/${params.id}/financing-summary`,
  );
  if (!res.ok) {
    if (res.status === 401) redirect(BUYER_LOGIN);
    if (res.status === 404) notFound();
    throw new Error(`Failed to load deal (${res.code})`);
  }
  const s = res.data;
  const completed = dealCompletedSteps(s.stage);
  const active = isDealActive(s.stage);
  const escrowSecured = ['payment_held', 'title_held', 'completed'].includes(s.stage);

  return (
    <main className="mx-auto max-w-5xl px-11 py-6">
      <Link href="/dashboard" className="text-sm text-ink-500 transition hover:text-ink-900">
        ← Back
      </Link>
      <h1 className="mt-3 font-display text-3xl text-emerald-deep">Deal Progress</h1>
      <p className="text-sm text-ink-500">Deal ID: {params.id.slice(0, 8)}</p>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          <Card>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="font-display text-2xl text-ink-900">{s.property.title}</h2>
                <p className="mt-1 text-sm text-ink-500">
                  📍 {s.property.lga}, {s.property.state}
                </p>
              </div>
              <span
                className={`flex-none rounded-full px-3 py-1 text-xs font-medium ${
                  active ? 'bg-amber-100 text-amber-700' : 'bg-ink-300/20 text-ink-500'
                }`}
              >
                {active ? 'Active Deal' : 'Closed'}
              </span>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4 border-t border-line pt-4">
              <div>
                <p className="text-xs text-ink-500">Your Bid</p>
                <p className="mt-0.5 font-display text-xl text-emerald-deep">
                  {formatNaira(s.agreed_price_kobo)}
                </p>
              </div>
              <div>
                <p className="text-xs text-ink-500">Asking Price</p>
                <p className="mt-0.5 font-display text-xl text-ink-900">
                  {formatNaira(s.property.asking_price_kobo)}
                </p>
              </div>
            </div>
          </Card>

          <Card>
            <div className="flex items-center justify-between">
              <h2 className="font-display text-xl text-ink-900">Overall Progress</h2>
              <span className="text-sm text-ink-500">
                {completed} of {DEAL_TOTAL_STEPS} complete
              </span>
            </div>
            <div className="mt-3 h-2 rounded-full bg-ink-300/25">
              <div
                className="h-2 rounded-full bg-emerald-deep"
                style={{ width: `${(completed / DEAL_TOTAL_STEPS) * 100}%` }}
              />
            </div>
          </Card>

          <Card>
            <h2 className="font-display text-xl text-ink-900">Milestones</h2>
            <ol className="mt-4 space-y-4">
              {DEAL_MILESTONES.map((m, i) => {
                const done = i < completed;
                const current = i === completed && active;
                return (
                  <li key={m.title} className="flex gap-3">
                    <span
                      className={`flex h-7 w-7 flex-none items-center justify-center rounded-full text-sm ${
                        done
                          ? 'bg-emerald-deep text-bone'
                          : current
                            ? 'bg-amber-400 text-white'
                            : 'border border-ink-300/50 text-ink-300'
                      }`}
                    >
                      {done ? '✓' : current ? '◷' : '○'}
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className={`font-medium ${done || current ? 'text-ink-900' : 'text-ink-400'}`}>
                          {m.title}
                        </p>
                        {current && <span className="text-xs text-amber-600">In progress</span>}
                      </div>
                      <p className="mt-0.5 text-sm text-ink-500">{m.desc}</p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </Card>
        </div>

        <aside className="space-y-4">
          {active && s.existing_loan === null && (
            <div className="rounded-2xl bg-emerald-deep p-5 text-bone">
              <p className="font-semibold">Need financing?</p>
              <p className="mt-1 text-sm text-bone/80">
                Cover up to {formatNaira(s.max_loan_kobo)} (50%) with a Maiplot loan.
              </p>
              <Link
                href={`/loans/apply/${s.transaction_id}`}
                className="mt-4 block rounded-lg bg-white px-4 py-2.5 text-center text-sm font-semibold text-emerald-deep transition hover:bg-bone"
              >
                Apply for loan
              </Link>
            </div>
          )}

          <Card className="!p-5">
            <h3 className="font-display text-lg text-ink-900">Deal Summary</h3>
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-ink-500">Stage</dt>
                <dd className="font-medium capitalize text-ink-900">
                  {s.stage.replace(/_/g, ' ')}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-500">Agreed price</dt>
                <dd className="font-medium text-ink-900">{formatNaira(s.agreed_price_kobo)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-500">Escrow</dt>
                <dd className={`font-medium ${escrowSecured ? 'text-emerald-deep' : 'text-ink-500'}`}>
                  {escrowSecured ? 'Secured' : 'Pending'}
                </dd>
              </div>
            </dl>
          </Card>
        </aside>
      </div>
    </main>
  );
}
