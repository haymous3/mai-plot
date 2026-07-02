/**
 * Shared non-admin session (SCRUM-132) — pure constants + helpers (no
 * next/headers, so it's unit-testable). The server-only cookie reader lives in
 * session-server.ts.
 *
 * One httpOnly cookie namespace for buyers, sellers, and realtors (admins keep
 * their own `mp_admin_*` session + `/admin` middleware). Registration/login set
 * these cookies from the tokens auth-service returns; role decides the landing.
 */

export const SESSION_ACCESS_COOKIE = 'mp_user_at';
export const SESSION_REFRESH_COOKIE = 'mp_user_rt';

export const SESSION_LOGIN = '/login';

export const NON_ADMIN_ROLES = ['buyer', 'seller', 'realtor'] as const;
export type NonAdminRole = (typeof NON_ADMIN_ROLES)[number];

export function isNonAdminRole(role: string | null | undefined): role is NonAdminRole {
  return role === 'buyer' || role === 'seller' || role === 'realtor';
}

/** Where a signed-in user lands, by role. Buyer has the fullest surface today;
 * seller/realtor land on their onboarding placeholders pending their Figma. */
export function roleHome(role: string): string {
  switch (role) {
    case 'seller':
      return '/seller';
    case 'realtor':
      return '/realtor';
    default:
      return '/dashboard';
  }
}
