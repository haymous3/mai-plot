import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { DocumentsList } from './documents-list';
import type { SellerDocumentsResponse } from '@/lib/api';
import { documentServiceUrl } from '@/lib/api';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Documents · Maiplot Seller' };

const REQUIREMENTS = [
  'Certificate of Occupancy (C of O) — Required',
  'Survey Plan — Required',
  'Deed of Assignment — Required',
  'Power of Attorney — If applicable',
];

export default async function SellerDocumentsPage() {
  const result = await sessionBackendGet<SellerDocumentsResponse>(
    `${documentServiceUrl()}/documents/mine`,
  );
  if (!result.ok && result.status === 401) redirect(`${SESSION_LOGIN}?role=seller`);
  const docs = result.ok ? result.data.data : [];

  const count = (fn: (s: string) => boolean) => docs.filter((d) => fn(d.verification_status)).length;

  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <div>
        <h1 className="font-display text-3xl text-emerald-deep">Documents</h1>
        <p className="mt-1 text-sm text-ink-500">Manage your property documents</p>
      </div>

      <div className="mt-2 grid gap-6 lg:grid-cols-[1fr_300px]">
        <div>
          {!result.ok ? (
            <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              Could not load your documents. Please retry.
            </div>
          ) : (
            <DocumentsList documents={docs} />
          )}
        </div>

        <aside className="space-y-4 lg:mt-6">
          <h2 className="font-display text-lg text-ink-900">Document Summary</h2>
          <Tile n={count((s) => s === 'verified')} label="Verified Documents" cls="bg-emerald-deep/5 text-emerald-deep" />
          <Tile n={count((s) => s === 'pending' || s === 'under_review')} label="Pending Review" cls="bg-amber-50 text-amber-700" />
          <Tile n={count((s) => s === 'failed')} label="Rejected" cls="bg-red-50 text-red-700" />
          <div className="rounded-2xl bg-bone/70 p-5">
            <p className="text-sm font-medium text-ink-800">Document Requirements</p>
            <p className="mt-1 text-xs text-ink-600">
              All documents must be clear, legible scans in PDF, JPG, or PNG format.
            </p>
            <ul className="mt-2 space-y-1 text-xs text-ink-600">
              {REQUIREMENTS.map((r) => (
                <li key={r} className="flex gap-2">
                  <span className="text-emerald-accent">•</span> {r}
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-2xl border border-emerald-deep/15 bg-emerald-deep/5 p-4">
            <p className="text-sm font-medium text-emerald-deep">Verification Benefit</p>
            <p className="mt-1 text-xs text-ink-700">
              Verified listings with complete documentation perform 3× better and earn more buyer trust.
            </p>
          </div>
        </aside>
      </div>
    </main>
  );
}

function Tile({ n, label, cls }: { n: number; label: string; cls: string }) {
  return (
    <div className={`rounded-2xl px-4 py-4 ${cls}`}>
      <p className="text-2xl font-semibold">{n}</p>
      <p className="text-sm">{label}</p>
    </div>
  );
}
