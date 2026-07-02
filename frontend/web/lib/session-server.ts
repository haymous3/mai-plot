/**
 * Server-only session helpers (SCRUM-132). Separated from session.ts so the
 * pure constants/helpers there stay importable in unit tests without next/headers.
 */

import { cookies } from 'next/headers';

import { SESSION_ACCESS_COOKIE } from '@/lib/session';

/** The shared non-admin session access token, or null. */
export function sessionAccessToken(): string | null {
  return cookies().get(SESSION_ACCESS_COOKIE)?.value ?? null;
}
