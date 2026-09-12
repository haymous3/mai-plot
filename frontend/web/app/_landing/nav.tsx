'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { BrandLogo } from '@/app/_components/brand-logo';

/**
 * Public top navigation — SCRUM-178.
 *
 * STICKY since SCRUM-204, and rendered by the page rather than by the hero.
 *
 * It could not stay inside the hero `<section>`: `position: sticky` is bounded
 * by its parent, so it would have unstuck at the bottom of the hero — and that
 * section carries `overflow-hidden`, which disables sticky outright. Neither
 * fails loudly; the nav would simply have scrolled away.
 *
 * The background is a flat `emerald-deep` with no scroll listener, because the
 * hero's gradient is solid `emerald-deep` for its first 85%. At rest the bar is
 * therefore indistinguishable from the transparent-over-hero look the export
 * draws — no rule, no shadow, just continuous colour — and once the page
 * scrolls it is what keeps white links legible over white content.
 *
 * Measured (1577px artboard, container 180..1396):
 *   row height    72px  (Get Started spans y16..55, so 40px centred in 72)
 *   logo          house glyph only — NO wordmark. The wordmark appears in the
 *                 footer lockup, not here. Verified on a contrast-stretched
 *                 crop; there is no faint text next to the icon. Since
 *                 SCRUM-230 the glyph is the logo's own house-on-H mark rather
 *                 than a generic line icon; still glyph-only, as designed.
 *   link gaps     ~32px between items
 *   Get Started   118×40, 12px radius, `status-gold` fill
 *
 * SCRUM-216 makes it a client component so it can tell whether the page has
 * scrolled. At rest it stays flat, exactly as described above; once past the
 * first few pixels it gains a shadow and a hairline, which is what separates
 * the bar from white content scrolling under it. There is no colour change —
 * the fill is already `emerald-deep` at both ends.
 *
 * ⚠️ `Shell` is deliberately INLINED here rather than imported. It lives in
 * `sections.tsx`, and importing a 23KB module of server-rendered sections into
 * a client component would pull all of it into the browser bundle to reuse one
 * `<div>` of container padding.
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
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    // Read once on mount as well as on scroll: a reload partway down the page,
    // or a back-navigation that restores scroll position, both start already
    // scrolled and would otherwise render the flat bar over white content.
    const sync = () => setScrolled(window.scrollY > 8);
    sync();
    window.addEventListener('scroll', sync, { passive: true });
    return () => window.removeEventListener('scroll', sync);
  }, []);

  return (
    <header
      className={`sticky top-0 z-50 bg-emerald-deep transition-shadow duration-300 ${
        scrolled ? 'shadow-lg shadow-black/10 ring-1 ring-white/10' : ''
      }`}
    >
      <div className="mx-auto flex h-18 w-full max-w-[1280px] items-center justify-between px-8">
        <Link href="/" className="flex items-center text-white" aria-label="Maihomme home">
          <BrandLogo variant="mark" tone="dark" height={30} priority />
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

        {/* Log In was removed here (SCRUM-204): the hero now carries Sign In
            and Sign Up as its two calls to action, so a third auth entry point
            in the bar was competing with them. */}
        <div className="flex items-center gap-7">
          <Link
            href="/register"
            className="inline-flex h-10 items-center rounded-xl bg-status-gold px-5 text-[15px] font-semibold leading-5 text-white transition hover:brightness-105"
          >
            Get Started
          </Link>
        </div>
      </div>
    </header>
  );
}
