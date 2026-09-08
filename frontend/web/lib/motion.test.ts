import { describe, expect, it } from 'vitest';

import {
  MOTION_EASING,
  REVEAL_ROOT_MARGIN,
  STAGGER_MAX_STEPS,
  STAGGER_STEP_MS,
  staggerDelayMs,
} from './motion';

describe('staggerDelayMs', () => {
  it('gives the first item no delay', () => {
    // The lead item must move the instant its group is in view; a delay on
    // index 0 makes the whole group feel like it reacted late.
    expect(staggerDelayMs(0)).toBe(0);
  });

  it('steps evenly across a row', () => {
    expect(staggerDelayMs(1)).toBe(STAGGER_STEP_MS);
    expect(staggerDelayMs(2)).toBe(STAGGER_STEP_MS * 2);
    expect(staggerDelayMs(3)).toBe(STAGGER_STEP_MS * 3);
  });

  it('flattens past the cap instead of growing without bound', () => {
    // A 12-card grid would otherwise finish arriving ~960ms in, long after the
    // reader has looked at the last card.
    const capped = STAGGER_STEP_MS * STAGGER_MAX_STEPS;
    expect(staggerDelayMs(STAGGER_MAX_STEPS)).toBe(capped);
    expect(staggerDelayMs(STAGGER_MAX_STEPS + 1)).toBe(capped);
    expect(staggerDelayMs(40)).toBe(capped);
  });

  it('never returns a negative or NaN delay', () => {
    // A negative transition-delay starts the transition mid-flight, which
    // renders as a visible jump rather than a fade.
    for (const bad of [-1, -100, Number.NaN, Number.POSITIVE_INFINITY]) {
      const delay = staggerDelayMs(bad);
      expect(Number.isFinite(delay)).toBe(true);
      expect(delay).toBeGreaterThanOrEqual(0);
    }
  });

  it('honours a caller-supplied step and cap', () => {
    expect(staggerDelayMs(2, 50)).toBe(100);
    expect(staggerDelayMs(9, 50, 3)).toBe(150);
  });

  it('keeps the longest wait under half a second at the default settings', () => {
    // The cap exists to bound this; if either constant is raised without
    // thought, this is the test that should object.
    expect(staggerDelayMs(Number.MAX_SAFE_INTEGER)).toBeLessThan(500);
  });
});

describe('motion constants', () => {
  it('reuses the easing the login card already shipped with', () => {
    // globals.css's `rise` keyframe. A second easing curve on the same site is
    // the kind of drift nobody notices until the whole thing feels incoherent.
    expect(MOTION_EASING).toBe('cubic-bezier(0.22, 1, 0.36, 1)');
  });

  it('fires the observer slightly before the element is fully in view', () => {
    // A NEGATIVE bottom margin shrinks the root box, so the callback runs once
    // the element is 10% inside rather than the moment it touches the edge.
    expect(REVEAL_ROOT_MARGIN).toContain('-10%');
  });
});
