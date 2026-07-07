import { NextResponse } from 'next/server';

import { SESSION_ACCESS_COOKIE, SESSION_LOGIN, SESSION_REFRESH_COOKIE } from '@/lib/session';

/**
 * Shared non-admin logout (SCRUM-98). Clears the session cookies and returns the
 * login redirect. Used by the seller/realtor surfaces (and can replace the
 * buyer-specific logout).
 */
export async function POST(): Promise<NextResponse> {
  const response = NextResponse.json({ ok: true, redirect: SESSION_LOGIN });
  response.cookies.set(SESSION_ACCESS_COOKIE, '', { path: '/', maxAge: 0 });
  response.cookies.set(SESSION_REFRESH_COOKIE, '', { path: '/', maxAge: 0 });
  return response;
}
