/**
 * Payout bank account — shared pieces (SCRUM-223). Pure: no next/headers, so
 * unit-testable. The server-side read lives in payout-account-server.ts.
 */

export type PayoutAccount = {
  account_number_masked: string;
  bank_code: string;
  account_name: string;
  recipient_ready: boolean;
};

export const ACCOUNT_NUMBER_DIGITS = 10;

/** A NUBAN account number: exactly ten digits. */
export function isCompleteAccountNumber(value: string): boolean {
  return /^\d{10}$/.test(value);
}

/** Digits only, capped at ten — stripping as they type beats rejecting after. */
export function cleanAccountNumber(value: string): string {
  return value.replace(/\D/g, '').slice(0, ACCOUNT_NUMBER_DIGITS);
}

const MESSAGES: Record<string, string> = {
  ACCOUNT_NOT_RESOLVED:
    'Your bank doesn’t recognise that account number. Check the number and the bank.',
  RECIPIENT_UNAVAILABLE: 'We couldn’t reach the bank just now. Please try again in a moment.',
  PASSWORD_INCORRECT: 'That password is incorrect.',
  REAUTH_RATE_LIMITED: 'Too many password attempts. Please wait a while and try again.',
  REAUTH_REQUIRED: 'Please confirm your password again.',
  VALIDATION_ERROR: 'Check the bank and the 10-digit account number.',
  INVALID_REQUEST: 'Check the bank and the 10-digit account number.',
  NO_SESSION: 'Your session has ended. Sign in again to continue.',
};

export function payoutErrorMessage(code: string | undefined): string {
  return (code && MESSAGES[code]) || 'Something went wrong. Please try again.';
}
