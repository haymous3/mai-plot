'use client';

import { useState } from 'react';

import { ChevronLeftIcon, ChevronRightIcon, StarIcon } from './icons';
import { pageCount, pageItems, stepPage } from '@/lib/carousel';

/**
 * Testimonials — node 627:746, rebuilt as the carousel the export draws
 * (SCRUM-178). SCRUM-174 shipped a static 3-up grid.
 *
 * This is the ONLY interactive element on the landing page, so it is the only
 * client component. Everything else stays server-rendered — the page is ISR'd
 * at `revalidate = 300` and shipping the whole thing to the client for one pair
 * of arrows would be a poor trade.
 *
 * Measured: section fill `surface-linen` (#f9f7f3); a 1024px track centred in
 * the 1216px container holding two 500px cards at a 24px gutter; cards 500×248
 * with a `border-line/50` hairline; controls 42px circles at y4976.
 *
 * ⚠️ The export draws FOUR pagination dots but only two cards, i.e. eight
 * testimonials, of which six were never written. Rather than invent six
 * customer quotes, this ships the export's two plus the two already in the
 * codebase — four over two pages. The dot count is derived from the data, so
 * adding the missing quotes later needs no code change.
 */

type Quote = { initials: string; name: string; role: string; quote: string };

const QUOTES: Quote[] = [
  {
    initials: 'CO',
    name: 'Chidinma Okafor',
    role: 'First-time Homeowner, Lagos',
    quote:
      'Maihomme made buying my Lekki duplex feel effortless. The verified documents gave me absolute peace of mind. I closed in six weeks.',
  },
  {
    initials: 'EN',
    name: 'Emeka Nwosu',
    role: 'Property Investor, Abuja',
    quote:
      'The financing feature alone is a game-changer. My partner bank approved 45% of the purchase price within three working days.',
  },
  {
    initials: 'AB',
    name: 'Adebayo Bello',
    role: 'Seller, Ikeja',
    quote:
      'I listed a distress sale on a Monday and had three serious offers by Friday. The escrow gave both sides confidence.',
  },
  {
    initials: 'FI',
    name: 'Fatima Ibrahim',
    role: 'Financed Buyer, Port Harcourt',
    quote:
      'The 50% financing was the difference between waiting two more years and moving into my own home this year.',
  },
];

const PER_PAGE = 2;

export function TestimonialCarousel() {
  const [page, setPage] = useState(0);
  const pages = pageCount(QUOTES.length, PER_PAGE);
  const shown = pageItems(QUOTES, page, PER_PAGE);

  return (
    <>
      {/* 1024px = two 500px cards plus the 24px gutter. The track is narrower
          than the 1216px container by design — it is centred, not stretched. */}
      <div className="mx-auto mt-16 grid max-w-[1024px] gap-6 md:grid-cols-2">
        {shown.map((q) => (
          <figure
            key={q.name}
            className="rounded-2xl border border-line/50 bg-surface-card p-8"
          >
            <div className="flex gap-1 text-status-gold" aria-label="Rated 5 out of 5">
              {Array.from({ length: 5 }, (_, i) => (
                <StarIcon key={i} className="h-4 w-4" />
              ))}
            </div>

            <blockquote className="mt-5 text-base italic leading-[26px] text-ink-700">
              &ldquo;{q.quote}&rdquo;
            </blockquote>

            <figcaption className="mt-7 flex items-center gap-4">
              <span
                aria-hidden
                className="flex h-12 w-12 flex-none items-center justify-center rounded-full bg-emerald-deep text-sm font-semibold text-white"
              >
                {q.initials}
              </span>
              <span>
                <span className="block text-[15px] font-bold leading-5 text-ink-buyer">
                  {q.name}
                </span>
                <span className="block text-sm leading-5 text-ink-500">{q.role}</span>
              </span>
            </figcaption>
          </figure>
        ))}
      </div>

      {pages > 1 && (
        <div className="mt-10 flex items-center justify-center gap-5">
          <CarouselButton label="Previous testimonials" onClick={() => setPage(stepPage(page, -1, pages))}>
            <ChevronLeftIcon className="h-4 w-4" />
          </CarouselButton>

          <div className="flex items-center gap-2">
            {Array.from({ length: pages }, (_, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setPage(i)}
                aria-label={`Go to testimonials page ${i + 1}`}
                aria-current={i === page}
                className={
                  i === page
                    ? 'h-1.5 w-7 rounded-full bg-emerald-deep'
                    : 'h-1.5 w-1.5 rounded-full bg-ink-300 transition hover:bg-ink-400'
                }
              />
            ))}
          </div>

          <CarouselButton label="Next testimonials" onClick={() => setPage(stepPage(page, 1, pages))}>
            <ChevronRightIcon className="h-4 w-4" />
          </CarouselButton>
        </div>
      )}
    </>
  );
}

function CarouselButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="flex h-[42px] w-[42px] items-center justify-center rounded-full border border-line-strong text-ink-700 transition hover:border-emerald-deep hover:text-emerald-deep"
    >
      {children}
    </button>
  );
}
