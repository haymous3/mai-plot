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
  /** Buyer only: full name. Registration no longer collects it (SCRUM-185). */
  | 'personal-details'
  /** Buyer only: NIN + buying capacity. All optional — the design has "Skip for now". */
  | 'buyer-profile'
  /** Seller only: NIN, selling authority, and a PoA document when not the owner. */
  | 'seller-verification'
  /** Realtor only: ESVARBON, coverage area, credentials document. */
  | 'realtor-profile'
  /** Shared closing screen for every role. */
  | 'welcome';

const STEPS: Record<OnboardingRole, readonly OnboardingStep[]> = {
  buyer: ['personal-details', 'buyer-profile', 'welcome'],
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
 * `buyer-profile` is skippable because the design draws a "Skip for now" beside
 * its CTA and every field on it is optional server-side. The seller and realtor
 * steps are NOT: they gate real capability (a seller cannot publish without a
 * declared authority, CLAUDE.md §8.1; a realtor row does not exist until
 * POST /realtors succeeds), so skipping them would strand the account in a
 * state the rest of the product does not expect.
 */
export function isSkippable(step: OnboardingStep): boolean {
  return step === 'buyer-profile';
}

/**
 * Where a role lands once onboarding finishes.
 *
 * Deliberately just `roleHome` — onboarding exits exactly where verification
 * used to send people directly, so there is no second copy of that mapping to
 * drift out of sync.
 */
export { roleHome as onboardingExit } from './session';
