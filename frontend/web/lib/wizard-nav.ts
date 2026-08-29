/**
 * Step navigation for the create-listing wizard (SCRUM-200).
 *
 * Lives here rather than in the component because `vitest.config.ts` collects
 * `lib/**` only, and the rules below have more corners than they look: the
 * interesting cases are all about a seller going BACK, editing something into
 * an invalid state, and then trying to jump forward again.
 *
 * No data-persistence logic is needed anywhere: every field is controlled state
 * on the one wizard component, so leaving a step and returning to it already
 * shows exactly what was typed. This module only decides where you may go.
 */

export interface JumpContext {
  /** The step being clicked. */
  target: number;
  /** The step currently shown. */
  current: number;
  /**
   * The furthest step reached so far. Going back must not shrink it — the
   * seller would otherwise lose the ability to jump forward again to work they
   * had already completed.
   */
  maxVisited: number;
  /** Whether step `i`'s own required fields are currently filled. */
  isValid: (i: number) => boolean;
  /** True while the listing is being submitted; the wizard is read-only then. */
  busy?: boolean;
}

/**
 * Whether the stepper may jump straight to `target`.
 *
 *  - never while submitting, and never to the step already shown
 *  - BACKWARDS is always allowed; nothing is lost by leaving a step
 *  - FORWARDS only to a step already reached, and only when every step in
 *    between currently validates
 *
 * That last rule is the point of the whole function. Without it a seller could
 * go back to step 1, clear the title, then click straight to Review and sit on
 * a listing that cannot be submitted, with the failure surfacing only at the
 * end. It makes the stepper honour exactly the gate the Next button already
 * honours.
 */
export function canJumpToStep({
  target,
  current,
  maxVisited,
  isValid,
  busy = false,
}: JumpContext): boolean {
  if (busy) return false;
  if (target === current) return false;
  if (target < 0) return false;
  if (target < current) return true;
  if (target > maxVisited) return false;
  for (let i = current; i < target; i += 1) {
    if (!isValid(i)) return false;
  }
  return true;
}
