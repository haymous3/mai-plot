/**
 * Buyer session primitives (SCRUM-94).
 *
 * Separate from the admin session (lib/auth.ts): buyers get their own httpOnly
 * cookie namespace and their own login surface. Only the `buyer` role may hold a
 * buyer session — sellers/realtors will get their own surfaces later.
 *
 * NOTE: this login gate is intentionally minimal and temporary — the polished
 * auth screens come from Figma in a later ticket. It exists so the loan flow can
 * run end-to-end today.
 */

export const BUYER_ACCESS_COOKIE = 'mp_buyer_at';
export const BUYER_REFRESH_COOKIE = 'mp_buyer_rt';

export function isBuyerRole(role: string | null | undefined): boolean {
  return role === 'buyer';
}

/** Where a signed-in buyer lands after login. */
export const BUYER_HOME = '/dashboard';
export const BUYER_LOGIN = '/login';
