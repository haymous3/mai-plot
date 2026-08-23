/**
 * Handoff between the register funnel and /verify-otp (SCRUM-175).
 *
 * The keys live here rather than on the page component so the funnel doesn't
 * have to import a client component just to read three constants.
 *
 * sessionStorage, deliberately, rather than a query parameter: the phone is an
 * MSISDN and a query parameter would put it in browser history and in server
 * access logs. Same reasoning that made /verify-email POST its token instead of
 * taking it from the URL (SCRUM-152). sessionStorage is origin-scoped and dies
 * with the tab, which suits a value only needed between two consecutive steps.
 */
export const VERIFY_PHONE_KEY = 'mp_verify_phone';
export const VERIFY_EMAIL_KEY = 'mp_verify_email';
export const VERIFY_EXPIRES_KEY = 'mp_verify_expires_at';

/** Matches auth-service `otp_expire_minutes` — a fallback only; the register
 *  response's `verification_expires_in_seconds` is authoritative. */
export const OTP_TTL_SECONDS = 300;

/** Clear the handoff once verification has succeeded (or been abandoned). */
export function clearVerifyHandoff(): void {
  sessionStorage.removeItem(VERIFY_PHONE_KEY);
  sessionStorage.removeItem(VERIFY_EMAIL_KEY);
  sessionStorage.removeItem(VERIFY_EXPIRES_KEY);
}
