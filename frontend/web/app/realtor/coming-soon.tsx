import { RealtorHeader } from './realtor-header';

/** Placeholder for realtor sections still landing in this epic (SCRUM-140).
 * Replaced by the real page in its PR (inspections → PR2, reports → PR4,
 * earnings → PR5). */
export function ComingSoon({ title, subtitle, note }: { title: string; subtitle: string; note: string }) {
  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <RealtorHeader title={title} subtitle={subtitle} />
      <div className="mt-8 rounded-2xl border border-dashed border-ink-300/50 bg-white/60 px-6 py-16 text-center">
        <p className="text-sm text-ink-500">{note}</p>
      </div>
    </main>
  );
}
