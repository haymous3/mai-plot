/**
 * Buyer session constants (SCRUM-94), now backed by the shared non-admin session
 * (SCRUM-132). The cookie namespace is shared across buyer/seller/realtor — these
 * re-exports keep the SCRUM-94 buyer imports stable while the register funnel and
 * future seller/realtor surfaces use lib/session.ts directly.
 */

export {
  SESSION_ACCESS_COOKIE as BUYER_ACCESS_COOKIE,
  SESSION_REFRESH_COOKIE as BUYER_REFRESH_COOKIE,
} from './session';

export function isBuyerRole(role: string | null | undefined): boolean {
  return role === 'buyer';
}

/** Where a signed-in buyer lands after login. */
export const BUYER_HOME = '/dashboard';
/**
 * Carries the role since SCRUM-235: bare `/login` is now the role PICKER, and
 * a buyer bounced off a protected page already told us who they are. Seller
 * and realtor layouts have done this (`?role=seller` / `?role=realtor`) since
 * they were built; buyer was the odd one out.
 */
export const BUYER_LOGIN = '/login?role=buyer';
