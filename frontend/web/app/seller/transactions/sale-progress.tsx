import { SELLER_MILESTONES, sellerCompletedSteps } from '@/lib/seller-deal-stage';

/** Vertical 7-step progress timeline for a seller transaction (SCRUM-98).
 * Shared by the Transactions list cards and the detail page. */
export function SaleProgress({ stage, compact }: { stage: string; compact?: boolean }) {
  const done = sellerCompletedSteps(stage);
  const current = done; // the first not-yet-complete step is the active one

  return (
    <ol className="space-y-0">
      {SELLER_MILESTONES.map((m, i) => {
        const isDone = i < done;
        const isCurrent = i === current;
        const last = i === SELLER_MILESTONES.length - 1;
        return (
          <li key={m.title} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span
                className={`flex h-6 w-6 flex-none items-center justify-center rounded-full text-xs ${
                  isDone
                    ? 'bg-emerald-deep text-white'
                    : isCurrent
                      ? 'border-2 border-amber-500 text-amber-600'
                      : 'border border-ink-300/50 text-ink-300'
                }`}
              >
                {isDone ? '✓' : isCurrent ? '◷' : ''}
              </span>
              {!last && <span className={`w-px flex-1 ${isDone ? 'bg-emerald-deep' : 'bg-ink-300/30'} ${compact ? 'min-h-5' : 'min-h-7'}`} />}
            </div>
            <div className={last ? 'pb-0' : 'pb-4'}>
              <p className={`text-sm ${isDone || isCurrent ? 'font-medium text-ink-900' : 'text-ink-500'}`}>
                {m.title}
              </p>
              {!compact && (isDone || isCurrent) && (
                <p className={`text-xs ${isCurrent ? 'text-amber-600' : 'text-ink-500'}`}>
                  {isCurrent ? 'In progress' : m.desc}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
