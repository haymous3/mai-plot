import type { Metadata } from 'next';
import Link from 'next/link';

import { Reveal } from './_components/reveal';
import { FeaturedCard } from './_landing/featured-card';
import { Footer } from './_landing/footer';
import { Hero } from './_landing/hero';
import { Nav } from './_landing/nav';
import { ArrowRightIcon } from './_landing/icons';
import {
  Categories,
  Financing,
  FinalCta,
  Process,
  Shell,
  Stats,
  Testimonials,
  TrustBar,
  WhyChooseUs,
} from './_landing/sections';
import type { FeedResponse } from '@/lib/api';
import { listingServiceUrl } from '@/lib/api';

export const metadata: Metadata = {
  title: 'Maihomme — verified property, financed and closed in under 60 days',
  description:
    "Nigeria's verified property marketplace. Browse checked listings, apply for up to 50% financing through partner banks, and close in under 60 days.",
};

// The feed is genuinely public: Kong's `listings-read` route (GET /listings)
// carries rate-limiting but no jwt plugin, and middleware only gates /admin/*.
// So this page fetches server-side with no session and stays unauthenticated.
export const revalidate = 300;

async function fetchFeatured() {
  try {
    const resp = await fetch(`${listingServiceUrl()}/listings?doc_status=verified&page_size=6`, {
      next: { revalidate: 300 },
    });
    if (!resp.ok) return [];
    const body = (await resp.json()) as FeedResponse;
    return body.data ?? [];
  } catch {
    // A marketing page must render even if the listing service is down — the
    // section drops out rather than failing the whole route.
    return [];
  }
}

export default async function HomePage() {
  const featured = await fetchFeatured();

  return (
    <main>
      {/*
        Arms the scroll animations (SCRUM-216).

        Every `[data-reveal]` hidden state in globals.css is scoped under
        `.motion-ready`, and this is the only thing that ever adds it. That
        makes the animations strictly additive: with JS disabled, broken, or
        still loading, the class is absent and the page renders exactly as it
        did before this ticket rather than as a blank screen.

        Inline and rendered FIRST on purpose — it executes while the browser is
        still parsing the sections below, so they are hidden before their first
        paint. Deferring it to a React effect would show every section, then
        hide it, then fade it back in.
      */}
      <script
        dangerouslySetInnerHTML={{
          __html: "document.documentElement.classList.add('motion-ready')",
        }}
      />

      {/* Rendered here rather than inside <Hero> (SCRUM-204) so `sticky` is
          bounded by the page, not by the hero section — and clear of that
          section's `overflow-hidden`, which would have disabled sticky. */}
      <Nav />
      <Hero featured={featured[0]} />

      <TrustBar />

      {/* Featured Listings — node 627:49, re-measured for SCRUM-178.
          Live data from the public feed; 389px columns at a 24px gutter.
          The eyebrow is gold (#c9a646), not emerald, and the heading breaks
          across two lines with the "View All" link baseline-aligned to the
          second one — hence `items-end`. */}
      {featured.length > 0 && (
        <section className="bg-surface-paper pb-24 pt-[104px]">
          <Shell>
            <Reveal className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.08em] text-status-gold">
                  Featured Listings
                </p>
                <h2 className="mt-4 font-display text-[32px] font-bold leading-[1.22] text-ink-buyer sm:text-[36px]">
                  Curated Properties
                  <span className="block">You&apos;ll Love</span>
                </h2>
              </div>
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-2 text-[15px] font-semibold text-emerald-deep hover:underline"
              >
                View All Properties
                <ArrowRightIcon className="h-4 w-4" />
              </Link>
            </Reveal>
            {/* `stagger` makes this Reveal the grid itself, so the cards arrive
                one after another without an extra wrapper element changing how
                the grid lays out. */}
            <Reveal stagger className="mt-16 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {featured.map((item) => (
                <FeaturedCard key={item.id} item={item} />
              ))}
            </Reveal>
          </Shell>
        </section>
      )}

      <WhyChooseUs />
      <Process />
      <Categories />
      <Testimonials />
      <Stats />
      {/* A different listing from the hero's, so the page does not show the
          same photograph twice; falls back to the first if the feed is short. */}
      <Financing
        photo={(featured[3] ?? featured[0])?.thumbnail_url}
        alt={(featured[3] ?? featured[0])?.title}
      />
      <FinalCta />
      <Footer />
    </main>
  );
}
