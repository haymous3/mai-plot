/** Realtor page header (SCRUM-140): title + subtitle. No global action button —
 * the realtor's primary actions live on the section pages. */
export function RealtorHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="font-display text-3xl text-emerald-deep">{title}</h1>
        <p className="mt-1 text-sm text-ink-500">{subtitle}</p>
      </div>
    </div>
  );
}
