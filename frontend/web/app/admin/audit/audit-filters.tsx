'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

export interface AuditFilterValues {
  entity_type: string;
  action: string;
  actor_id: string;
  date_from: string;
  date_to: string;
}

/**
 * Audit-log filter bar (SCRUM-127). Submitting pushes the non-empty filters into
 * the URL query (resetting to page 1); the Server Component refetches. Filters
 * mirror the SCRUM-126 backend params (entity_type / action / actor_id / date
 * range). Date inputs send a yyyy-mm-dd the backend parses as a datetime.
 */
export function AuditFilters({ current }: { current: AuditFilterValues }) {
  const router = useRouter();
  const [values, setValues] = useState<AuditFilterValues>(current);

  function set(key: keyof AuditFilterValues, value: string) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  function apply() {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(values)) {
      if (value.trim()) params.set(key, value.trim());
    }
    const qs = params.toString();
    router.push(qs ? `/admin/audit?${qs}` : '/admin/audit');
  }

  function clear() {
    setValues({ entity_type: '', action: '', actor_id: '', date_from: '', date_to: '' });
    router.push('/admin/audit');
  }

  const inputClass =
    'rounded-md border border-ink-300/60 px-3 py-1.5 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-emerald-deep focus:ring-2 focus:ring-emerald-deep/20';

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        apply();
      }}
      className="mb-5 flex flex-wrap items-end gap-3 rounded-lg border border-ink-300/30 bg-white p-4"
    >
      <label className="flex flex-col gap-1 text-xs text-ink-500">
        Entity type
        <input
          value={values.entity_type}
          onChange={(e) => set('entity_type', e.target.value)}
          placeholder="listing, realtor…"
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-ink-500">
        Action
        <input
          value={values.action}
          onChange={(e) => set('action', e.target.value)}
          placeholder="listing.approved"
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-ink-500">
        Actor ID
        <input
          value={values.actor_id}
          onChange={(e) => set('actor_id', e.target.value)}
          placeholder="UUID"
          className={`${inputClass} w-44`}
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-ink-500">
        From
        <input
          type="date"
          value={values.date_from}
          onChange={(e) => set('date_from', e.target.value)}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-ink-500">
        To
        <input
          type="date"
          value={values.date_to}
          onChange={(e) => set('date_to', e.target.value)}
          className={inputClass}
        />
      </label>
      <div className="flex gap-2">
        <button
          type="submit"
          className="rounded-md bg-emerald-deep px-4 py-1.5 text-sm font-medium text-bone transition hover:bg-emerald-accent"
        >
          Filter
        </button>
        <button
          type="button"
          onClick={clear}
          className="rounded-md border border-ink-300/60 px-4 py-1.5 text-sm font-medium text-ink-500 transition hover:border-ink-500 hover:text-ink-900"
        >
          Clear
        </button>
      </div>
    </form>
  );
}
