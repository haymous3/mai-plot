import Link from 'next/link';

import {
  ArrowRightIcon,
  BanknoteIcon,
  BuildingIcon,
  CheckCircleIcon,
  ChevronRightIcon,
  EyeIcon,
  FileTextIcon,
  HouseIcon,
  LockIcon,
  SearchIcon,
  ShieldIcon,
  TreeIcon,
  TrendingUpIcon,
  UsersIcon,
  WarehouseIcon,
} from './icons';
import { TestimonialCarousel } from './testimonials';

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
 * SCRUM-173, re-confirmed in SCRUM-178 and swept product-wide in SCRUM-186.
 * The copy below therefore diverges from the Figma text by design. The legal
 * entity ("Maiplot Technologies Ltd", in the footer) is a separate name and is
 * kept verbatim.
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
 * Browse By Category — node 627:646, re-measured.
 *
 * Six 189×150 tiles at a 16px gutter (6×189 + 5×16 = 1214, i.e. the 1216px
 * container), each centred with a 48px `surface-warm` icon chip. Tile fill is
 * `surface-paper` with a `border-line/50` hairline. SCRUM-174's tiles were
 * left-aligned with emoji and a different set of categories.
 *
 * ⚠️ THREE OF THE SIX HAVE NO FILTER BEHIND THEM. listing-service accepts
 * `property_type` of land | residential | commercial only (routes/listings.py
 * pattern), so Industrial, Off-Plan and Shortlet cannot be filtered for. Per
 * product decision they render as non-interactive tiles rather than linking
 * somewhere that silently ignores the category — the same rule the footer uses
 * for routes that do not exist.
 *
 * Counts are marketing figures from the design. There is no metrics endpoint
 * to source them from (analytics-service exposes only the audit log).
 */
export function Categories() {
  const cats: { label: string; count: string; Icon: typeof HouseIcon; q?: string }[] = [
    { label: 'Residential', count: '2,400+ listings', Icon: HouseIcon, q: 'residential' },
    { label: 'Commercial', count: '840+ listings', Icon: BuildingIcon, q: 'commercial' },
    { label: 'Land & Plots', count: '1,120+ listings', Icon: TreeIcon, q: 'land' },
    { label: 'Industrial', count: '310+ listings', Icon: WarehouseIcon },
    { label: 'Off-Plan', count: '680+ listings', Icon: TrendingUpIcon },
    { label: 'Shortlet', count: '920+ listings', Icon: UsersIcon },
  ];

  return (
    <section className="bg-surface-card pb-24 pt-[104px]">
      <Shell>
        <SectionHead eyebrow="Browse By Category" title="Find Your Property Type" />
        <div className="mt-14 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {cats.map(({ label, count, Icon, q }) => {
            const inner = (
              <>
                <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-surface-warm text-emerald-deep">
                  <Icon className="h-6 w-6" />
                </span>
                <span className="mt-4 text-[15px] font-semibold leading-5 text-ink-buyer">
                  {label}
                </span>
                <span className="mt-1 text-[13px] leading-5 text-ink-500">{count}</span>
              </>
            );
            const shell =
              'flex h-[150px] flex-col items-center justify-center rounded-2xl border border-line/50 bg-surface-paper p-4 text-center';
            return q ? (
              <Link
                key={label}
                href={`/dashboard?property_type=${q}`}
                className={`${shell} transition hover:border-emerald-deep/40`}
              >
                {inner}
              </Link>
            ) : (
              <div key={label} className={shell}>
                {inner}
              </div>
            );
          })}
        </div>
      </Shell>
    </section>
  );
}

/**
 * Testimonials — node 627:746. The carousel itself is a client component
 * (`testimonials.tsx`); this wrapper keeps the section chrome on the server.
 */
export function Testimonials() {
  return (
    <section className="bg-surface-linen pb-24 pt-[104px]">
      <Shell>
        <SectionHead eyebrow="Testimonials" title="Stories From Happy Homeowners" />
        <TestimonialCarousel />
      </Shell>
    </section>
  );
}

/**
 * Stats bar — node 627:832, re-measured.
 *
 * A plain white band, not the rule-bounded one SCRUM-174 shipped, with the
 * four figures centred rather than left-aligned. Values measured at 48px
 * (digit height 35px / 0.727) in `emerald-deep`, labels 16px `ink-500`.
 *
 * The fourth figure is "14 / Partner Banks" in the export, not the
 * "₦48B+ / Transacted Value" previously shipped, and the third reads "Happy
 * Homeowners" rather than "Happy Nigerians".
 *
 * These are marketing figures taken from the design. There is no metrics
 * endpoint to source them from — analytics-service exposes only the admin
 * audit log — so they are hardcoded until one exists.
 */
export function Stats() {
  const stats = [
    { value: '4,200+', label: 'Properties Sold' },
    { value: '12,800+', label: 'Verified Listings' },
    { value: '9,600+', label: 'Happy Homeowners' },
    { value: '14', label: 'Partner Banks' },
  ];
  return (
    <section className="bg-surface-card py-20">
      <Shell>
        <dl className="grid grid-cols-2 gap-10 lg:grid-cols-4">
          {stats.map((s) => (
            <div key={s.label} className="text-center">
              <dd className="text-[40px] font-bold leading-none text-emerald-deep sm:text-5xl">
                {s.value}
              </dd>
              <dt className="mt-5 text-base leading-6 text-ink-500">{s.label}</dt>
            </div>
          ))}
        </dl>
      </Shell>
    </section>
  );
}

/**
 * Property Financing — node 627:868, rebuilt.
 *
 * Image left, copy right — not the filled emerald card SCRUM-174 shipped. The
 * split is exact: 576 + 64 + 576 = 1216, so it is a plain two-column grid at a
 * 64px gutter rather than a fractional split.
 *
 * The 50% badge overhangs the photo's bottom-right corner by 24px on both
 * axes, mirroring the hero's overlay composition.
 *
 * ⚠️ NO IMAGE ASSET EXISTS. Like the hero, this renders a real listing photo
 * from the feed rather than a stock file; with no feed it degrades to a flat
 * tint. The badge is static because 50% is a business rule (CLAUDE.md §8.5).
 */
export function Financing({ photo, alt }: { photo?: string | null; alt?: string }) {
  const points = [
    'Up to 50% of purchase price financed',
    'Competitive mortgage rates from partner banks',
    'Apply in minutes, decision in 72 hours',
    'No hidden charges or processing surprises',
  ];
  return (
    <section id="financing" className="bg-surface-paper pb-24 pt-[104px]">
      <Shell className="grid items-center gap-y-16 lg:grid-cols-2 lg:gap-x-16">
        <div className="relative">
          <div className="h-[416px] w-full overflow-hidden rounded-2xl bg-emerald-deep/10 shadow-lg">
            {photo && (
              // eslint-disable-next-line @next/next/no-img-element -- listing media is an external CDN URL
              <img src={photo} alt={alt ?? ''} className="h-full w-full object-cover" />
            )}
          </div>
          <div className="absolute bottom-4 right-4 w-[130px] rounded-2xl bg-emerald-deep px-5 py-5 text-white shadow-xl lg:-bottom-6 lg:-right-6">
            <p className="text-[28px] font-bold leading-9">50%</p>
            <p className="mt-1 text-sm leading-5 text-white/75">Financing Available</p>
            <span aria-hidden className="mt-3 block h-1 w-7 rounded-full bg-status-gold" />
          </div>
        </div>

        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.08em] text-status-gold">
            Property Financing
          </p>
          {/*
            34px here, not the 36px the other section headings use. This is the
            page's longest heading and the design fits it on two lines in a
            576px column — but the design is set in Inter and the app renders
            Fraunces, which is wider, so at 36px "Banks." falls to a third line
            and the two-line composition is lost. 2px is imperceptible; the
            wrap is not.
          */}
          <h2 className="mt-4 font-display text-[30px] font-bold leading-[1.22] text-ink-buyer sm:text-[34px]">
            Your Home, Our Financing.
            <span className="block">Up to 50% Through Partner Banks.</span>
          </h2>
          <p className="mt-5 text-lg leading-7 text-ink-500">
            Don&apos;t let capital stop your property dream. Maihomme partners with 14 CBN-licensed
            banks to give you access to competitive mortgage financing — applied directly from your
            dashboard, with decisions in as little as 72 hours.
          </p>
          <ul className="mt-8 flex flex-col gap-4">
            {points.map((p) => (
              <li key={p} className="flex items-center gap-3 text-[15px] leading-5 text-ink-700">
                <CheckCircleIcon className="h-5 w-5 flex-none text-emerald-deep" />
                {p}
              </li>
            ))}
          </ul>
          <Link
            href="/dashboard"
            className="mt-10 inline-flex h-[52px] items-center gap-2.5 rounded-xl bg-emerald-deep px-7 text-base font-semibold text-white transition hover:brightness-110"
          >
            Check Financing Eligibility
            <ArrowRightIcon className="h-5 w-5" />
          </Link>
        </div>
      </Shell>
    </section>
  );
}

/**
 * Final CTA — node 627:941, rebuilt.
 *
 * An inset 960×460 `emerald-deep` card on a white section, not the flat
 * full-width band SCRUM-174 shipped.
 *
 * The two decorative circles are measured, not eyeballed. Fitting three
 * boundary samples of the top-right one gives centre (1205, 6167) radius 128 —
 * i.e. a 256px circle whose centre sits on the card's top edge, 63px in from
 * the right corner, which is what the offsets below encode. The fill is
 * `white/10` (measured #275439 over #0f3d2e).
 */
export function FinalCta() {
  return (
    <section className="bg-surface-card pb-24 pt-[104px]">
      <Shell>
        <div className="relative mx-auto max-w-[960px] overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-deep to-[#154937] px-8 py-20 text-center">
          <span
            aria-hidden
            className="pointer-events-none absolute -right-16 -top-32 h-64 w-64 rounded-full bg-white/10"
          />
          <span
            aria-hidden
            className="pointer-events-none absolute -bottom-32 -left-20 h-60 w-60 rounded-full bg-white/10"
          />

          <div className="relative">
            <p className="text-sm font-semibold uppercase tracking-[0.08em] text-status-gold">
              Start Today
            </p>
            <h2 className="mt-4 font-display text-[32px] font-bold leading-[1.22] text-white sm:text-[40px]">
              Your Property Journey
              <span className="block">Starts Here</span>
            </h2>
            <p className="mx-auto mt-6 max-w-xl text-lg leading-7 text-white/75">
              Join over 9,600 Nigerians who have found, financed, and secured their dream properties
              through Maihomme.
            </p>
            <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
              <Link
                href="/dashboard"
                className="inline-flex h-14 items-center gap-2.5 rounded-xl bg-status-gold px-7 text-base font-semibold text-white transition hover:brightness-105"
              >
                <SearchIcon className="h-5 w-5" />
                Explore Properties
              </Link>
              <Link
                href="/register"
                className="inline-flex h-14 items-center gap-2.5 rounded-xl border border-white/20 bg-white/10 px-7 text-base font-semibold text-white transition hover:bg-white/15"
              >
                <HouseIcon className="h-5 w-5" />
                List Your Property
              </Link>
            </div>
          </div>
        </div>
      </Shell>
    </section>
  );
}
