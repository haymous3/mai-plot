'use client';

import { useState } from 'react';

import { SaveHeart } from '../../dashboard/save-heart';

/** Property-detail image carousel (SCRUM-95). Client-side prev/next over the
 * listing media, with the badge overlays + save heart from the design. */
export function Carousel({
  listingId,
  images,
  badges,
  daysLeft,
  initialSaved,
}: {
  listingId: string;
  images: string[];
  badges: React.ReactNode;
  daysLeft: number | null;
  initialSaved: boolean;
}) {
  const [i, setI] = useState(0);
  const has = images.length > 0;
  const go = (d: number) => setI((prev) => (prev + d + images.length) % images.length);

  return (
    <div className="relative overflow-hidden rounded-2xl bg-bone">
      <div className="aspect-[16/9] w-full">
        {has ? (
          // eslint-disable-next-line @next/next/no-img-element -- listing media is an external CDN URL
          <img src={images[i]} alt="Property" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-4xl text-ink-300">
            🏠
          </div>
        )}
      </div>

      <div className="absolute left-3 top-3 flex flex-col gap-1.5">{badges}</div>
      <div className="absolute right-3 top-3 flex items-center gap-2">
        {daysLeft !== null && (
          <span className="rounded-full bg-white/90 px-2.5 py-1 text-xs font-medium text-red-600">
            ⏱ {daysLeft} days left
          </span>
        )}
        <SaveHeart listingId={listingId} initialSaved={initialSaved} />
      </div>

      {images.length > 1 && (
        <>
          <button
            type="button"
            onClick={() => go(-1)}
            aria-label="Previous image"
            className="absolute left-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-white/80 text-ink-buyer transition hover:bg-white"
          >
            ‹
          </button>
          <button
            type="button"
            onClick={() => go(1)}
            aria-label="Next image"
            className="absolute right-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-white/80 text-ink-buyer transition hover:bg-white"
          >
            ›
          </button>
          <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 gap-1.5">
            {images.map((_, n) => (
              <span
                key={n}
                className={`h-1.5 rounded-full transition-all ${n === i ? 'w-4 bg-white' : 'w-1.5 bg-white/50'}`}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
