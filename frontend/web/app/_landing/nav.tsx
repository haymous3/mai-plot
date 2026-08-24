import Link from 'next/link';

import { HouseIcon } from './icons';
import { Shell } from './sections';

/**
 * Public top navigation — SCRUM-178.
 *
 * Sits transparently on top of the hero rather than being its own bar: the
 * export has no rule, no fill and no shadow between the nav row and the
 * headline, just continuous `emerald-deep`.
 *
 * Measured (1577px artboard, container 180..1396):
 *   row height    72px  (Get Started spans y16..55, so 40px centred in 72)
 *   logo          house glyph only — NO wordmark. The wordmark appears in the
 *                 footer lockup, not here. Verified on a contrast-stretched
 *                 crop; there is no faint text next to the icon.
 *   link gaps     ~32px between items
 *   Get Started   118×40, 12px radius, `status-gold` fill
 *
 * The link group sits ~20px left of the true container centre in the export.
 * That is not reproduced: `justify-between` puts it ~20px further left still,
 * and chasing the difference would mean hard-coding a magic offset for a
 * position that is imperceptible and would break at any other viewport.
 */

/** Nav destinations. `href` omitted = no route exists, so it renders as plain text. */
const LINKS: { label: string; href?: string }[] = [
  { label: 'Properties', href: '/dashboard' },
  { label: 'How It Works', href: '#how-it-works' },
  { label: 'Financing', href: '#financing' },
  // The realtor funnel is the closest real destination, and the footer already
  // sends "Agent Registration" here.
  { label: 'Agents', href: '/register' },
  // No blog exists. Plain text beats a 404 — same rule the footer follows.
  { label: 'Blog' },
];

export function Nav() {
  return (
    <header className="relative z-10">
      <Shell className="flex h-18 items-center justify-between">
        <Link href="/" className="flex items-center text-white" aria-label="Maihomme home">
          <HouseIcon className="h-7 w-7" strokeWidth={2} />
        </Link>

        <nav aria-label="Primary" className="hidden lg:block">
          <ul className="flex items-center gap-8">
            {LINKS.map(({ label, href }) => (
              <li key={label}>
                {href ? (
                  <Link
                    href={href}
                    className="text-[15px] leading-5 text-white/90 transition hover:text-white"
                  >
                    {label}
                  </Link>
                ) : (
                  <span className="text-[15px] leading-5 text-white/90">{label}</span>
                )}
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex items-center gap-7">
          <Link
            href="/login"
            className="text-[15px] leading-5 text-white/90 transition hover:text-white"
          >
            Log In
          </Link>
          <Link
            href="/register"
            className="inline-flex h-10 items-center rounded-xl bg-status-gold px-5 text-[15px] font-semibold leading-5 text-white transition hover:brightness-105"
          >
            Get Started
          </Link>
        </div>
      </Shell>
    </header>
  );
}
