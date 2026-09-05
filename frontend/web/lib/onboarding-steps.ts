/**
 * Which post-verification onboarding steps each role sees — SCRUM-185.
 *
 * Kept out of the component because `vitest.config.ts` collects
 * `lib/**\/*.test.ts` only, in a node environment with no DOM. Anything that
 * needs a test has to live here rather than in a `.tsx`.
 *
 * Verification (email link or phone OTP) establishes the session and then hands
 * off here instead of straight to the dashboard. Every step is reachable only
 * once — this is not a wizard a user can navigate backwards through, because
 * each step POSTs to a real endpoint as it completes.
 */

export type OnboardingRole = 'buyer' | 'seller' | 'realtor';

export type OnboardingStep =
  /** Buyer only: NIN (required), address (required) and buying capacity. */
  | 'buyer-profile'
  /** Seller only: NIN, selling authority, and a PoA document when not the owner. */
  | 'seller-verification'
  /** Realtor only: NIN, address, coverage area, credentials document. */
  | 'realtor-profile'
  /** Shared closing screen for every role. */
  | 'welcome';

const STEPS: Record<OnboardingRole, readonly OnboardingStep[]> = {
  // No 'personal-details' step any more (SCRUM-197): registration collects the
  // full name again, for every role, so asking a buyer a second time would
  // show them an empty field for something they had already typed.
  buyer: ['buyer-profile', 'welcome'],
  seller: ['seller-verification', 'welcome'],
  realtor: ['realtor-profile', 'welcome'],
};

/**
 * Roles that reach onboarding. Anything else — admin, legal_team, bank_partner —
 * has no onboarding and is sent straight to its own home.
 */
export function isOnboardingRole(role: string): role is OnboardingRole {
  return role === 'buyer' || role === 'seller' || role === 'realtor';
}

/** The ordered steps for a role. Unknown roles get nothing, not a default flow. */
export function stepsFor(role: string): readonly OnboardingStep[] {
  return isOnboardingRole(role) ? STEPS[role] : [];
}

/**
 * The step after `current`, or null when the flow is done.
 *
 * Returns null for a step that does not belong to the role rather than guessing
 * a position — a mismatch means the caller is confused, and silently dropping
 * the user into another role's flow would be worse than ending it.
 */
export function nextStep(role: string, current: OnboardingStep): OnboardingStep | null {
  const steps = stepsFor(role);
  const i = steps.indexOf(current);
  if (i < 0) return null;
  return steps[i + 1] ?? null;
}

/** The first step for a role, or null if the role has no onboarding. */
export function firstStep(role: string): OnboardingStep | null {
  return stepsFor(role)[0] ?? null;
}

/**
 * Steps a user may leave without completing.
 *
 * NONE, since SCRUM-201. `buyer-profile` used to be skippable — the design drew
 * a "Skip for now" and every field on it was optional server-side — but NIN and
 * address are now required of every role, so that button was removed rather
 * than left offering something the submit path no longer honours.
 *
 * The seller and realtor steps were never skippable: they gate real capability
 * (a seller cannot publish without a declared authority, CLAUDE.md §8.1; a
 * realtor row does not exist until POST /realtors succeeds).
 *
 * Kept as a function rather than deleted: it is the one place that answers this
 * question, and a later step may well be optional again.
 */
export function isSkippable(_step: OnboardingStep): boolean {
  return false;
}

/**
 * Where a role lands once onboarding finishes.
 *
 * Deliberately just `roleHome` — onboarding exits exactly where verification
 * used to send people directly, so there is no second copy of that mapping to
 * drift out of sync.
 */
export { roleHome as onboardingExit } from './session';

/**
 * The closing screen's greeting (SCRUM-197).
 *
 * Lives here rather than in the component because `vitest.config.ts` collects
 * `lib/**` only — and this has more edge cases than it looks: an account that
 * predates SCRUM-197 has `full_name = ""` (registration stored `full_name or
 * ""`), not null, so "absent" has two spellings.
 *
 * Given name only. The design's greeting band is a single ~58px line, and a
 * full Nigerian name with two given names and a surname wraps it.
 */
export function welcomeGreeting(fullName?: string | null): string {
  const first = fullName?.trim().split(/\s+/)[0];
  return first ? `Welcome, ${first}!` : 'Welcome!';
}
