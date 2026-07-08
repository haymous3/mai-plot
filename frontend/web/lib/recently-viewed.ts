/**
 * Client-side "recently viewed listings" cache (SCRUM-136).
 *
 * The buyer surfaces are server-rendered, so there is no React Query cache to
 * persist. Instead we record a compact summary of each listing the buyer opens
 * into localStorage, so a Recently Viewed strip can still render from cache when
 * connectivity is flaky (and the live feed can't be fetched). Purely a
 * progressive enhancement — never the source of truth.
 */

const STORAGE_KEY = 'mp_recent_listings';
const CAP = 8;

export interface RecentListing {
  id: string;
  title: string;
  location: string;
  asking_price_kobo: number;
  sale_type: string;
  thumbnail_url: string | null;
  viewed_at: string;
}

/** The fields a caller supplies; `viewed_at` is stamped here. */
export type RecentListingInput = Omit<RecentListing, 'viewed_at'>;

function isBrowser(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

/** Read the cache, newest-first. Never throws — a corrupt/absent value is []. */
export function getRecentlyViewed(): RecentListing[] {
  if (!isBrowser()) return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (x): x is RecentListing =>
        typeof x === 'object' && x !== null && typeof (x as RecentListing).id === 'string',
    );
  } catch {
    return [];
  }
}

/**
 * Record a viewed listing: moves it to the front, de-duplicates by id, and caps
 * the list at CAP entries. No-op off the browser or if storage is unavailable
 * (e.g. private mode quota).
 */
export function recordRecentlyViewed(item: RecentListingInput): void {
  if (!isBrowser()) return;
  try {
    const existing = getRecentlyViewed().filter((x) => x.id !== item.id);
    const next = [{ ...item, viewed_at: new Date().toISOString() }, ...existing].slice(0, CAP);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Best-effort — a storage failure must never break the page.
  }
}
