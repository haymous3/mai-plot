/**
 * Admin session primitives (SCRUM-59).
 *
 * The access + refresh tokens live in httpOnly cookies set by the login route
 * handler — never in client-readable JS. "Admin auth is separate from regular
 * user auth": only the privileged roles below may hold an admin session.
 */

export const ACCESS_COOKIE = 'mp_admin_at';
export const REFRESH_COOKIE = 'mp_admin_rt';

/** Roles permitted on the admin dashboard: platform admins + the legal team. */
export const ADMIN_ROLES = ['admin', 'legal_team'] as const;
export type AdminRole = (typeof ADMIN_ROLES)[number];

export function isAdminRole(role: string | null | undefined): role is AdminRole {
  return role === 'admin' || role === 'legal_team';
}

/** Where an authenticated admin lands after login (AC6). */
export const ADMIN_HOME = '/admin/listings/queue';
export const ADMIN_LOGIN = '/admin/login';
