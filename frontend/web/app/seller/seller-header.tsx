import Link from 'next/link';

/** Seller page header (SCRUM-98): title + subtitle on the left, the global
 * "Create Listing" action on the right. */
export function SellerHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="font-display text-3xl text-emerald-deep">{title}</h1>
        <p className="mt-1 text-sm text-ink-500">{subtitle}</p>
      </div>
      <Link
        href="/seller/listings/new"
        className="rounded-lg bg-emerald-deep px-4 py-2.5 text-sm font-semibold text-bone transition hover:bg-emerald-accent"
      >
        + Create Listing
      </Link>
    </div>
  );
}
