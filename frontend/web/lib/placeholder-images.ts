/**
 * Stand-in photography for slots that would otherwise render empty (SCRUM-203).
 *
 * The landing page renders real listing media: the hero, the featured cards and
 * the financing panel all take a `thumbnail_url` from the public feed. When a
 * listing has no media uploaded, every one of those collapsed to a flat tinted
 * box — the live site currently renders ZERO `<img>` tags while still showing
 * six priced listings, because not one of them has a photo on file.
 *
 * These are Unsplash CDN URLs, not an API integration: direct, keyless, cached
 * at their edge, and each one verified to return `200 image/jpeg` before being
 * added here. A URL that 404s would trade a blank box for a broken-image icon,
 * which is worse.
 *
 * ⚠️ A REAL PHOTO ALWAYS WINS. These are only reached when `thumbnail_url` is
 * null, so a seller who uploads media never sees a stock image in its place.
 *
 * ⚠️ AND A LISTING CARD SAYS SO. On a property marketplace, a stock house under
 * a real address and price implies that house is the property. `isPlaceholder`
 * lets the card mark it, so the page is complete without asserting something
 * untrue about a listing. The hero and financing panels are decorative framing
 * rather than a specific property, so they carry no marker.
 */

/** Verified Unsplash CDN URLs. Sized per slot at the call site. */
function unsplash(id: string, width: number): string {
  return `https://images.unsplash.com/${id}?auto=format&fit=crop&w=${width}&q=70`;
}

/**
 * The pool a listing without photos draws from.
 *
 * Several, not one, so a grid of six cards does not look like the same house
 * repeated — which reads as a bug rather than as missing photography.
 */
const LISTING_PHOTO_IDS = [
  'photo-1560518883-ce09059eeffa',
  'photo-1568605114967-8130f3a36994',
  'photo-1512917774080-9991f1c4c750',
  'photo-1600596542815-ffad4c1539a9',
  'photo-1600585154340-be6161a56a0c',
  'photo-1583608205776-bfd35f0d9f83',
  'photo-1600607687939-ce8a6c25118c',
  'photo-1613977257363-707ba9348227',
] as const;

/**
 * Pick a stand-in for a listing, keyed by its id.
 *
 * DETERMINISTIC on purpose. `Math.random()` here would pick differently on the
 * server and the client, which React reports as a hydration mismatch, and the
 * card would visibly swap image on load. Hashing the id also means a listing
 * keeps the same photo between visits instead of shuffling on every render.
 */
export function listingPlaceholder(seed: string, width = 800): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return unsplash(LISTING_PHOTO_IDS[hash % LISTING_PHOTO_IDS.length], width);
}

/**
 * Decorative imagery for the two panels that frame the page rather than
 * depicting a particular listing. No marker needed: nothing here claims to be
 * a property anyone can buy.
 */
export const HERO_IMAGE = unsplash('photo-1582407947304-fd86f028f716', 1200);
export const FINANCING_IMAGE = unsplash('photo-1554995207-c18c203602cb', 1200);
