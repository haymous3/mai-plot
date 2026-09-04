import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { InspectionActions } from './inspection-actions';
import { ArrowLeftIcon, CalendarIcon, ClockIcon, HouseIcon, MapPinIcon } from '../../_icons';
import { StatusPill, DistressBadge } from '../status-pill';
import type { RealtorInspection, RealtorInspectionsResponse } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { formatDate, formatNaira, formatTimeOfDay, isPowerOfAttorney } from '@/lib/format';
import { reportSubmittable } from '@/lib/inspection-report';
import { inspectionLocation, isDistressSale, propertyTypeLabel } from '@/lib/realtor-inspection';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Inspection · Maihomme Realtor' };

/** Assignment detail (SCRUM-204). New page — the designed table's "View
 * Details" had nowhere to go. Carries the property context the realtor needs on
 * site, plus every per-assignment action: accepting inside the 2-hour window,
 * proposing an alternate time, and starting the report.
 *
 * Resolved from the realtor's own assignments because there is no
 * single-inspection GET; that also means an inspection belonging to another
 * realtor 404s here rather than leaking. */
export default async function InspectionDetailPage({ params }: { params: { id: string } }) {
  const res = await sessionBackendGet<RealtorInspectionsResponse>(
    `${realtorServiceUrl()}/inspections/mine`,
  );

  if (!res.ok) {
    return (
      <main className="mx-auto max-w-[1088px] px-8 py-8">
        <BackLink />
        <div className="mt-8 rounded-card-sm border border-status-danger/30 bg-distress-100 px-6 py-10 text-center text-sm text-distress-700">
          Could not load this inspection. Please retry.
        </div>
      </main>
    );
  }

  const insp = res.data.data.find((i) => i.inspection_id === params.id);
  if (!insp) notFound();

  const gate = reportSubmittable(insp);
  const scheduledAt = insp.confirmed_date ?? insp.proposed_date;

  return (
    <main className="mx-auto max-w-[1088px] px-8 py-8">
      <BackLink />

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          <PropertyCard insp={insp} scheduledAt={scheduledAt} />
          <PartiesCard insp={insp} />
        </div>

        <aside className="space-y-4">
          {insp.status === 'pending' && <InspectionActions insp={insp} />}

          {gate.ok ? (
            <Link
              href={`/realtor/inspections/${insp.inspection_id}/report`}
              className="flex h-11 items-center justify-center rounded-[10px] bg-emerald-deep text-sm font-semibold text-white transition hover:bg-emerald-accent"
            >
              Submit inspection report
            </Link>
          ) : gate.reason === 'too_early' ? (
            <div className="rounded-card-sm border border-pending-200 bg-pending-50 p-6">
              <p className="text-sm font-medium text-pending-700">Report opens on inspection day</p>
              <p className="mt-1 text-xs text-ink-600">
                You can submit your report on or after
                {gate.opensAt ? ` ${formatDate(gate.opensAt)}` : ' the confirmed date'}.
              </p>
            </div>
          ) : insp.report_submitted_at ? (
            <div className="rounded-card-sm border border-done-200 bg-done-50 p-6">
              <p className="text-sm font-medium text-done-700">Report submitted</p>
              <p className="mt-1 text-xs text-ink-600">
                Sent {formatDate(insp.report_submitted_at)}.
              </p>
              <Link
                href="/realtor/reports"
                className="mt-3 inline-block text-xs font-medium text-emerald-deep hover:underline"
              >
                View report history
              </Link>
            </div>
          ) : null}
        </aside>
      </div>
    </main>
  );
}

function BackLink() {
  return (
    <Link
      href="/realtor/inspections"
      className="inline-flex items-center gap-2 text-sm font-medium text-ink-600 transition hover:text-ink-900"
    >
      <ArrowLeftIcon className="h-4 w-4" />
      Back to Inspections
    </Link>
  );
}

function PropertyCard({ insp, scheduledAt }: { insp: RealtorInspection; scheduledAt: string }) {
  const type = propertyTypeLabel(insp.property_type);

  return (
    <section className="rounded-card-sm border border-line bg-surface-card p-6">
      <div className="flex flex-wrap items-start gap-4">
        {insp.cover_photo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={insp.cover_photo_url}
            alt=""
            className="h-20 w-24 flex-none rounded-[10px] object-cover"
          />
        ) : (
          <div aria-hidden className="h-20 w-24 flex-none rounded-[10px] bg-surface-muted" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-display text-2xl font-bold text-ink-900">
              {insp.property_title ?? 'Property inspection'}
            </h1>
            <StatusPill status={insp.status} />
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-600">
            <span className="flex items-center gap-1.5">
              <MapPinIcon className="h-4 w-4 flex-none text-ink-500" />
              {inspectionLocation(insp)}
            </span>
            <span className="flex items-center gap-1.5">
              <CalendarIcon className="h-4 w-4 flex-none text-ink-500" />
              {formatDate(scheduledAt)}
            </span>
            <span className="flex items-center gap-1.5">
              <ClockIcon className="h-4 w-4 flex-none text-ink-500" />
              {formatTimeOfDay(scheduledAt)}
            </span>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {type && (
              <span className="inline-flex h-6 items-center gap-1.5 rounded-full bg-surface-muted px-3 text-xs font-medium text-ink-700">
                <HouseIcon className="h-3 w-3 flex-none" strokeWidth={2} />
                {type}
                {insp.size_sqm ? ` · ${insp.size_sqm.toLocaleString('en-NG')} sqm` : ''}
              </span>
            )}
            {isDistressSale(insp) && <DistressBadge />}
            {insp.asking_price_kobo !== null && (
              <span className="inline-flex h-6 items-center rounded-full bg-emerald-deep px-3 text-xs font-semibold text-white">
                {formatNaira(insp.asking_price_kobo)}
              </span>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

/** Who the realtor deals with on site, and the references to quote. The seller
 * phone arrives already masked from realtor-service — the raw number is never
 * sent to the browser (CLAUDE.md §10). */
function PartiesCard({ insp }: { insp: RealtorInspection }) {
  return (
    <section className="grid gap-6 rounded-card-sm border border-line bg-surface-card p-6 sm:grid-cols-3">
      <Detail label="Contact Person">
        {insp.seller_name ? (
          <>
            <p className="font-medium text-ink-900">{insp.seller_name}</p>
            {insp.seller_phone_masked && (
              <p className="mt-0.5 text-sm text-ink-600">{insp.seller_phone_masked}</p>
            )}
          </>
        ) : (
          <p className="text-sm text-ink-500">Not available</p>
        )}
      </Detail>

      <Detail label="Seller Authority">
        <p className="font-medium text-ink-900">
          {insp.seller_authority_type === null
            ? 'Not stated'
            : isPowerOfAttorney(insp.seller_authority_type)
              ? 'Power of Attorney'
              : 'Property Owner'}
        </p>
      </Detail>

      <Detail label="Reference IDs">
        <p className="text-sm text-ink-600">
          Inspection:{' '}
          <span className="font-mono text-ink-900">{insp.inspection_ref.toUpperCase()}</span>
        </p>
        <p className="mt-0.5 text-sm text-ink-600">
          Buyer: <span className="font-mono text-ink-900">{insp.buyer_ref.toUpperCase()}</span>
        </p>
      </Detail>
    </section>
  );
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs text-ink-500">{label}</p>
      <div className="mt-1">{children}</div>
    </div>
  );
}
