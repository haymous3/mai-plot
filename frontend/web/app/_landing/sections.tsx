import Link from 'next/link';

/**
 * Static sections of the public landing page — Figma nodes 627:9 through
 * 627:941. The artboard is 1:1, so values are literal.
 *
 * Layout: a 1280px container (centred, 148px side margins at the 1577px
 * artboard width) with 32px inner padding, giving 1216px of content.
 *
 * COPY: the Figma text reads "MaiHome" in three places and "Maiplot" in two.
 * Per product decision (SCRUM-174) the landing page uses "Maihomme" throughout,
 * matching the buyer sidebar shipped in SCRUM-173. The copy below therefore
 * diverges from the Figma text by design.
 */

/** 1280px container with 32px inner padding — the landing page's own layout. */
export function Shell({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`mx-auto w-full max-w-[1280px] px-8 ${className}`}>{children}</div>
  );
}

/** Eyebrow + heading pair used at the top of most sections. */
function SectionHead({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="max-w-3xl">
      <p className="text-sm font-semibold uppercase tracking-wide text-emerald-deep">{eyebrow}</p>
      <h2 className="mt-3 font-display text-3xl font-bold leading-10 text-ink-buyer sm:text-4xl">
        {title}
      </h2>
      {sub && <p className="mt-4 text-base leading-7 text-ink-500">{sub}</p>}
    </div>
  );
}

/** Trust bar — node 627:9. */
export function TrustBar() {
  const banks = ['Access Bank', 'GTBank', 'Zenith Bank', 'First Bank'];
  return (
    // White, and no top rule: the hero's curved edge (HeroWave) is a white
    // shape, so anything but white here would show as a band under the curve.
    // The pill treatment lands in PR 2 of SCRUM-178.
    <section className="bg-surface-card py-12">
      <Shell>
        <p className="text-center text-sm text-ink-500">
          Trusted by leading Nigerian banks &amp; institutions
        </p>
        <ul className="mt-6 flex flex-wrap items-center justify-center gap-x-12 gap-y-4">
          {banks.map((b) => (
            <li key={b} className="text-lg font-semibold text-ink-400">
              {b}
            </li>
          ))}
        </ul>
      </Shell>
    </section>
  );
}

/** Why Choose Us — node 627:465. */
export function WhyChooseUs() {
  const pillars = [
    {
      icon: '🛡',
      title: 'Verified Documents',
      body: 'Every title deed, survey plan and consent letter is checked by our legal team before a listing goes live.',
    },
    {
      icon: '🏦',
      title: 'Bank-Grade Escrow',
      body: 'Funds sit in a CBN-licensed escrow account and are only released once title transfer is confirmed.',
    },
    {
      icon: '⚡',
      title: 'Under 60 Days',
      body: 'Verification, financing and transfer run in parallel, cutting a six-month process to under two months.',
    },
  ];
  return (
    <section className="py-24">
      <Shell>
        <SectionHead
          eyebrow="Why Choose Us"
          title="Built on Trust, Powered by Technology"
          sub="We combine rigorous verification, bank-grade escrow and a transparent process so you always know where your money and your paperwork stand."
        />
        <div className="mt-16 grid gap-6 md:grid-cols-3">
          {pillars.map((p) => (
            <div key={p.title} className="rounded-2xl border border-line bg-surface-card p-8">
              <span
                aria-hidden
                className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-deep/[0.08] text-xl"
              >
                {p.icon}
              </span>
              <h3 className="mt-6 text-lg font-semibold text-ink-buyer">{p.title}</h3>
              <p className="mt-2 text-sm leading-6 text-ink-500">{p.body}</p>
            </div>
          ))}
        </div>
      </Shell>
    </section>
  );
}

/** The Process — node 627:550. Five numbered steps. */
export function Process() {
  const steps = [
    { n: '01', title: 'Discover', body: 'Browse thousands of verified listings across Nigeria.' },
    { n: '02', title: 'Inspect', body: 'A licensed realtor visits and reports back with photos and GPS proof.' },
    { n: '03', title: 'Offer', body: 'Make an offer. Accepted offers lock the listing for 72 hours.' },
    { n: '04', title: 'Finance', body: 'Apply for up to 50% of the price through a partner bank.' },
    { n: '05', title: 'Own', body: 'Funds clear from escrow and the title transfers to your name.' },
  ];
  return (
    <section className="bg-surface-page py-24">
      <Shell>
        <SectionHead eyebrow="The Process" title="From Search to Ownership in Five Steps" />
        <ol className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-5">
          {steps.map((s) => (
            <li key={s.n}>
              <span className="font-display text-3xl font-bold text-emerald-deep/30">{s.n}</span>
              <h3 className="mt-3 text-lg font-semibold text-ink-buyer">{s.title}</h3>
              <p className="mt-2 text-sm leading-6 text-ink-500">{s.body}</p>
            </li>
          ))}
        </ol>
      </Shell>
    </section>
  );
}

/**
 * Browse By Category — node 627:646. Six 189×154 tiles at a 16px gap.
 * Counts are marketing figures from the design; there is no metrics endpoint
 * (analytics-service exposes only the audit log), so they are static.
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

/** Testimonials — node 627:746. Copy rewritten from "MaiHome" to "Maihomme". */
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
 * Stats bar — node 627:832. Four 268×80 blocks at a 48px gap.
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

/** Property Financing — node 627:868. Copy rewritten to "Maihomme". */
export function Financing() {
  return (
    <section className="py-24">
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

/** Final CTA — node 627:941. */
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
