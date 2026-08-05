import type { Metadata } from 'next';
import Link from 'next/link';

import { FeaturedCard } from './_landing/featured-card';
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
        TEMPORARY HERO.

        The hero is NOT designed — Figma node 627:8 "Placeholder for App" is
        1577x944 with no children, i.e. the entire above-the-fold is an empty
        placeholder. Everything below this block comes from the design
        (nodes 627:9 … 627:941).

        Per product decision (SCRUM-174) this is a deliberately minimal stand-in
        rather than an invented hero, so it can be replaced wholesale once the
        real one exists. Do not build on it.
      */}
      <section className="bg-emerald-deep py-24 text-white">
        <Shell>
          <span className="font-display text-xl font-bold tracking-tight">Maihomme</span>
          <h1 className="mt-8 max-w-4xl font-display text-4xl font-bold leading-tight sm:text-5xl">
            Verified property. Financed and closed in under 60 days.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-white/80">
            Every listing document-checked before it goes live. Up to 50% financing through
            CBN-licensed partner banks, with funds held in escrow until title transfers.
          </p>
          <div className="mt-10 flex flex-wrap gap-4">
            <Link
              href="/dashboard"
              className="inline-flex h-12 items-center rounded-xl bg-white px-6 text-sm font-semibold text-emerald-deep transition hover:bg-bone"
            >
              Explore Properties
            </Link>
            <Link
              href="/register"
              className="inline-flex h-12 items-center rounded-xl border border-white/30 px-6 text-sm font-semibold text-white transition hover:border-white"
            >
              List Your Property
            </Link>
          </div>
        </Shell>
      </section>

      <TrustBar />

      {/* Featured Listings — node 627:49. Live data from the public feed;
          3-up grid of 389x383 cards at a 24px gap. */}
      {featured.length > 0 && (
        <section className="py-24">
          <Shell>
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-sm font-semibold uppercase tracking-wide text-emerald-deep">
                  Featured Listings
                </p>
                <h2 className="mt-3 font-display text-3xl font-bold leading-10 text-ink-buyer sm:text-4xl">
                  Curated Properties You&apos;ll Love
                </h2>
              </div>
              <Link
                href="/dashboard"
                className="text-sm font-semibold text-emerald-deep hover:underline"
              >
                View All Properties →
              </Link>
            </div>
            <div className="mt-14 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {featured.map((item) => (
                <FeaturedCard key={item.id} item={item} />
              ))}
            </div>
          </Shell>
        </section>
      )}

      <WhyChooseUs />
      <Process />
      <Categories />
      <Testimonials />
      <Stats />
      <Financing />
      <FinalCta />
    </main>
  );
}
