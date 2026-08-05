import Link from 'next/link';

import { Shell } from './sections';

/**
 * Landing page footer — Figma node 627:973 (1577×489). Artboard is 1:1.
 *
 * I originally missed this section: my sweep enumerated frames named "Section",
 * and this one is named "Footer". The arithmetic gives it away — the nine
 * Sections sum to 6726px and the App frame is 7215px; the 489px difference is
 * exactly this footer.
 *
 * ⚠️ BRAND ARCHITECTURE. The design's own copy states:
 *     "MaiHome is the consumer brand of Maiplot Technologies Ltd."
 * plus "© 2026 Maiplot Technologies Ltd." and hello@maihome.ng.
 *
 * So "Maiplot" appearing elsewhere in the product is NOT drift — it is the
 * legal entity, deliberately distinct from the consumer brand. Per SCRUM-174
 * the consumer brand here is rendered as "Maihomme"; the entity name is left
 * as "Maiplot Technologies Ltd" exactly as the design has it.
 *
 * ⚠️ MOST FOOTER LINKS HAVE NO ROUTE. Rather than ship a footer full of 404s,
 * destinations that do not exist render as plain text. Only links with a real
 * route are anchors. See the PR for the full list.
 */

/** A footer link that only becomes an anchor when the route actually exists. */
function FooterLink({ label, href }: { label: string; href?: string }) {
  const cls = 'text-sm leading-5 text-white/60';
  return href ? (
    <Link href={href} className={`${cls} transition hover:text-white`}>
      {label}
    </Link>
  ) : (
    <span className={cls}>{label}</span>
  );
}

function Column({ title, items }: { title: string; items: { label: string; href?: string }[] }) {
  return (
    <div>
      <p className="text-sm font-bold leading-5 text-white/90">{title}</p>
      <ul className="mt-5 flex flex-col gap-3">
        {items.map((i) => (
          <li key={i.label}>
            <FooterLink {...i} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Footer() {
  return (
    <footer className="bg-emerald-deep">
      <Shell className="pb-8 pt-16">
        <div className="grid gap-12 border-b border-white/10 pb-12 lg:grid-cols-5">
          {/* Brand column spans 2 of the 5 tracks — node 627:976. */}
          <div className="lg:col-span-2">
            <div className="flex items-center gap-2.5">
              <span
                aria-hidden
                className="flex h-9 w-9 flex-none items-center justify-center rounded-card-sm bg-white/10 text-sm font-bold text-white"
              >
                M
              </span>
              <span className="font-display text-xl font-bold leading-7 tracking-[-0.5px] text-white">
                Maihomme
              </span>
            </div>

            <p className="mt-5 max-w-[320px] text-sm leading-[22.75px] text-white/65">
              Buy, sell &amp; finance property in Nigeria with verified listings, secure escrow, and
              partner bank financing.
            </p>

            {/* Entity name kept verbatim from the design — it is the legal entity,
                not the consumer brand. */}
            <p className="mt-6 text-xs leading-4 text-white/50">
              Maihomme is the consumer brand of Maiplot Technologies Ltd.
            </p>

            <ul className="mt-6 flex gap-4">
              {['𝕏', 'in', 'f', 'ig'].map((s) => (
                <li key={s}>
                  <span
                    aria-hidden
                    className="flex h-9 w-9 items-center justify-center rounded-card-sm bg-white/10 text-xs text-white/80"
                  >
                    {s}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <Column
            title="Properties"
            items={[
              { label: 'For Sale', href: '/dashboard' },
              { label: 'For Rent' },
              { label: 'Land & Plots', href: '/dashboard?property_type=land' },
              { label: 'Off-Plan' },
              { label: 'Shortlet' },
              { label: 'Commercial', href: '/dashboard?property_type=commercial' },
            ]}
          />

          <Column
            title="Company"
            items={[
              { label: 'About Us' },
              { label: 'How It Works' },
              { label: 'Financing', href: '/dashboard' },
              { label: 'Blog' },
              { label: 'Careers' },
              { label: 'Press' },
            ]}
          />

          <div>
            <Column
              title="Support"
              items={[
                { label: 'Help Center' },
                { label: 'FAQs' },
                { label: 'List a Property', href: '/register' },
                { label: 'Agent Registration', href: '/register' },
                { label: 'Report an Issue' },
              ]}
            />
            <div className="mt-8 flex flex-col gap-3">
              <a
                href="tel:+2349012345678"
                className="flex items-center gap-2 text-sm leading-5 text-white/60 transition hover:text-white"
              >
                ☏ +234 901 234 5678
              </a>
              <a
                href="mailto:hello@maihome.ng"
                className="flex items-center gap-2 text-sm leading-5 text-white/60 transition hover:text-white"
              >
                ✉ hello@maihome.ng
              </a>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-4 pt-8">
          <p className="text-sm leading-5 text-white/50">
            © 2026 Maiplot Technologies Ltd. All rights reserved.
          </p>
          <ul className="flex flex-wrap gap-6">
            {['Privacy Policy', 'Terms of Service', 'Cookie Policy', 'Sitemap'].map((l) => (
              <li key={l} className="text-xs leading-4 text-white/50">
                {l}
              </li>
            ))}
          </ul>
        </div>
      </Shell>
    </footer>
  );
}
