/**
 * Motion constants and the one bit of arithmetic behind the landing-page
 * animations (SCRUM-216).
 *
 * WHY THERE IS NO ANIMATION LIBRARY HERE. `package.json` carries exactly three
 * dependencies — next, react, react-dom. framer-motion would add ~50KB gzipped
 * to a marketing page whose job is to load fast, and `motion.div` forces
 * `'use client'` onto sections that are server-rendered today, converting the
 * page's rendering model to buy easing curves that are four lines of CSS. The
 * whole mechanism is a CSS transition plus one IntersectionObserver.
 *
 * The easing and distance are NOT invented. `globals.css` already shipped a
 * `rise` keyframe for the login card — 12px of travel on
 * cubic-bezier(0.22, 1, 0.36, 1) — and this reuses that house style rather
 * than introducing a second one.
 *
 * Lives in `lib/` rather than beside the component because `vitest.config.ts`
 * collects `lib/**` only, and the stagger cap below is exactly the kind of
 * off-by-one that looks obviously right and is quietly wrong.
 */

/** Travel and easing, shared by the scroll reveal and the hero's entrance. */
export const MOTION_DURATION_MS = 700;
export const MOTION_EASING = 'cubic-bezier(0.22, 1, 0.36, 1)';

/** Gap between consecutive items in a staggered row or grid. */
export const STAGGER_STEP_MS = 80;

/**
 * How many steps the stagger is allowed to climb before it flattens.
 *
 * Without a cap, a 12-card grid would take 12 x 80ms = 960ms to finish
 * arriving, and the last card lands long after the reader has looked at it.
 * Capping at 6 keeps the longest wait under half a second whatever the row
 * length; items past the cap all share the final delay.
 */
export const STAGGER_MAX_STEPS = 6;

/**
 * Start `bottom: -10%` — fire slightly BEFORE the element's top edge reaches
 * the viewport bottom, so the transition is already under way by the time it
 * is properly in view. Revealing exactly at the edge reads as a lag.
 */
export const REVEAL_ROOT_MARGIN = '0px 0px -10% 0px';

/** Delay for the item at `index` in a staggered group, in milliseconds. */
export function staggerDelayMs(
  index: number,
  step = STAGGER_STEP_MS,
  maxSteps = STAGGER_MAX_STEPS,
): number {
  if (!Number.isFinite(index) || index <= 0) return 0;
  return Math.min(Math.floor(index), maxSteps) * step;
}
