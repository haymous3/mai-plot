'use client';

import {
  CameraIcon,
  CheckIcon,
  FileTextIcon,
  HouseIcon,
  ShieldCheckIcon,
  XIcon,
} from '../../../_icons';
import { reportSummary, STEPS, type ReportForm, type SummaryRow } from '@/lib/inspection-report';

/** Shared presentational pieces of the report wizard (SCRUM-204, Figma
 * 278:3729). Kept beside the wizard rather than in components/ because nothing
 * else in the app draws these. */

const STEP_ICONS = [HouseIcon, ShieldCheckIcon, FileTextIcon, CameraIcon, CheckIcon] as const;

/** Horizontal stepper (Figma 278:3786): 40px circles, 2px 64px connectors, the
 * current step at full opacity and the rest at 50%. A completed step keeps its
 * own glyph in a filled green circle. */
export function Stepper({ step, done }: { step: number; done: boolean[] }) {
  return (
    <div className="rounded-card-sm border border-line bg-surface-card px-6 py-6">
      <ol className="flex items-center justify-between gap-2">
        {STEPS.map((label, i) => {
          const n = i + 1;
          const Icon = STEP_ICONS[i];
          const isCurrent = n === step;
          const isDone = done[i] && !isCurrent;
          return (
            <li key={label} className="flex flex-1 items-center gap-2 last:flex-none">
              <div
                className={`flex w-[100px] flex-none flex-col items-center gap-2 ${
                  isCurrent ? '' : 'opacity-50'
                }`}
              >
                <span
                  className={`flex h-10 w-10 items-center justify-center rounded-full border-2 ${
                    isCurrent
                      ? 'border-emerald-deep bg-emerald-deep text-white'
                      : isDone
                        ? 'border-done-700 bg-done-50 text-done-700'
                        : 'border-line-strong bg-surface-card text-ink-500'
                  }`}
                >
                  {isDone ? (
                    <CheckIcon className="h-4 w-4" strokeWidth={2.4} />
                  ) : (
                    <Icon className="h-4 w-4" strokeWidth={2} />
                  )}
                </span>
                <span className="text-center text-xs font-medium leading-4 text-ink-900">
                  {label}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <span
                  aria-hidden
                  className={`h-0.5 w-16 flex-none ${done[i] ? 'bg-emerald-deep' : 'bg-line-strong'}`}
                />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** One labelled question with its option row (Figma 278:3837). */
export function Question({
  label,
  required = false,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm font-medium text-ink-900">
        {label}
        {required && <span className="ml-0.5 text-status-danger">*</span>}
      </p>
      {children}
    </div>
  );
}

export type OptionTone = 'positive' | 'negative';

const TONE_SELECTED: Record<OptionTone, string> = {
  positive: 'border-done-700 bg-done-50 text-done-700',
  negative: 'border-distress-700 bg-distress-50 text-distress-700',
};

/** A yes/no option card (Figma 278:3841): 92px tall, 2px border, 10px radius,
 * a 24px glyph over a 16px label. Renders as a real radio group so the pair is
 * keyboard-navigable and announced as one question. */
export function OptionPair({
  name,
  value,
  onChange,
  yes,
  no,
}: {
  name: string;
  value: 'yes' | 'no' | null;
  onChange: (v: 'yes' | 'no') => void;
  yes: string;
  no: string;
}) {
  const options: { v: 'yes' | 'no'; label: string; tone: OptionTone }[] = [
    { v: 'yes', label: yes, tone: 'positive' },
    { v: 'no', label: no, tone: 'negative' },
  ];
  return (
    <div role="radiogroup" aria-label={name} className="flex gap-4">
      {options.map(({ v, label, tone }) => {
        const selected = value === v;
        const Icon = v === 'yes' ? CheckCircleGlyph : XGlyph;
        return (
          <button
            key={v}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(v)}
            className={`flex h-[92px] flex-1 flex-col items-center justify-center gap-2 rounded-[10px] border-2 text-base font-medium transition ${
              selected ? TONE_SELECTED[tone] : 'border-line-strong text-ink-900 hover:border-ink-500'
            }`}
          >
            <Icon className="h-6 w-6" />
            {label}
          </button>
        );
      })}
    </div>
  );
}

function CheckCircleGlyph({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M21.5 11.1V12a9.5 9.5 0 1 1-5.6-8.7" />
      <path d="m9 11.5 3 3 9.5-9.5" />
    </svg>
  );
}

function XGlyph({ className }: { className?: string }) {
  return <XIcon className={className} strokeWidth={1.8} />;
}

const textareaBase =
  'w-full rounded-[10px] border border-line-strong px-4 py-3 text-base leading-6 text-ink-900 outline-none transition placeholder:text-ink-900/50 focus:border-emerald-deep';

export function NotesField({
  label,
  value,
  onChange,
  placeholder,
  rows = 4,
  required = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  rows?: number;
  required?: boolean;
}) {
  return (
    <label className="flex flex-col gap-3">
      <span className="text-sm font-medium text-ink-900">
        {label}
        {required && <span className="ml-0.5 text-status-danger">*</span>}
      </span>
      <textarea
        rows={rows}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={textareaBase}
      />
    </label>
  );
}

const SUMMARY_TONE: Record<SummaryRow['tone'], string> = {
  positive: 'text-done-700',
  caution: 'text-pending-700',
  negative: 'text-distress-700',
  neutral: 'text-ink-900',
};

/** Report Summary panel (Figma Section 5) — also what the rail's Preview Report
 * shows, so it reads correctly part-way through the wizard. */
export function ReportSummary({ form }: { form: ReportForm }) {
  return (
    <div className="rounded-card-sm bg-surface-warm p-6">
      <p className="text-sm font-semibold text-ink-900">Report Summary</p>
      <dl className="mt-3 space-y-2">
        {reportSummary(form).map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-4 text-sm">
            <dt className="text-ink-700">{row.label}:</dt>
            <dd className={`font-medium ${SUMMARY_TONE[row.tone]}`}>{row.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
