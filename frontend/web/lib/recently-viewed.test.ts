import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  getRecentlyViewed,
  recordRecentlyViewed,
  type RecentListingInput,
} from './recently-viewed';

// The helper guards on `typeof window` (SSR-safe). Install a minimal window with
// an in-memory localStorage so the node test env can exercise the real logic.
class MemoryStorage {
  private store = new Map<string, string>();
  getItem(k: string): string | null {
    return this.store.has(k) ? (this.store.get(k) as string) : null;
  }
  setItem(k: string, v: string): void {
    this.store.set(k, v);
  }
  removeItem(k: string): void {
    this.store.delete(k);
  }
}

function item(id: string): RecentListingInput {
  return {
    id,
    title: `Listing ${id}`,
    location: 'Ikeja, Lagos',
    asking_price_kobo: 5_000_000_00,
    sale_type: 'normal',
    thumbnail_url: null,
  };
}

beforeEach(() => {
  (globalThis as { window?: unknown }).window = { localStorage: new MemoryStorage() };
});

afterEach(() => {
  delete (globalThis as { window?: unknown }).window;
});

describe('recordRecentlyViewed', () => {
  it('stores a viewed listing with a viewed_at stamp', () => {
    recordRecentlyViewed(item('a'));
    const got = getRecentlyViewed();
    expect(got).toHaveLength(1);
    expect(got[0].id).toBe('a');
    expect(typeof got[0].viewed_at).toBe('string');
  });

  it('moves a re-viewed listing to the front without duplicating', () => {
    recordRecentlyViewed(item('a'));
    recordRecentlyViewed(item('b'));
    recordRecentlyViewed(item('a'));
    const ids = getRecentlyViewed().map((x) => x.id);
    expect(ids).toEqual(['a', 'b']);
  });

  it('caps the list at 8 entries, newest-first', () => {
    for (let i = 0; i < 12; i++) recordRecentlyViewed(item(`id-${i}`));
    const ids = getRecentlyViewed().map((x) => x.id);
    expect(ids).toHaveLength(8);
    expect(ids[0]).toBe('id-11');
    expect(ids.at(-1)).toBe('id-4');
  });
});

describe('getRecentlyViewed', () => {
  it('returns [] when nothing is stored', () => {
    expect(getRecentlyViewed()).toEqual([]);
  });

  it('returns [] on a corrupt payload rather than throwing', () => {
    window.localStorage.setItem('mp_recent_listings', 'not json{');
    expect(getRecentlyViewed()).toEqual([]);
  });

  it('is SSR-safe: returns [] with no window', () => {
    delete (globalThis as { window?: unknown }).window;
    expect(getRecentlyViewed()).toEqual([]);
  });
});
