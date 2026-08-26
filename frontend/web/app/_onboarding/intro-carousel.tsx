'use client';

import { useState } from 'react';

import { BanknoteIcon, ChevronRightIcon, HouseIcon, ShieldCheckIcon } from './icons';
import { PrimaryButton } from './ui';

/**
 * Three-slide intro carousel — `design/onboarding/onboarding-{1,2,3}.png`.
 *
 * SCRUM-132 shipped this with the right copy but placeholder presentation (a
 * slide number in a small box). The exports give it a real illustration chip
 * and layout.
 *
 * Measured (1577 artboard, 1:1):
 *   icon chip   192×192, 24px radius, glyph ~72px
 *   slides 1-2  `surface-tint` chip, `emerald-deep` glyph
 *   slide 3     `surface-gold` chip, `status-gold` glyph — the financing slide
 *               is the only one that changes colour
 *   title       34px bold, body 18px `ink-500`
 *   dots        active 48×10 pill, inactive 10px circles at `emerald-deep/20`
 *               (that alpha composites to exactly the measured #cfd8d5)
 *   button      384×68, i.e. half the 768 column — the only CTA in these flows
 *               that is not full width
 *
 * Skip and the final "Get Started" both land on the same place, so a user who
 * skips is not penalised — the carousel is pure marketing and carries no state.
 */

const SLIDES = [
  {
    Icon: HouseIcon,
    title: 'Access Distress & Premium Property Deals',
    body: 'From value deals to prime locations, buyers explore verified options, sellers connect with serious buyers',
    gold: false,
  },
  {
    Icon: ShieldCheckIcon,
    title: 'Verified Documents & Listings',
    body: 'Every property is thoroughly vetted, transparency for buyers, credibility for sellers',
    gold: false,
  },
  {
    Icon: BanknoteIcon,
    title: 'Get Financing in Days',
    body: 'Buyers access loans up to 50% of property value, sellers get paid faster with approved buyers',
    gold: true,
  },
];

export function IntroCarousel({ onDone }: { onDone: () => void }) {
  const [i, setI] = useState(0);
  const slide = SLIDES[i];
  const last = i === SLIDES.length - 1;

  return (
    <div className="flex w-full flex-1 flex-col">
      {/* Anchored to the viewport, not the 768px column: the export puts Skip
          at x1489-1521 of 1577, ~56px from the page edge. */}
      <button
        type="button"
        onClick={onDone}
        className="absolute right-6 top-10 rounded-lg px-2 py-1 text-[15px] font-semibold text-ink-500 transition hover:text-ink-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-deep sm:right-14"
      >
        Skip
      </button>

      <div className="flex flex-1 flex-col items-center justify-center text-center">
        <span
          className={`flex h-[192px] w-[192px] items-center justify-center rounded-3xl ${
            slide.gold ? 'bg-surface-gold text-status-gold' : 'bg-surface-tint text-emerald-deep'
          }`}
        >
          <slide.Icon className="h-[72px] w-[72px]" strokeWidth={1.7} />
        </span>

        <h1 className="mt-12 max-w-[760px] text-[26px] font-bold leading-[1.2] text-ink-buyer sm:text-[36px]">
          {slide.title}
        </h1>
        <p className="mt-4 max-w-[560px] text-[19px] leading-[26px] text-ink-500">{slide.body}</p>
      </div>

      <div className="flex flex-col items-center gap-8 pb-4">
        <div className="flex items-center gap-3" role="presentation">
          {SLIDES.map((_, n) => (
            <span
              key={n}
              className={`h-2.5 rounded-full transition-all ${
                n === i ? 'w-12 bg-emerald-deep' : 'w-2.5 bg-emerald-deep/20'
              }`}
            />
          ))}
        </div>

        <div className="w-full max-w-[384px]">
          <PrimaryButton onClick={() => (last ? onDone() : setI(i + 1))}>
            {last ? 'Get Started' : 'Next'}
            <ChevronRightIcon className="h-5 w-5" strokeWidth={2.2} />
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
}
