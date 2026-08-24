import Link from 'next/link';

import {
  ArrowRightIcon,
  BanknoteIcon,
  ChevronRightIcon,
  EyeIcon,
  FileTextIcon,
  LockIcon,
  ShieldIcon,
} from './icons';

/**
 * Static sections of the public landing page — Figma nodes 627:9 through
 * 627:941, re-measured against the SCRUM-178 export.
 *
 * Layout: a 1280px container (centred, 180px side margins at the 1577px
 * artboard width) with 32px inner padding, giving 1216px of content. Every
 * card grid on the page is 389px columns at a 24px gutter.
 *
 * COPY: the Figma text reads "MaiHome" throughout. Per product decision the
 * landing page uses "Maihomme", matching the buyer sidebar shipped in
 * SCRUM-173 and re-confirmed in SCRUM-178. The copy below therefore diverges
 * from the Figma text by design. The legal entity ("Maiplot Technologies Ltd",
 * in the footer) is a separate name and is kept verbatim.
 */

/** 1280px container with 32px inner padding — the landing page's own layout. */
export function Shell({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`mx-auto w-full max-w-[1280px] px-8 ${className}`}>{children}</div>
  );
}

/**
 * Eyebrow + heading pair used at the top of every section.
 *
 * Measured: eyebrow 14px semibold uppercase in `status-gold` at ~0.08em
 * tracking; heading 36px/44px serif in `ink-buyer` (#1a1a1a); sub 18px/28px
 * `ink-500` (#6b7280).
 *
 * Every section that carries one centres it — Featured Listings is the only
 * left-aligned case, because its "View All" link occupies the right of the row.
 */
function SectionHead({
  eyebrow,
  title,
  sub,
  align = 'center',
  tone = 'light',
}: {
  eyebrow: string;
  title: React.ReactNode;
  sub?: string;
  align?: 'left' | 'center';
  tone?: 'light' | 'dark';
}) {
  return (
    <div className={align === 'center' ? 'mx-auto max-w-3xl text-center' : 'max-w-3xl'}>
      <p className="text-sm font-semibold uppercase tracking-[0.08em] text-status-gold">
        {eyebrow}
      </p>
      <h2
        className={`mt-4 font-display text-[32px] font-bold leading-[1.22] sm:text-[36px] ${
          tone === 'dark' ? 'text-white' : 'text-ink-buyer'
        }`}
      >
        {title}
      </h2>
      {sub && (
        <p className={`mt-5 text-lg leading-7 ${tone === 'dark' ? 'text-white/70' : 'text-ink-500'}`}>
          {sub}
        </p>
      )}
    </div>
  );
}

/**
 * Trust bar — node 627:9, re-measured.
 *
 * Eight banks, not the four SCRUM-174 shipped, and each sits in a pill rather
 * than being bare text. Measured: pills 44px tall, 12px radius, `surface-paper`
 * fill, 48px column gap, 24px row gap, 15px semibold `ink-500` label.
 *
 * Pill widths run 128-139px. That is NOT a 7-column grid — that would make them
 * all 133 — but content width against a 128px floor: every measured pill
 * matches `min-w-[128px] px-6` to within 3px.
 *
 * Seven fit the 1216px container and the eighth wraps and centres, which
 * `flex-wrap justify-center` reproduces without hard-coding the break.
 *
 * White, with no top rule: the hero's curved edge is a white shape, so any
 * other fill here would show as a band under the curve.
 */
export function TrustBar() {
  const banks = [
    'Access Bank',
    'GTBank',
    'Zenith Bank',
    'First Bank',
    'UBA',
    'Stanbic IBTC',
    'FCMB',
    'Fidelity Bank',
  ];
  return (
    <section className="bg-surface-card pb-16 pt-[72px]">
      <Shell>
        <p className="text-center text-sm font-semibold uppercase tracking-[0.08em] text-ink-500">
          Trusted by leading Nigerian banks &amp; institutions
        </p>
        <ul className="mt-12 flex flex-wrap items-center justify-center gap-x-12 gap-y-6">
          {banks.map((b) => (
            <li
              key={b}
              className="flex h-11 min-w-[128px] items-center justify-center rounded-xl bg-surface-paper px-6 text-[15px] font-semibold text-ink-500"
            >
              {b}
            </li>
          ))}
        </ul>
      </Shell>
    </section>
  );
}

/**
 * Why Choose Us — node 627:465, re-measured.
 *
 * FIVE cards on a 3-column grid, not the three SCRUM-174 shipped, and the
 * header is centred rather than left-aligned. Cards 1 and 5 are filled
 * `emerald-deep`; the rest are white with a `border-line/50` hairline — the
 * same 50%-opacity border the buyer surface uses (SCRUM-169), measured here as
 * #f2f2f2 against white, which is exactly #e5e7eb at half opacity.
 *
 * Icon chips are 48x48 at a 12px radius. On the dark cards `white/15` with a
 * gold glyph (measured #335a4d fill, #c9a646 glyph); on the light cards
 * `surface-warm` with an `emerald-deep` glyph (#f5f1e8 / #0f3d2e).
 */
export function WhyChooseUs() {
  const pillars = [
    {
      Icon: FileTextIcon,
      title: 'Verified Documents',
      body: 'Every title deed, survey plan, and consent letter is authenticated by our legal team before listing.',
      dark: true,
    },
    {
      Icon: EyeIcon,
      title: 'Realtor Inspections',
      body: 'Certified agents conduct physical inspections and file detailed condition reports on every property.',
      dark: false,
    },
    {
      Icon: LockIcon,
      title: 'Secure Escrow',
      body: 'Funds are held in a CBN-licensed escrow account until all conditions of sale are satisfied.',
      dark: false,
    },
    {
      Icon: BanknoteIcon,
      title: 'Property Financing',
      body: 'Access up to 50% financing through our partner banks with competitive mortgage rates.',
      dark: false,
    },
    {
      Icon: ShieldIcon,
      title: 'Transparent Transactions',
      body: 'Track every stage of your deal in real time — no hidden fees, no surprises.',
      dark: true,
    },
  ];
  return (
    <section className="bg-surface-card pb-24 pt-[104px]">
      <Shell>
        <SectionHead
          eyebrow="Why Choose Us"
          title="Built on Trust, Powered by Technology"
          sub="We combine rigorous verification, bank-grade escrow, and smart financing to give every Nigerian a fair shot at property ownership."
        />
        <div className="mt-16 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {pillars.map(({ Icon, title, body, dark }) => (
            <div
              key={title}
              className={`rounded-2xl p-8 ${
                dark ? 'bg-emerald-deep' : 'border border-line/50 bg-surface-card'
              }`}
            >
              <span
                className={`flex h-12 w-12 items-center justify-center rounded-xl ${
                  dark ? 'bg-white/15 text-status-gold' : 'bg-surface-warm text-emerald-deep'
                }`}
              >
                <Icon className="h-6 w-6" />
              </span>
              <h3
                className={`mt-6 text-lg font-semibold leading-7 ${
                  dark ? 'text-white' : 'text-ink-buyer'
                }`}
              >
                {title}
              </h3>
              <p className={`mt-3 text-[15px] leading-6 ${dark ? 'text-white/70' : 'text-ink-500'}`}>
                {body}
              </p>
            </div>
          ))}
        </div>
      </Shell>
    </section>
  );
}

/**
 * The Process — node 627:550, re-measured.
 *
 * Full-bleed `emerald-deep`, not the light band SCRUM-174 shipped, and the five
 * steps are connected chips rather than a plain numbered list. It also has a
 * call to action the previous build omitted entirely.
 *
 * Measured: chips 78x78 at a 12px radius, `white/10` fill, on a 243.2px pitch
 * — which is exactly the 1216px container divided by five, so this is a plain
 * `grid-cols-5` with the chip centred in each cell, not a flex row with a
 * computed gap.
 *
 * The connector is a 1px `white/15` rule at the chip's vertical centre with a
 * chevron at the midpoint between chips. It is drawn per-cell rather than as
 * one line behind the row because the chips are translucent — a line running
 * behind them would show through.
 */
export function Process() {
  const steps = [
    {
      n: '01',
      title: 'Discover',
      body: 'Browse thousands of verified listings across Nigeria filtered by location, budget, and property type.',
    },
    {
      n: '02',
      title: 'Verify',
      body: 'Review authenticated documents, inspection reports, and title information before you commit.',
    },
    {
      n: '03',
      title: 'Make an Offer',
      body: 'Submit a binding offer through our secure platform. Sellers respond within 48 hours.',
    },
    {
      n: '04',
      title: 'Finance',
      body: 'Apply for mortgage financing through a partner bank directly from your Maihomme dashboard.',
    },
    {
      n: '05',
      title: 'Secure Ownership',
      body: 'Funds are released from escrow and title is transferred upon completion of all legal requirements.',
    },
  ];
  return (
    <section id="how-it-works" className="bg-emerald-deep pb-24 pt-[104px]">
      <Shell>
        <SectionHead
          eyebrow="The Process"
          title={
            <>
              From Search to Ownership
              <span className="block">in Five Steps</span>
            </>
          }
          tone="dark"
        />

        <ol className="mt-16 grid gap-y-10 sm:grid-cols-2 lg:grid-cols-5 lg:gap-y-0">
          {steps.map((s, i) => (
            <li key={s.n} className="relative flex flex-col items-center text-center">
              {i < steps.length - 1 && (
                <>
                  {/* Runs from this chip's right edge (half a cell plus half a
                      78px chip) to the next chip's left edge — one cell wide
                      less one chip. Hidden below lg, where the steps stack. */}
                  <span
                    aria-hidden
                    className="absolute left-[calc(50%+39px)] top-[39px] hidden h-px w-[calc(100%-78px)] bg-white/15 lg:block"
                  />
                  <ChevronRightIcon className="absolute left-full top-[39px] hidden h-4 w-4 -translate-x-1/2 -translate-y-1/2 text-white/40 lg:block" />
                </>
              )}

              <span className="relative flex h-[78px] w-[78px] flex-col items-center justify-center rounded-xl bg-white/10 px-2">
                <span className="text-xs font-semibold leading-4 text-status-gold">{s.n}</span>
                <span className="mt-0.5 text-sm font-bold leading-[18px] text-white">{s.title}</span>
              </span>

              <p className="mt-6 max-w-[196px] text-sm leading-[22px] text-white/70">{s.body}</p>
            </li>
          ))}
        </ol>

        <div className="mt-14 flex justify-center">
          <Link
            href="/register"
            className="inline-flex h-[52px] items-center gap-2.5 rounded-xl bg-status-gold px-7 text-base font-semibold text-white transition hover:brightness-105"
          >
            Start Your Journey
            <ArrowRightIcon className="h-5 w-5" />
          </Link>
        </div>
      </Shell>
    </section>
  );
}

/**
 * Browse By Category — node 627:646. Six 189×154 tiles at a 16px gap.
 * Counts are marketing figures from the design; there is no metrics endpoint
 * (analytics-service exposes only the audit log), so they are static.
 *
 * PR 3 of SCRUM-178 rebuilds this against the new export.
 */
export function Categories() {
  const cats = [
    { label: 'Residential', count: '2,400+ listings', icon: '🏠', q: 'residential' },
    { label: 'Commercial', count: '1,100+ listings', icon: '🏢', q: 'commercial' },
    { label: 'Land', count: '3,800+ listings', icon: '🌍', q: 'land' },
    { label: 'Duplexes', count: '900+ listings', icon: '🏘', q: 'residential' },
    { label: 'Apartments', count: '1,600+ listings', icon: '🏬', q: 'residential' },
    { label: 'Distress Sales', count: '450+ listings', icon: '🔥', q: '' },
  ];
  return (
    <section className="py-24">
      <Shell>
        <SectionHead eyebrow="Browse By Category" title="Find Your Property Type" />
        <div className="mt-14 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {cats.map((c) => (
            <Link
              key={c.label}
              href={c.q ? `/dashboard?property_type=${c.q}` : '/dashboard?sale_type=distress'}
              className="flex h-[154px] flex-col justify-center rounded-2xl border border-line bg-surface-card p-5 transition hover:border-emerald-deep/40"
            >
              <span aria-hidden className="text-2xl">
                {c.icon}
              </span>
              <span className="mt-3 text-sm font-semibold text-ink-buyer">{c.label}</span>
              <span className="mt-1 text-xs text-ink-500">{c.count}</span>
            </Link>
          ))}
        </div>
      </Shell>
    </section>
  );
}

/** Testimonials — node 627:746. PR 3 of SCRUM-178 rebuilds this as a carousel. */
export function Testimonials() {
  const quotes = [
    {
      initials: 'CO',
      name: 'Chidinma Okafor',
      role: 'Bought in Lekki',
      quote: 'Maihomme made buying my Lekki duplex feel effortless. Every document was verified before I ever saw the property.',
    },
    {
      initials: 'AB',
      name: 'Adebayo Bello',
      role: 'Sold in Ikeja',
      quote: 'I listed a distress sale on a Monday and had three serious offers by Friday. The escrow gave both sides confidence.',
    },
    {
      initials: 'FI',
      name: 'Fatima Ibrahim',
      role: 'Financed through a partner bank',
      quote: 'The 50% financing was the difference between waiting two more years and moving in this year.',
    },
  ];
  return (
    <section className="bg-surface-page py-24">
      <Shell>
        <SectionHead eyebrow="Testimonials" title="Stories From Happy Homeowners" />
        <div className="mt-16 grid gap-6 md:grid-cols-3">
          {quotes.map((q) => (
            <figure key={q.name} className="rounded-2xl border border-line bg-surface-card p-8">
              <blockquote className="text-base leading-7 text-ink-700">“{q.quote}”</blockquote>
              <figcaption className="mt-6 flex items-center gap-3">
                <span
                  aria-hidden
                  className="flex h-10 w-10 flex-none items-center justify-center rounded-full bg-emerald-deep text-sm font-semibold text-white"
                >
                  {q.initials}
                </span>
                <span>
                  <span className="block text-sm font-semibold text-ink-buyer">{q.name}</span>
                  <span className="block text-xs text-ink-500">{q.role}</span>
                </span>
              </figcaption>
            </figure>
          ))}
        </div>
      </Shell>
    </section>
  );
}

/**
 * Stats bar — node 627:832. PR 3 of SCRUM-178 re-measures this.
 *
 * These are marketing figures taken from the design. There is no metrics
 * endpoint to source them from — analytics-service exposes only the admin
 * audit log — so they are hardcoded until one exists.
 */
export function Stats() {
  const stats = [
    { value: '4,200+', label: 'Properties Sold' },
    { value: '12,800+', label: 'Verified Listings' },
    { value: '9,600+', label: 'Happy Nigerians' },
    { value: '₦48B+', label: 'Transacted Value' },
  ];
  return (
    <section className="border-y border-line py-20">
      <Shell>
        <dl className="grid grid-cols-2 gap-12 lg:grid-cols-4">
          {stats.map((s) => (
            <div key={s.label}>
              <dt className="sr-only">{s.label}</dt>
              <dd>
                <span className="block font-display text-4xl font-bold text-emerald-deep">
                  {s.value}
                </span>
                <span className="mt-1 block text-sm text-ink-500">{s.label}</span>
              </dd>
            </div>
          ))}
        </dl>
      </Shell>
    </section>
  );
}

/** Property Financing — node 627:868. PR 3 of SCRUM-178 rebuilds this. */
export function Financing() {
  return (
    <section id="financing" className="py-24">
      <Shell>
        <div className="grid items-center gap-12 rounded-2xl bg-emerald-deep p-12 text-white lg:grid-cols-[1fr_320px]">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-white/70">
              Property Financing
            </p>
            <h2 className="mt-3 font-display text-3xl font-bold leading-10 sm:text-4xl">
              Your Home, Our Financing. Up to 50% Through Partner Banks.
            </h2>
            <p className="mt-4 max-w-2xl text-base leading-7 text-white/80">
              Don&apos;t let capital stop your property dream. Maihomme works with CBN-licensed
              partner banks to finance up to half your purchase, with the title held as collateral
              until repayment completes.
            </p>
            <Link
              href="/dashboard"
              className="mt-8 inline-flex h-12 items-center rounded-xl bg-white px-6 text-sm font-semibold text-emerald-deep transition hover:bg-bone"
            >
              Explore Financing
            </Link>
          </div>
          <div className="rounded-2xl bg-white/10 p-8 text-center">
            <span className="block font-display text-6xl font-bold">50%</span>
            <span className="mt-2 block text-sm text-white/80">Financing Available</span>
          </div>
        </div>
      </Shell>
    </section>
  );
}

/** Final CTA — node 627:941. PR 3 of SCRUM-178 rebuilds this. */
export function FinalCta() {
  return (
    <section className="bg-surface-page py-24">
      <Shell className="text-center">
        <p className="text-sm font-semibold uppercase tracking-wide text-emerald-deep">
          Start Today
        </p>
        <h2 className="mt-3 font-display text-3xl font-bold leading-10 text-ink-buyer sm:text-4xl">
          Your Property Journey Starts Here
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-base leading-7 text-ink-500">
          Join over 9,600 Nigerians who have found, financed and closed on property through
          Maihomme.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
          <Link
            href="/dashboard"
            className="inline-flex h-12 items-center rounded-xl bg-emerald-deep px-6 text-sm font-semibold text-white transition hover:brightness-95"
          >
            Explore Properties
          </Link>
          <Link
            href="/register"
            className="inline-flex h-12 items-center rounded-xl border border-line-strong px-6 text-sm font-semibold text-ink-700 transition hover:border-emerald-deep"
          >
            List Your Property
          </Link>
        </div>
      </Shell>
    </section>
  );
}
