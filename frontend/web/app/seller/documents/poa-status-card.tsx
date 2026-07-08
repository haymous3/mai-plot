import type { SellerPoaStatus } from '@/lib/api';

/** Seller-facing Power-of-Attorney verification tracker (SCRUM-137).
 * Only shown to power_of_attorney sellers — an owner has no PoA to track. */
const STATUS_STYLE: Record<
  string,
  { label: string; badge: string; card: string; icon: string }
> = {
  pending: {
    label: 'Under review',
    badge: 'bg-amber-100 text-amber-700',
    card: 'border-amber-200 bg-amber-50/60',
    icon: '◷',
  },
  verified: {
    label: 'Verified',
    badge: 'bg-emerald-deep/10 text-emerald-deep',
    card: 'border-emerald-deep/20 bg-emerald-deep/5',
    icon: '✓',
  },
  rejected: {
    label: 'Rejected',
    badge: 'bg-red-100 text-red-700',
    card: 'border-red-200 bg-red-50/70',
    icon: '✕',
  },
  not_submitted: {
    label: 'Not submitted',
    badge: 'bg-ink-300/20 text-ink-600',
    card: 'border-ink-300/30 bg-white',
    icon: '○',
  },
};

export function PoaStatusCard({ poa }: { poa: SellerPoaStatus }) {
  if (poa.authority_type !== 'power_of_attorney') return null;

  // A pending PoA with no document on file yet reads as "not submitted".
  const key =
    poa.status === 'pending' && !poa.has_document ? 'not_submitted' : poa.status;
  const style = STATUS_STYLE[key] ?? STATUS_STYLE.pending;
  const submitted = poa.submitted_at
    ? new Date(poa.submitted_at).toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    : null;

  return (
    <div className={`mb-6 rounded-2xl border p-5 ${style.card}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="text-xl">{style.icon}</span>
          <div>
            <p className="font-medium text-ink-900">Power of Attorney</p>
            <p className="text-xs text-ink-500">
              {submitted ? `Submitted ${submitted}` : 'Legal-team verification required'}
            </p>
          </div>
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-medium ${style.badge}`}>
          {style.label}
        </span>
      </div>

      {poa.status === 'rejected' && poa.rejection_reason && (
        <p className="mt-3 rounded-lg bg-white/70 px-3 py-2 text-xs text-red-700">
          <span className="font-medium">Reason:</span> {poa.rejection_reason}
        </p>
      )}

      {!poa.can_publish && (
        <p className="mt-3 text-xs text-ink-600">
          You cannot publish listings until your Power of Attorney is verified by our legal team.
          {poa.status === 'rejected' && ' Please re-upload a corrected document during onboarding.'}
        </p>
      )}
    </div>
  );
}
