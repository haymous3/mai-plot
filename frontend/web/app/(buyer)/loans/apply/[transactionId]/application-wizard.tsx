'use client';

import { useRouter } from 'next/navigation';
import { useRef, useState } from 'react';

import type { BankPartner, FinancingSummary } from '@/lib/api';
import { formatNaira } from '@/lib/format';
import { monthlyPaymentKobo } from '@/lib/loan-math';

const EMPLOYMENT_OPTIONS = [
  { value: 'employed', label: 'Employed' },
  { value: 'self_employed', label: 'Self-employed' },
  { value: 'business_owner', label: 'Business owner' },
  { value: 'unemployed', label: 'Unemployed' },
];

const APPLY_ERRORS: Record<string, string> = {
  LOAN_CAP_EXCEEDED: 'The loan cannot exceed 50% of the property price.',
  BANK_PARTNER_UNAVAILABLE: 'That bank is not available right now. Please pick another.',
  LOAN_BAND_VIOLATION: "The amount is outside the bank's loan range.",
  TENURE_VIOLATION: "The repayment period is outside the bank's allowed range.",
  DAILY_LIMIT_REACHED: "You've reached today's application limit. Please try again tomorrow.",
  NOT_TRANSACTION_BUYER: 'Only the buyer on this deal can apply.',
  TRANSACTION_NOT_FOUND: 'We could not find this deal.',
};

type DocKey = 'bankStatement' | 'employment' | 'passport';

export function ApplicationWizard({
  transactionId,
  summary,
  bank,
  amountKobo,
  tenureMonths,
}: {
  transactionId: string;
  summary: FinancingSummary;
  bank: BankPartner;
  amountKobo: number;
  tenureMonths: number;
}) {
  const router = useRouter();
  const idempotencyKey = useRef(crypto.randomUUID());

  const [step, setStep] = useState(1);

  // Step 1 — BVN is verified against auth-service; employment + income are sent
  // with the application and persisted on the loan (SCRUM-131).
  const [bvn, setBvn] = useState('');
  const [employment, setEmployment] = useState('');
  const [income, setIncome] = useState('');
  const [step1Errors, setStep1Errors] = useState<Record<string, string>>({});
  const [verifying, setVerifying] = useState(false);

  // Step 2 — files are selected client-side and uploaded after the loan is
  // created (SCRUM-131), since the upload endpoint is loan-scoped.
  const [files, setFiles] = useState<Record<DocKey, File | null>>({
    bankStatement: null,
    employment: null,
    passport: null,
  });
  const [docsTouched, setDocsTouched] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const monthly = monthlyPaymentKobo(amountKobo, bank.interest_rate_bps, tenureMonths);

  async function submitStep1() {
    const errs: Record<string, string> = {};
    if (!/^\d{11}$/.test(bvn)) errs.bvn = 'BVN must be 11 digits';
    if (!employment) errs.employment = 'Please select employment status';
    if (!income || Number(income) <= 0) errs.income = 'Please enter a valid monthly income';
    setStep1Errors(errs);
    if (Object.keys(errs).length > 0) return;

    setVerifying(true);
    try {
      const resp = await fetch('/api/buyer/bvn-verify', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ bvn }),
      });
      // 202 accepted (initiated) or 409 already verified both let us proceed.
      if (resp.status === 202 || resp.ok || resp.status === 409) {
        setStep(2);
        return;
      }
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code === 'BVN_FORMAT_INVALID') {
        setStep1Errors({ bvn: 'BVN must be 11 digits' });
      } else {
        setStep1Errors({ bvn: 'Could not verify your BVN. Please try again.' });
      }
    } catch {
      setStep1Errors({ bvn: 'Could not reach the server. Please try again.' });
    } finally {
      setVerifying(false);
    }
  }

  function submitStep2() {
    setDocsTouched(true);
    if (files.bankStatement && files.employment && files.passport) setStep(3);
  }

  async function uploadDocuments(loanId: string): Promise<boolean> {
    const slots: [DocKey, string][] = [
      ['bankStatement', 'bank_statement'],
      ['employment', 'employment_letter'],
      ['passport', 'passport'],
    ];
    for (const [key, documentType] of slots) {
      const file = files[key];
      if (!file) continue; // step 2 requires all three, so this is defensive
      const fd = new FormData();
      fd.append('document_type', documentType);
      fd.append('file', file);
      try {
        const r = await fetch(`/api/buyer/loans/${loanId}/documents`, {
          method: 'POST',
          body: fd,
        });
        if (!r.ok) return false;
      } catch {
        return false;
      }
    }
    return true;
  }

  async function submit() {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const resp = await fetch('/api/buyer/loans/apply', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          transaction_id: transactionId,
          bank_partner_id: bank.id,
          requested_amount_kobo: amountKobo,
          tenure_months: tenureMonths,
          idempotency_key: idempotencyKey.current,
          // Applicant details from step 1 (SCRUM-131) — now persisted.
          employment_status: employment || null,
          monthly_income_kobo: income ? Number(income) * 100 : null,
        }),
      });
      const body = (await resp.json()) as { loan_id?: string; error_code?: string };
      if (resp.ok && body.loan_id) {
        // Upload the step-2 documents now that the loan exists (SCRUM-131).
        // /loans/apply is idempotent, so a retry after a failed upload re-uses
        // the same loan and re-attempts the uploads.
        const uploaded = await uploadDocuments(body.loan_id);
        if (!uploaded) {
          setSubmitError(
            'Your application was created, but a document failed to upload. Please submit again to retry.',
          );
          return;
        }
        router.push(`/loans/${body.loan_id}`);
        return;
      }
      setSubmitError(APPLY_ERRORS[body.error_code ?? ''] ?? 'Could not submit your application.');
    } catch {
      setSubmitError('Could not reach the server. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <header className="flex items-center justify-between border-b border-line bg-surface-card px-11 py-4">
        <button
          type="button"
          onClick={() => (step > 1 ? setStep(step - 1) : router.push(`/financing/${transactionId}`))}
          className="text-sm text-ink-500 transition hover:text-ink-900"
        >
          ← Back
        </button>
        <h1 className="font-display text-lg text-ink-900">Loan Application</h1>
        <span className="w-12" />
      </header>

      <main className="mx-auto grid max-w-6xl gap-6 px-11 py-8 lg:grid-cols-[1.7fr_1fr]">
        <div className="space-y-6">
          <StepIndicator step={step} />

          {step === 1 && (
            <StepCard title="Personal Information">
              <Field label="Bank Verification Number (BVN)" error={step1Errors.bvn} hint="Your BVN is used for identity verification">
                <input
                  inputMode="numeric"
                  maxLength={11}
                  value={bvn}
                  onChange={(e) => setBvn(e.target.value.replace(/\D/g, ''))}
                  placeholder="Enter your 11-digit BVN"
                  className={inputClass(!!step1Errors.bvn)}
                />
              </Field>
              <Field label="Employment Status" error={step1Errors.employment}>
                <select
                  value={employment}
                  onChange={(e) => setEmployment(e.target.value)}
                  className={inputClass(!!step1Errors.employment)}
                >
                  <option value="">Select employment status</option>
                  {EMPLOYMENT_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Monthly Income (₦)" error={step1Errors.income} hint="Used to assess loan eligibility">
                <input
                  inputMode="numeric"
                  value={income}
                  onChange={(e) => setIncome(e.target.value.replace(/\D/g, ''))}
                  placeholder="Enter your monthly income"
                  className={inputClass(!!step1Errors.income)}
                />
              </Field>
              <div className="flex justify-end pt-2">
                <PrimaryButton onClick={submitStep1} disabled={verifying}>
                  {verifying ? 'Verifying…' : 'Next →'}
                </PrimaryButton>
              </div>
            </StepCard>
          )}

          {step === 2 && (
            <StepCard title="Upload Documents" subtitle="Please upload the following documents to verify your application">
              <UploadSlot
                label="Bank Statement (Last 6 months)"
                hint="PDF, JPG, PNG (Max 10MB)"
                file={files.bankStatement}
                error={docsTouched && !files.bankStatement ? 'Bank statement is required' : undefined}
                onSelect={(f) => setFiles((s) => ({ ...s, bankStatement: f }))}
              />
              <UploadSlot
                label="Employment Letter / CAC Document"
                hint="PDF, JPG, PNG (Max 10MB)"
                file={files.employment}
                error={docsTouched && !files.employment ? 'Employment proof is required' : undefined}
                onSelect={(f) => setFiles((s) => ({ ...s, employment: f }))}
              />
              <UploadSlot
                label="Passport Photograph"
                hint="JPG, PNG (Max 10MB)"
                file={files.passport}
                error={docsTouched && !files.passport ? 'Passport photo is required' : undefined}
                onSelect={(f) => setFiles((s) => ({ ...s, passport: f }))}
              />
              <div className="flex items-center justify-between border-t border-line pt-5">
                <button type="button" onClick={() => setStep(1)} className="text-sm font-medium text-ink-700">
                  ← Back
                </button>
                <PrimaryButton onClick={submitStep2}>Next →</PrimaryButton>
              </div>
            </StepCard>
          )}

          {step === 3 && (
            <StepCard title="Review Your Application" subtitle="Please review all information before submitting">
              <ReviewBlock title="Personal Information">
                <ReviewGrid
                  rows={[
                    ['BVN', bvn],
                    ['Employment Status', EMPLOYMENT_OPTIONS.find((o) => o.value === employment)?.label ?? '—'],
                    ['Monthly Income', formatNaira(Number(income) * 100)],
                  ]}
                />
              </ReviewBlock>
              <ReviewBlock title="Uploaded Documents">
                <ul className="space-y-2 text-sm text-ink-700">
                  {[files.bankStatement, files.employment, files.passport].map((f, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span className="text-emerald-deep" aria-hidden>✓</span>
                      {f?.name ?? '—'}
                    </li>
                  ))}
                </ul>
              </ReviewBlock>
              <ReviewBlock title="Loan Details">
                <ReviewGrid
                  rows={[
                    ['Loan Amount', formatNaira(amountKobo)],
                    ['Tenure', `${tenureMonths} months`],
                    ['Monthly Payment', formatNaira(monthly)],
                    ['Bank', bank.name],
                  ]}
                />
              </ReviewBlock>
              <ReviewBlock title="Property">
                <p className="text-sm font-medium text-ink-900">{summary.property.title}</p>
                <p className="text-xs text-ink-500">
                  {summary.property.lga}, {summary.property.state}
                </p>
                <p className="mt-1 text-sm text-ink-700">{formatNaira(summary.agreed_price_kobo)}</p>
              </ReviewBlock>

              {submitError && (
                <p role="alert" className="rounded-md bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
                  {submitError}
                </p>
              )}

              <div className="flex items-center justify-between border-t border-line pt-5">
                <button type="button" onClick={() => setStep(2)} className="text-sm font-medium text-ink-700">
                  ← Back
                </button>
                <PrimaryButton onClick={submit} disabled={submitting}>
                  {submitting ? 'Submitting…' : '✓ Submit Application'}
                </PrimaryButton>
              </div>
            </StepCard>
          )}
        </div>

        <div className="space-y-6">
          <section className="rounded-xl bg-emerald-deep p-6 text-bone">
            <h3 className="flex items-center gap-2 font-medium">
              <span aria-hidden>🛡</span> Your Data is Secure
            </h3>
            <ul className="mt-4 space-y-2 text-sm text-bone/80">
              {[
                '256-bit SSL encryption',
                'Bank-level security standards',
                'Data Protection Act compliant',
                'Never shared with third parties',
              ].map((i) => (
                <li key={i} className="flex gap-2">
                  <span aria-hidden>✓</span>
                  {i}
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-card border border-line/50 bg-surface-card p-8">
            <h3 className="font-medium text-ink-900">What Happens Next?</h3>
            <ol className="mt-4 space-y-4">
              {[
                ['Application Review', "We'll verify your documents"],
                ['Bank Processing', '3-5 days'],
                ['Loan Decision', "You'll receive approval notification"],
                ['Fund Disbursement', 'Funds transferred to seller'],
              ].map(([t, d], i) => (
                <li key={t} className="flex gap-3">
                  <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-bone text-xs font-semibold text-ink-700">
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

function inputClass(hasError: boolean): string {
  return `w-full rounded-md border bg-white px-3.5 py-2.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:ring-2 focus:ring-emerald-accent/20 ${
    hasError ? 'border-red-400 focus:border-red-400' : 'border-ink-300/60 focus:border-emerald-accent'
  }`;
}

function StepIndicator({ step }: { step: number }) {
  const steps = ['Personal Info', 'Documents', 'Review'];
  return (
    <div className="rounded-card border border-line/50 bg-surface-card p-8">
      <ol className="flex items-center">
        {steps.map((label, i) => {
          const n = i + 1;
          const done = step > n;
          const active = step === n;
          return (
            <li key={label} className="flex flex-1 items-center last:flex-none">
              <div className="flex flex-col items-center">
                <span
                  className={`flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold ${
                    done || active ? 'bg-emerald-deep text-bone' : 'border border-ink-300 text-ink-300'
                  }`}
                >
                  {done ? '✓' : n}
                </span>
                <span className={`mt-1 text-xs ${active ? 'text-ink-900' : 'text-ink-500'}`}>
                  Step {n}
                </span>
                <span className="text-xs text-ink-500">{label}</span>
              </div>
              {n < steps.length && (
                <span className={`mx-3 h-px flex-1 ${step > n ? 'bg-emerald-deep' : 'bg-ink-300/40'}`} />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function StepCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-card border border-line/50 bg-surface-card p-8">
      <h2 className="font-display text-lg text-ink-900">{title}</h2>
      {subtitle && <p className="mt-1 text-sm text-ink-500">{subtitle}</p>}
      <div className="mt-5 space-y-5">{children}</div>
    </section>
  );
}

function Field({
  label,
  error,
  hint,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-ink-700">{label}</label>
      {children}
      {error ? (
        <p className="text-xs text-red-600">{error}</p>
      ) : hint ? (
        <p className="text-xs text-ink-500">{hint}</p>
      ) : null}
    </div>
  );
}

function UploadSlot({
  label,
  hint,
  file,
  error,
  onSelect,
}: {
  label: string;
  hint: string;
  file: File | null;
  error?: string;
  onSelect: (f: File | null) => void;
}) {
  const inputId = `file-${label.replace(/\W+/g, '-').toLowerCase()}`;
  return (
    <div>
      <p className="text-sm font-medium text-ink-700">{label}</p>
      <label
        htmlFor={inputId}
        className={`mt-2 flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-8 text-center transition ${
          error ? 'border-red-300' : 'border-ink-300/40 hover:border-emerald-accent/60'
        }`}
      >
        <span className="text-ink-300" aria-hidden>↑</span>
        <span className="mt-2 text-sm text-ink-700">
          {file ? file.name : 'Drag and drop or click to upload'}
        </span>
        <span className="mt-1 text-xs text-ink-500">{hint}</span>
        <span className="mt-3 rounded-md bg-emerald-deep px-4 py-1.5 text-xs font-medium text-bone">
          {file ? 'Replace File' : 'Choose File'}
        </span>
        <input
          id={inputId}
          type="file"
          className="sr-only"
          onChange={(e) => onSelect(e.target.files?.[0] ?? null)}
        />
      </label>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}

function ReviewBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-bone px-5 py-4">
      <h3 className="font-medium text-ink-900">{title}</h3>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function ReviewGrid({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt className="text-xs text-ink-500">{label}</dt>
          <dd className="mt-0.5 font-medium text-ink-900">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function PrimaryButton({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-lg bg-emerald-deep px-5 py-2.5 text-sm font-medium text-bone transition hover:bg-emerald-accent disabled:cursor-not-allowed disabled:opacity-60"
    >
      {children}
    </button>
  );
}
