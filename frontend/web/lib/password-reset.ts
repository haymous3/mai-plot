/**
 * Password-reset client logic — SCRUM-191.
 *
 * Kept out of the component because `vitest.config.ts` collects
 * `lib/**\/*.test.ts` only, in a node environment with no DOM. Anything that
 * needs a test has to live here rather than in a `.tsx`.
 *
 * Two decisions live here, and both are the kind that break quietly:
 * which error codes end the flow, and what the password rules actually are.
 */

/** Terminal states of /reset-password. `form` is where a retryable error stays. */
export type ResetPhase = 'form' | 'success' | 'expired' | 'invalid' | 'missing';

/**
 * Map a BFF error code to a terminal phase, or null to stay on the form.
 *
 * ⚠️ `PASSWORD_TOO_WEAK` deliberately returns null. The backend checks strength
 * only AFTER the token proves out and does not mark it used on that path, so the
 * link is still live — sending the user off to request a new one because they
 * typed a short password would be wrong and would waste their real link.
 *
 * Unrecognised codes also return null: an unknown failure is far more likely to
 * be transient than proof that a working link is dead, and declaring it dead is
 * the more expensive mistake.
 */
export function resetPhaseForError(code: string | undefined): ResetPhase | null {
  switch (code) {
    case 'RESET_TOKEN_EXPIRED':
      return 'expired';
    case 'RESET_TOKEN_INVALID':
      return 'invalid';
    default:
      return null;
  }
}

/**
 * The password rules the UI shows as a live checklist.
 *
 * ⚠️ These MUST mirror `is_strong()` in auth-service
 * (`app/services/password.py`) exactly: ≥8 characters, an uppercase letter, a
 * number. Showing a rule the server does not enforce trains users to satisfy
 * fiction; omitting one it does enforce makes a `PASSWORD_TOO_WEAK` rejection
 * unexplainable — the user sees every box ticked and still gets refused.
 */
export const PASSWORD_RULES: readonly { label: string; test: (value: string) => boolean }[] = [
  { label: 'At least 8 characters', test: (v) => v.length >= 8 },
  { label: 'An uppercase letter', test: (v) => /[A-Z]/.test(v) },
  { label: 'A number', test: (v) => /\d/.test(v) },
];

/** Whether a candidate satisfies every rule the server will apply. */
export function meetsPasswordRules(value: string): boolean {
  return PASSWORD_RULES.every((rule) => rule.test(value));
}

/**
 * Whether the reset form may be submitted.
 *
 * Note what this does NOT gate on: `meetsPasswordRules`. The checklist is
 * guidance and the server stays the authority — a user who somehow disagrees
 * with our regex still gets a real answer rather than a dead button with no
 * explanation. Only the two things the API cannot judge are enforced here:
 * that something was typed, and that the confirm field matches (the API has no
 * concept of a confirm field, so a mismatch is purely a typing check).
 */
export function canSubmitReset(password: string, confirm: string, submitting: boolean): boolean {
  return password.length > 0 && confirm.length > 0 && password === confirm && !submitting;
}
