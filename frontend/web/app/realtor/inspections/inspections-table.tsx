'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';

import { StatusPill, DistressBadge } from './status-pill';
import {
  ArrowRightIcon,
  CalendarIcon,
  ChevronDownIcon,
  ClockIcon,
  FilterIcon,
  MapPinIcon,
  SearchIcon,
} from '../_icons';
import type { RealtorInspection } from '@/lib/api';
import { formatDate, formatTimeOfDay } from '@/lib/format';
import {
  filterInspections,
  INSPECTION_FILTERS,
  inspectionLocationLines,
  isDistressSale,
  propertyTypeLabel,
  type InspectionFilter,
} from '@/lib/realtor-inspection';

/** Assigned Inspections table (SCRUM-204, Figma 280:5555). Search + status
 * filter are client state over the full assignment list — the realtor has at
 * most a working caseload of rows, so filtering in the browser avoids a round
 * trip per keystroke. */
export function InspectionsTable({ items }: { items: RealtorInspection[] }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<InspectionFilter>('all');

  const rows = useMemo(
    () => filterInspections(items, { query, status }),
    [items, query, status],
  );

  return (
    <>
      <div className="mt-8 rounded-card-sm border border-line bg-surface-card p-6">
        <div className="flex flex-wrap items-center gap-4">
          <div className="relative min-w-[240px] flex-1">
            <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-500" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search inspections"
              placeholder="Search by property, location, or ID..."
              className="h-[50px] w-full rounded-[10px] border border-line-strong pl-10 pr-4 text-base text-ink-900 outline-none transition placeholder:text-ink-900/50 focus:border-emerald-deep"
            />
          </div>
          <div className="relative w-[183px]">
            <FilterIcon className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-500" />
            <ChevronDownIcon className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-500" />
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as InspectionFilter)}
              aria-label="Filter by status"
              className="h-[50px] w-full appearance-none rounded-[10px] border border-line-strong bg-surface-card pl-10 pr-9 text-sm text-ink-900 outline-none transition focus:border-emerald-deep"
            >
              {INSPECTION_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="mt-6 overflow-hidden rounded-card-sm border border-line bg-surface-card">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left">
            <thead>
              <tr className="border-b border-line bg-surface-page text-sm font-semibold text-ink-900">
                <th scope="col" className="px-6 py-4">
                  Property
                </th>
                <th scope="col" className="py-4 pr-6">
                  Location
                </th>
                <th scope="col" className="py-4 pr-6">
                  Schedule
                </th>
                <th scope="col" className="py-4 pr-6">
                  Reference
                </th>
                <th scope="col" className="py-4 pr-6">
                  Status
                </th>
                <th scope="col" className="py-4 pr-6 text-right">
                  Action
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-16 text-center text-sm text-ink-500">
                    No inspections match your search.
                  </td>
                </tr>
              ) : (
                rows.map((insp) => <Row key={insp.inspection_id} insp={insp} />)
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function Row({ insp }: { insp: RealtorInspection }) {
  const { primary, secondary } = inspectionLocationLines(insp);
  const type = propertyTypeLabel(insp.property_type);

  return (
    <tr className="border-b border-line last:border-b-0">
      <td className="px-6 py-4">
        <div className="flex items-center gap-3">
          {insp.cover_photo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={insp.cover_photo_url}
              alt=""
              className="h-16 w-16 flex-none rounded-[10px] object-cover"
            />
          ) : (
            <div
              aria-hidden
              className="h-16 w-16 flex-none rounded-[10px] bg-surface-muted"
            />
          )}
          <div className="min-w-0">
            <p className="truncate font-medium text-ink-900">
              {insp.property_title ?? 'Property inspection'}
            </p>
            {type && <p className="mt-0.5 text-sm text-ink-600">{type}</p>}
            {isDistressSale(insp) && (
              <span className="mt-1 block">
                <DistressBadge />
              </span>
            )}
          </div>
        </div>
      </td>

      <td className="py-4 pr-6 align-middle">
        <div className="flex items-start gap-2">
          <MapPinIcon className="mt-0.5 h-4 w-4 flex-none text-ink-500" />
          <div className="min-w-0">
            {primary && <p className="text-sm text-ink-900">{primary}</p>}
            {secondary && <p className="text-xs text-ink-600">{secondary}</p>}
          </div>
        </div>
      </td>

      <td className="py-4 pr-6 align-middle">
        <div className="space-y-1">
          <p className="flex items-center gap-2 text-sm text-ink-900">
            <CalendarIcon className="h-4 w-4 flex-none text-ink-500" />
            {formatDate(insp.confirmed_date ?? insp.proposed_date)}
          </p>
          <p className="flex items-center gap-2 text-sm text-ink-600">
            <ClockIcon className="h-4 w-4 flex-none text-ink-500" />
            {formatTimeOfDay(insp.confirmed_date ?? insp.proposed_date)}
          </p>
        </div>
      </td>

      <td className="py-4 pr-6 align-middle text-xs text-ink-600">
        <p>
          ID: <span className="font-mono text-ink-900">{insp.inspection_ref.toUpperCase()}</span>
        </p>
        <p className="mt-1">
          Buyer: <span className="font-mono text-ink-900">{insp.buyer_ref.toUpperCase()}</span>
        </p>
      </td>

      <td className="py-4 pr-6 align-middle">
        <StatusPill status={insp.status} />
      </td>

      <td className="py-4 pr-6 text-right align-middle">
        <Link
          href={`/realtor/inspections/${insp.inspection_id}`}
          className="inline-flex h-9 items-center gap-2 rounded-[10px] bg-emerald-deep px-4 text-sm font-medium text-white transition hover:bg-emerald-accent"
        >
          View Details
          <ArrowRightIcon className="h-4 w-4 flex-none" />
        </Link>
      </td>
    </tr>
  );
}
