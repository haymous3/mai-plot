/**
 * Server-only session helpers (SCRUM-132). Separated from session.ts so the
 * pure constants/helpers there stay importable in unit tests without next/headers.
 */

import { cookies } from 'next/headers';

import { roleHome, SESSION_ACCESS_COOKIE } from '@/lib/session';

/** The shared non-admin session access token, or null. */
export function sessionAccessToken(): string | null {
  return cookies().get(SESSION_ACCESS_COOKIE)?.value ?? null;
}

/** The caller's role from the session JWT (SCRUM-98). Reads the `role` claim
 * from the token payload for server-side route gating. The token is httpOnly and
 * set by us; a tampered token would fail every backend call, so decoding the
 * payload (without re-verifying the signature) is sufficient for routing. */
export function sessionRole(): string | null {
  const token = sessionAccessToken();
  if (!token) return null;
  try {
    const [, payload] = token.split('.');
    const claims = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as {
      role?: unknown;
    };
    return typeof claims.role === 'string' ? claims.role : null;
  } catch {
    return null;
  }
}

/** The signed-in caller's role home (e.g. /dashboard, /seller), or null. */
export function sessionHome(): string | null {
  const role = sessionRole();
  return role ? roleHome(role) : null;
}
