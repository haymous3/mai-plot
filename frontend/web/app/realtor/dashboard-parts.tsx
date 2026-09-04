import Link from 'next/link';

import {
  AlertCircleIcon,
  ArrowRightIcon,
  CalendarIcon,
  CheckCircleIcon,
  ClockIcon,
  FileTextIcon,
  MapPinIcon,
  TrendingUpIcon,
  WalletIcon,
} from './_icons';
import { StatusPill } from './inspections/status-pill';
import type { RealtorInspection } from '@/lib/api';
import { formatDate, formatTimeOfDay } from '@/lib/format';
import { inspectionLocation, relativeTime } from '@/lib/realtor-inspection';

/** Dashboard presentational pieces (SCRUM-204, Figma 276:4). */

export type StatTone = 'pending' | 'done' | 'scheduled' | 'neutral';

const STAT_CHIP: Record<StatTone, string> = {
  pending: 'bg-pending-100 text-pending-700',
  done: 'bg-done-100 text-done-700',
  scheduled: 'bg-scheduled-100 text-scheduled-700',
  neutral: 'bg-surface-muted text-ink-700',
};

const STAT_ICON = {
  pending: ClockIcon,
  done: CheckCircleIcon,
  scheduled: CalendarIcon,
  neutral: WalletIcon,
} as const;

/** Stat card (Figma 276:87): 162px tall, 14px radius, a 40px tinted icon chip
 * over a 30px value and a 14px label. */
export function StatCard({
  tone,
  value,
  label,
}: {
  tone: StatTone;
  value: string;
  label: string;
}) {
  const Icon = STAT_ICON[tone];
  return (
    <div className="rounded-card-sm border border-line bg-surface-card p-6">
      <span
        className={`flex h-10 w-10 items-center justify-center rounded-[10px] ${STAT_CHIP[tone]}`}
      >
        <Icon className="h-5 w-5" />
      </span>
      <p className="mt-9 text-3xl font-bold leading-9 text-ink-900">{value}</p>
      <p className="mt-1 text-sm leading-5 text-ink-600">{label}</p>
    </div>
  );
}

/** One row of Upcoming Inspections (Figma 276:4): thumbnail, title, location,
 * date + time, status pill and the buyer reference. */
export function UpcomingRow({ insp }: { insp: RealtorInspection }) {
  const scheduledAt = insp.confirmed_date ?? insp.proposed_date;
  return (
    <Link
      href={`/realtor/inspections/${insp.inspection_id}`}
      className="flex items-center gap-4 rounded-[10px] border border-line p-4 transition hover:border-ink-500/40"
    >
      {insp.cover_photo_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={insp.cover_photo_url}
          alt=""
          className="h-14 w-20 flex-none rounded-[10px] object-cover"
        />
      ) : (
        <div aria-hidden className="h-14 w-20 flex-none rounded-[10px] bg-surface-muted" />
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-base font-semibold text-ink-900">
          {insp.property_title ?? 'Property inspection'}
        </p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-4 gap-y-0.5 text-sm text-ink-600">
          <span className="flex items-center gap-1.5">
            <MapPinIcon className="h-4 w-4 flex-none" />
            {inspectionLocation(insp)}
          </span>
          <span className="flex items-center gap-1.5">
            <CalendarIcon className="h-4 w-4 flex-none" />
            {formatDate(scheduledAt)} at {formatTimeOfDay(scheduledAt)}
          </span>
        </p>
        <p className="mt-2 flex flex-wrap items-center gap-3">
          <StatusPill status={insp.status} />
          <span className="text-xs text-ink-600">
            Ref: <span className="font-mono">{insp.buyer_ref.toUpperCase()}</span>
          </span>
        </p>
      </div>
      <ArrowRightIcon className="h-5 w-5 flex-none text-ink-500" />
    </Link>
  );
}

export type ActivityKind = 'assigned' | 'submitted' | 'payment';

export interface ActivityItem {
  kind: ActivityKind;
  title: string;
  detail: string;
  ts: string;
}

const ACTIVITY_CHIP: Record<ActivityKind, string> = {
  assigned: 'bg-scheduled-100 text-scheduled-700',
  submitted: 'bg-pending-100 text-pending-700',
  payment: 'bg-done-100 text-done-700',
};

const ACTIVITY_ICON = {
  assigned: FileTextIcon,
  submitted: FileTextIcon,
  payment: WalletIcon,
} as const;

/** Recent Activity feed (Figma 276:4). The design also draws an "Inspection
 * report approved" event; there is no report-review workflow in any service
 * yet, so that row is not invented — this feed carries only events with real
 * backing: assignment, report submission, and commission disbursement. */
export function ActivityRow({ item }: { item: ActivityItem }) {
  const Icon = ACTIVITY_ICON[item.kind];
  return (
    <li className="flex items-start gap-3 border-b border-line py-4 last:border-b-0">
      <span
        className={`flex h-9 w-9 flex-none items-center justify-center rounded-[10px] ${ACTIVITY_CHIP[item.kind]}`}
      >
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-ink-900">{item.title}</p>
        <p className="truncate text-sm text-ink-600">{item.detail}</p>
        <p className="mt-0.5 text-xs text-ink-500">{relativeTime(item.ts)}</p>
      </div>
    </li>
  );
}

/** The cream verification-impact note shared by the dashboard rail and the
 * report wizard (Figma 276:292 / 278:3906). */
export function VerificationImpactCard({ body }: { body: string }) {
  return (
    <div className="flex gap-3 rounded-card-sm border border-status-gold/20 bg-surface-warm p-[17px]">
      <AlertCircleIcon className="mt-0.5 h-5 w-5 flex-none text-status-gold" />
      <div>
        <p className="text-sm font-medium text-ink-900">Verification Impact</p>
        <p className="mt-1 text-xs leading-5 text-ink-600">{body}</p>
      </div>
    </div>
  );
}

/** "Your Impact" hero (Figma 276:282) — a 146° emerald gradient, the one place
 * in the realtor portal with a gradient rather than a flat fill. */
export function ImpactCard({ value, label }: { value: string; label: string }) {
  return (
    <div
      className="rounded-card-sm p-6"
      style={{ backgroundImage: 'linear-gradient(146.4deg, #0f3d2e 0%, #0a2d21 100%)' }}
    >
      <TrendingUpIcon className="h-8 w-8 text-white" />
      <p className="mt-3 text-sm leading-5 text-white/90">This Month</p>
      <p className="mt-2 text-3xl font-bold leading-9 text-white">{value}</p>
      <p className="mt-1 text-sm leading-5 text-white/90">{label}</p>
    </div>
  );
}
