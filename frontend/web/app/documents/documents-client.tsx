'use client';

import Link from 'next/link';
import { useRef, useState } from 'react';

import {
  CATEGORY_LABELS,
  DOCUMENT_CATEGORIES,
  STATUS_LABELS,
  formatDate,
  formatKind,
  formatSize,
  type DocumentCategory,
  type UserDocument,
  type UserDocuments,
} from '@/lib/user-documents';

/**
 * My Documents — SCRUM-188.
 *
 * Measured 1:1 on `design/buyer-profile-page/Mobile App Onboarding Flow (4).png`
 * (1562 artboard):
 *   container   173..1389 = 1216, the same width Settings and the landing use
 *   stat cards  4 x 286 at a 24px gutter (286*4 + 24*3 = 1216)
 *   columns     280 (left) + 904 (right) at a 32px gutter
 *   nav item    246 wide, matching Settings
 *   doc row     838 wide inside the 904 card = 32px padding each side
 *   file tile   48px, filled `surface-warm` #f5f1e8
 *
 * Status pill colours are measured: verified #dcfce7 on #00a63e, pending
 * #fef3c6 on #bb4d00. ⚠️ The REJECTED tint is inferred, not measured — the
 * export's "Rejected" count is 0, so no rejected pill is drawn anywhere in it.
 */

const STATUS_STYLES: Record<string, string> = {
  verified: 'bg-[#dcfce7] text-status-success',
  pending: 'bg-[#fef3c6] text-[#bb4d00]',
  under_review: 'bg-[#fef3c6] text-[#bb4d00]',
  // Inferred from the pattern above; see the note in the component docblock.
  failed: 'bg-[#ffe2e2] text-status-danger',
};

function DocIcon({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5" aria-hidden>
      <rect x="3.5" y="5" width="17" height="16" rx="2" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
    </svg>
  );
}

function StatCard({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-2xl border border-line bg-white px-6 py-5">
      <p className="text-sm leading-5 text-ink-500">{label}</p>
      <p className={`mt-1 text-3xl font-bold leading-9 ${tone}`}>{value}</p>
    </div>
  );
}

export function DocumentsClient({
  initial,
  home,
}: {
  initial: UserDocuments;
  home: string;
}) {
  const [data, setData] = useState(initial);
  const [active, setActive] = useState<DocumentCategory | null>(null);
  const [pending, setPending] = useState<File | null>(null);
  const [pendingCategory, setPendingCategory] = useState<DocumentCategory>('identity');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function refresh(category: DocumentCategory | null) {
    const query = category ? `?category=${category}` : '';
    const resp = await fetch(`/api/documents/personal${query}`, { cache: 'no-store' });
    if (resp.ok) setData((await resp.json()) as UserDocuments);
  }

  async function select(category: DocumentCategory | null) {
    setActive(category);
    setError(null);
    await refresh(category);
  }

  async function upload() {
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('category', pendingCategory);
      form.append('file', pending);
      const resp = await fetch('/api/documents/personal', { method: 'POST', body: form });
      if (!resp.ok) {
        const b = (await resp.json().catch(() => ({}))) as { error_code?: string };
        setError(
          b.error_code === 'DOCUMENT_TOO_LARGE'
            ? 'That file is too large. Please choose one under 10MB.'
            : b.error_code === 'DOCUMENT_FORMAT_INVALID'
              ? 'Please choose a PDF, JPG or PNG file.'
              : 'We could not upload that document. Please retry.',
        );
        return;
      }
      setPending(null);
      await refresh(active);
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  async function remove(document: UserDocument) {
    setError(null);
    const resp = await fetch(`/api/documents/personal/${document.id}`, { method: 'DELETE' });
    if (!resp.ok) {
      setError('We could not remove that document. Please retry.');
      return;
    }
    await refresh(active);
  }

  async function view(document: UserDocument) {
    setError(null);
    const resp = await fetch(`/api/documents/personal/${document.id}/view`);
    if (!resp.ok) {
      setError('We could not open that document. Please retry.');
      return;
    }
    const { url } = (await resp.json()) as { url: string };
    // Opened directly rather than navigated to: the URL is pre-signed and
    // short-lived, so it should not enter this page's history.
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  return (
    <main className="min-h-screen bg-[#fbfbfb]">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex h-[102px] w-full max-w-[1280px] items-center gap-5 px-8">
          <Link
            href={home}
            aria-label="Back"
            className="rounded-lg p-1 text-ink-buyer transition hover:bg-surface-page focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5" aria-hidden>
              <path d="M19 12H5" />
              <path d="m11 6-6 6 6 6" />
            </svg>
          </Link>
          {/* A page glyph, not the brand mark — the design draws a document
              here, where Settings draws the logo. */}
          <span
            aria-hidden
            className="flex h-9 w-9 flex-none items-center justify-center rounded-lg bg-emerald-deep text-white"
          >
            <DocIcon className="h-[18px] w-[18px]" />
          </span>
          <div>
            <h1 className="text-2xl font-bold leading-8 text-ink-buyer">My Documents</h1>
            <p className="text-sm leading-5 text-ink-500">Manage your uploaded documents</p>
          </div>
        </div>
      </header>

      <div className="mx-auto w-full max-w-[1280px] px-8 py-9">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Total Documents" value={data.total} tone="text-ink-buyer" />
          <StatCard
            label="Verified"
            value={data.status_counts.verified ?? 0}
            tone="text-status-success"
          />
          <StatCard
            label="Pending Review"
            value={(data.status_counts.pending ?? 0) + (data.status_counts.under_review ?? 0)}
            tone="text-[#e17100]"
          />
          <StatCard
            label="Rejected"
            value={data.status_counts.failed ?? 0}
            tone="text-status-danger"
          />
        </div>

        <div className="mt-8 grid gap-8 lg:grid-cols-[280px_minmax(0,1fr)]">
          <div className="flex flex-col gap-6">
            <div className="rounded-2xl border border-line bg-white p-4">
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                disabled={busy}
                className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-emerald-deep px-5 text-sm font-semibold text-white transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-line disabled:text-ink-400"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden>
                  <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2" />
                </svg>
                Upload Document
              </button>
              <input
                ref={inputRef}
                type="file"
                accept="application/pdf,image/jpeg,image/png"
                className="sr-only"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    setPending(file);
                    setPendingCategory(active ?? 'identity');
                    setError(null);
                  }
                  // Clear so re-picking the same file fires change again.
                  e.target.value = '';
                }}
              />

              {/*
                The category chooser only appears once a file is picked. The
                design draws a single button, so asking for a category up front
                would add a control it does not have — but the server requires
                one, and silently filing everything under "Other" would be
                worse than one extra step.
              */}
              {pending && (
                <div className="mt-4 rounded-xl bg-surface-page p-4">
                  <p className="truncate text-sm font-semibold text-ink-buyer" title={pending.name}>
                    {pending.name}
                  </p>
                  <label
                    htmlFor="upload-category"
                    className="mt-3 block text-xs font-bold uppercase tracking-wide text-ink-500"
                  >
                    Category
                  </label>
                  <select
                    id="upload-category"
                    value={pendingCategory}
                    onChange={(e) => setPendingCategory(e.target.value as DocumentCategory)}
                    className="mt-1.5 block h-10 w-full rounded-lg border border-line-strong bg-white px-3 text-sm text-ink-buyer outline-none focus:border-emerald-deep"
                  >
                    {DOCUMENT_CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {CATEGORY_LABELS[c]}
                      </option>
                    ))}
                  </select>
                  <div className="mt-4 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void upload()}
                      disabled={busy}
                      className="h-9 flex-1 rounded-lg bg-emerald-deep text-sm font-semibold text-white transition hover:brightness-110 disabled:bg-line disabled:text-ink-400"
                    >
                      {busy ? 'Uploading…' : 'Upload'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setPending(null)}
                      className="h-9 rounded-lg border border-line-strong px-3 text-sm font-semibold text-ink-700"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>

            <nav
              aria-label="Document categories"
              className="h-fit rounded-2xl border border-line bg-white p-4"
            >
              <p className="px-4 pb-2 text-sm text-ink-500">Categories</p>
              <ul className="flex flex-col gap-1.5">
                <li>
                  <CategoryButton
                    label="All Documents"
                    count={data.total}
                    active={active === null}
                    onClick={() => void select(null)}
                  />
                </li>
                {DOCUMENT_CATEGORIES.map((c) => (
                  <li key={c}>
                    <CategoryButton
                      label={CATEGORY_LABELS[c]}
                      count={data.category_counts[c] ?? 0}
                      active={active === c}
                      onClick={() => void select(c)}
                    />
                  </li>
                ))}
              </ul>
            </nav>
          </div>

          <div className="flex flex-col gap-8">
            <section className="rounded-2xl border border-line bg-white p-8">
              <h2 className="text-xl font-bold leading-7 text-ink-buyer">
                {active === null ? 'All Documents' : CATEGORY_LABELS[active]}
              </h2>

              {error && (
                <p role="alert" className="mt-4 text-sm leading-5 text-status-danger">
                  {error}
                </p>
              )}

              {data.items.length === 0 ? (
                <p className="mt-7 text-sm leading-5 text-ink-500">
                  {active === null
                    ? 'You have not uploaded any documents yet.'
                    : `Nothing filed under ${CATEGORY_LABELS[active]} yet.`}
                </p>
              ) : (
                <ul className="mt-7 flex flex-col gap-4">
                  {data.items.map((d) => (
                    <li
                      key={d.id}
                      className="flex items-center gap-4 rounded-xl border border-line px-5 py-4"
                    >
                      <span
                        aria-hidden
                        className="flex h-12 w-12 flex-none items-center justify-center rounded-xl bg-surface-warm text-ink-700"
                      >
                        <DocIcon />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-base font-bold leading-6 text-ink-buyer">
                          {d.file_name}
                        </p>
                        {/* The design prefixes the kind and the date with
                            small glyphs; the size sits between them plain. */}
                        <p className="mt-1 flex flex-wrap items-center gap-x-4 text-sm leading-5 text-ink-500">
                          <span className="flex items-center gap-1.5">
                            <DocIcon className="h-3.5 w-3.5" />
                            {formatKind(d.content_type)}
                          </span>
                          <span>{formatSize(d.size_bytes)}</span>
                          <span className="flex items-center gap-1.5">
                            <CalendarIcon />
                            {formatDate(d.created_at)}
                          </span>
                        </p>
                      </div>
                      <span
                        className={`flex-none rounded-full px-3 py-1.5 text-sm font-semibold ${
                          STATUS_STYLES[d.verification_status] ?? 'bg-surface-muted text-ink-700'
                        }`}
                      >
                        {STATUS_LABELS[d.verification_status] ?? d.verification_status}
                      </span>
                      <div className="flex flex-none items-center gap-1">
                        <IconButton label={`View ${d.file_name}`} onClick={() => void view(d)}>
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                            <path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6-10-6-10-6Z" />
                            <circle cx="12" cy="12" r="2.6" />
                          </svg>
                        </IconButton>
                        <IconButton
                          label={`Remove ${d.file_name}`}
                          danger
                          onClick={() => void remove(d)}
                        >
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                            <path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" />
                          </svg>
                        </IconButton>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/*
              Measured: 1px #bedbff border over a vertical gradient
              #edf5ff -> #e1edfe, shield #155dfc, body copy #6b7280.
            */}
            <section className="rounded-2xl border border-[#bedbff] bg-gradient-to-b from-[#edf5ff] to-[#e1edfe] p-8">
              <div className="flex items-center gap-3">
                <svg viewBox="0 0 24 24" fill="none" stroke="#155dfc" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5 flex-none" aria-hidden>
                  <path d="M12 21s7-3.2 7-9V6l-7-3-7 3v6c0 5.8 7 9 7 9Z" />
                </svg>
                <h2 className="text-lg font-bold leading-6 text-ink-buyer">Document Security</h2>
              </div>
              <p className="mt-3 text-sm leading-6 text-[#6b7280]">
                All uploaded documents are encrypted and stored securely. Only authorized personnel
                can access your documents for verification purposes.
              </p>
              <ul className="mt-4 flex flex-col gap-1.5 text-sm leading-6 text-[#6b7280]">
                <li>• Documents are reviewed within 24-48 hours</li>
                <li>• Accepted formats: PDF, JPG, PNG (max 10MB)</li>
                <li>• You&apos;ll be notified once verification is complete</li>
              </ul>
            </section>
          </div>
        </div>
      </div>
    </main>
  );
}

function CategoryButton({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? 'true' : undefined}
      className={`flex h-12 w-full items-center justify-between rounded-xl px-4 text-left text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep ${
        active ? 'bg-emerald-deep text-white' : 'text-ink-700 hover:bg-surface-page'
      }`}
    >
      {label}
      <span
        className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
          active ? 'bg-white/20 text-white' : 'bg-surface-muted text-ink-500'
        }`}
      >
        {count}
      </span>
    </button>
  );
}

function IconButton({
  label,
  children,
  onClick,
  danger,
}: {
  label: string;
  children: React.ReactNode;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className={`flex h-9 w-9 items-center justify-center rounded-lg transition focus-visible:outline-none focus-visible:ring-2 ${
        danger
          ? 'text-ink-500 hover:bg-[#ffe2e2] hover:text-status-danger focus-visible:ring-status-danger'
          : 'text-ink-500 hover:bg-surface-page hover:text-ink-buyer focus-visible:ring-emerald-deep'
      }`}
    >
      {children}
    </button>
  );
}
