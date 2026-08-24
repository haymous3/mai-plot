import type { Metadata } from 'next';
import Link from 'next/link';

import { FeaturedCard } from './_landing/featured-card';
import { Footer } from './_landing/footer';
import { Hero } from './_landing/hero';
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
      <Hero featured={featured[0]} />

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
      <Footer />
    </main>
  );
}
