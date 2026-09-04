import { AlertCircleIcon, CalendarIcon, CheckCircleIcon, ClockIcon } from '../_icons';
import { inspectionStatusMeta } from '@/lib/realtor-inspection';

/** Inspection status pill (SCRUM-204, Figma 280:5555): 26px tall, fully
 * rounded, a -100 fill inside a -200 border, with a 12px glyph that restates
 * the state for anyone who can't rely on the colour alone. */
export function StatusPill({ status }: { status: string }) {
  const meta = inspectionStatusMeta(status);
  const Icon =
    meta.bucket === 'awaiting'
      ? ClockIcon
      : meta.bucket === 'completed'
        ? CheckCircleIcon
        : CalendarIcon;

  return (
    <span
      className={`inline-flex h-[26px] items-center gap-1.5 rounded-full border px-3 text-xs font-medium ${meta.pill}`}
    >
      <Icon className="h-3 w-3 flex-none" strokeWidth={2} />
      {meta.label}
    </span>
  );
}

/** Distress-sale marker beneath a property title (§8 rule 2). Fill + text, no
 * border — the one badge on this screen drawn that way. */
export function DistressBadge() {
  return (
    <span className="inline-flex h-5 items-center gap-1.5 rounded bg-distress-100 px-2 text-xs font-medium text-distress-700">
      <AlertCircleIcon className="h-3 w-3 flex-none" strokeWidth={2} />
      Distress Sale
    </span>
  );
}
