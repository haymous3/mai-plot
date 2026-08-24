/**
 * Paging arithmetic for the landing-page testimonial carousel (SCRUM-178).
 *
 * Kept out of the component so it can be unit-tested — `vitest.config.ts` runs
 * `lib/**\/*.test.ts` in a node environment with no DOM, so anything that needs
 * a test has to live here rather than in a `.tsx`.
 */

/** Number of pages needed to show `total` items `perPage` at a time. */
export function pageCount(total: number, perPage: number): number {
  if (perPage < 1 || total < 1) return 0;
  return Math.ceil(total / perPage);
}

/**
 * Move `delta` pages from `page`, wrapping at both ends.
 *
 * Wrapping rather than clamping is deliberate: the design's prev/next controls
 * are always drawn enabled, with no disabled state anywhere in the export, so
 * clamping would leave a live-looking button that does nothing on the first and
 * last page.
 */
export function stepPage(page: number, delta: number, pages: number): number {
  if (pages < 1) return 0;
  return ((page + delta) % pages + pages) % pages;
}

/** The slice of `items` shown on `page`. Out-of-range pages yield an empty slice. */
export function pageItems<T>(items: readonly T[], page: number, perPage: number): T[] {
  if (perPage < 1 || page < 0) return [];
  return items.slice(page * perPage, page * perPage + perPage);
}
