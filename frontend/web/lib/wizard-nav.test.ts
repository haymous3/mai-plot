import { describe, expect, it } from 'vitest';

import { canJumpToStep } from './wizard-nav';

/** Every step valid — the ordinary case. */
const allValid = () => true;

/** Only the named steps are invalid. */
const invalidAt = (...bad: number[]) => (i: number) => !bad.includes(i);

describe('canJumpToStep', () => {
  it('allows going back to any earlier step', () => {
    // The whole point of the ticket: reach step 5, click step 1 directly
    // instead of pressing Previous four times.
    for (const target of [0, 1, 2, 3, 4]) {
      expect(
        canJumpToStep({ target, current: 5, maxVisited: 5, isValid: allValid }),
      ).toBe(true);
    }
  });

  it('allows going back even when a later step is incomplete', () => {
    // Going back is how you FIX an incomplete step; blocking it would trap the
    // seller on the step they need to leave.
    expect(
      canJumpToStep({ target: 0, current: 4, maxVisited: 4, isValid: invalidAt(4) }),
    ).toBe(true);
  });

  it('refuses the step already shown', () => {
    expect(
      canJumpToStep({ target: 3, current: 3, maxVisited: 5, isValid: allValid }),
    ).toBe(false);
  });

  it('refuses a step never reached', () => {
    // Jumping to an unseen step would skip its predecessors' gates entirely.
    expect(
      canJumpToStep({ target: 4, current: 1, maxVisited: 2, isValid: allValid }),
    ).toBe(false);
  });

  it('allows jumping forward to a step already reached when everything between validates', () => {
    expect(
      canJumpToStep({ target: 5, current: 1, maxVisited: 5, isValid: allValid }),
    ).toBe(true);
  });

  it('refuses a forward jump when the CURRENT step has been broken', () => {
    // The case this function exists for: back to step 1, clear the title, then
    // try to click Review. Allowing it would carry an unsubmittable listing to
    // the end and fail there instead of here.
    expect(
      canJumpToStep({ target: 6, current: 1, maxVisited: 6, isValid: invalidAt(1) }),
    ).toBe(false);
  });

  it('refuses a forward jump when an INTERMEDIATE step has been broken', () => {
    // Standing on 1, jumping to 5, with 3 broken — checking only the current
    // step would wrongly allow this.
    expect(
      canJumpToStep({ target: 5, current: 1, maxVisited: 5, isValid: invalidAt(3) }),
    ).toBe(false);
  });

  it('does not require the TARGET itself to be valid', () => {
    // You are travelling TO that step to fill it in. Requiring it to be valid
    // already would make an incomplete step permanently unreachable.
    expect(
      canJumpToStep({ target: 5, current: 1, maxVisited: 5, isValid: invalidAt(5) }),
    ).toBe(true);
  });

  it('refuses everything while submitting', () => {
    expect(
      canJumpToStep({ target: 0, current: 5, maxVisited: 5, isValid: allValid, busy: true }),
    ).toBe(false);
    expect(
      canJumpToStep({ target: 5, current: 1, maxVisited: 5, isValid: allValid, busy: true }),
    ).toBe(false);
  });

  it('refuses a negative target', () => {
    expect(
      canJumpToStep({ target: -1, current: 2, maxVisited: 5, isValid: allValid }),
    ).toBe(false);
  });

  it('allows stepping forward one at a time, as Next does', () => {
    // The stepper must not be stricter than the button beside it.
    expect(
      canJumpToStep({ target: 2, current: 1, maxVisited: 2, isValid: allValid }),
    ).toBe(true);
  });
});
