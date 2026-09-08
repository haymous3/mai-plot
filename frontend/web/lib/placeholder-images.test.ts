import { describe, expect, it } from 'vitest';

import { FINANCING_IMAGE, HERO_IMAGE, listingPlaceholder } from './placeholder-images';

describe('listingPlaceholder', () => {
  it('is deterministic for a given listing', () => {
    // The reason this is hashed rather than random: a different pick on the
    // server and the client is a hydration mismatch, and the card would
    // visibly swap image on load.
    expect(listingPlaceholder('listing-abc')).toBe(listingPlaceholder('listing-abc'));
  });

  it('spreads different listings across the pool', () => {
    // Six identical houses in a grid reads as a bug, not as missing photos.
    const ids = Array.from({ length: 12 }, (_, i) => `listing-${i}`);
    const picked = new Set(ids.map((id) => listingPlaceholder(id)));
    expect(picked.size).toBeGreaterThan(1);
  });

  it('always returns a usable Unsplash CDN URL', () => {
    for (const id of ['a', 'listing-1', '', 'a-very-long-listing-uuid-0000-1111']) {
      const url = listingPlaceholder(id);
      expect(url.startsWith('https://images.unsplash.com/photo-')).toBe(true);
      expect(url).toContain('w=');
    }
  });

  it('handles an empty seed rather than throwing', () => {
    // A listing id should never be empty, but a blank string must still yield
    // an image — the whole point is that this slot is never empty.
    expect(listingPlaceholder('')).toContain('images.unsplash.com');
  });

  it('honours a requested width', () => {
    expect(listingPlaceholder('x', 1600)).toContain('w=1600');
  });
});

describe('decorative images', () => {
  it('are absolute CDN URLs', () => {
    for (const url of [HERO_IMAGE, FINANCING_IMAGE]) {
      expect(url.startsWith('https://images.unsplash.com/photo-')).toBe(true);
    }
  });

  it('are distinct from each other', () => {
    // The hero and the financing panel sit on the same page.
    expect(HERO_IMAGE).not.toBe(FINANCING_IMAGE);
  });
});
