/**
 * Turning a NIN-verify response into what the field should show — SCRUM-221.
 *
 * Pure so it can be tested in the node environment the rest of `lib/` uses; the
 * hook in `app/_onboarding/nin-verify-field.tsx` does the fetching and holds the
 * state, and defers every decision to this file.
 */

export type NinStatus = 'idle' | 'checking' | 'verified' | 'pending' | 'error';

export type NinOutcome = {
  status: NinStatus;
  message: string | null;
  /**
   * Whether the same number is worth spending another call on.
   *
   * A failed verification persists NOTHING server-side (SCRUM-218), so the
   * value can be retried; a success cannot be re-submitted at all, because
   * `has_nin` answers 409 from then on.
   */
  retryable: boolean;
};

export type NinResponseBody = {
  error_code?: string;
  status?: string;
};

const NIN_RE = /^\d{11}$/;

/** Exactly 11 digits — the only shape worth spending a ~₦100 call on. */
export function isCompleteNin(value: string): boolean {
  return NIN_RE.test(value.trim());
}

/**
 * `verified` and `pending` both let the caller proceed.
 *
 * `pending` is Ninja's `review` — a partially matching name, which is not a
 * fraud signal. The account simply is not advanced to `id_verified`. Blocking
 * on it would strand a real person behind a middle name.
 */
export function ninIsSettled(status: NinStatus): boolean {
  return status === 'verified' || status === 'pending';
}

export function ninOutcome(ok: boolean, body: NinResponseBody): NinOutcome {
  if (ok) {
    if (body.status === 'pending') {
      return {
        status: 'pending',
        message: 'We are still checking this one. You can carry on in the meantime.',
        retryable: false,
      };
    }
    return { status: 'verified', message: null, retryable: false };
  }

  switch (body.error_code) {
    case 'NIN_FORMAT_INVALID':
      return { status: 'error', message: 'A NIN is exactly 11 digits.', retryable: true };
    case 'NIN_ALREADY_VERIFIED':
      // Deliberately does not say WHOSE account holds it — auth-service will
      // not distinguish "yours" from "someone else's", because that answer is
      // an oracle for whether a NIN is registered here at all.
      return {
        status: 'error',
        message: 'This NIN has already been verified.',
        retryable: false,
      };
    case 'NIN_NOT_VERIFIED':
      return {
        status: 'error',
        message: 'That NIN did not match your name. Check both and try again.',
        retryable: true,
      };
    default:
      // Includes NIN_VERIFICATION_UNAVAILABLE (502) and anything unmapped.
      return {
        status: 'error',
        message: 'We could not check that NIN just now. Please try again.',
        retryable: true,
      };
  }
}
