import { NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { SESSION_ACCESS_COOKIE, SESSION_REFRESH_COOKIE } from '@/lib/session';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Account-deletion proxy for the Settings Danger Zone (SCRUM-188).
 *
 * POST rather than DELETE, matching the auth-service route: the operation is
 * guarded and can legitimately refuse, which is not how a plain resource
 * removal behaves.
 *
 * ⚠️ CLEARS THE SESSION COOKIES ON SUCCESS, for the same reason
 * /api/auth/change-password does — auth-service revokes every refresh token as
 * part of the deletion, so the cookies this browser still holds are already
 * dead. Leaving them set would show the user a signed-in shell for an account
 * that no longer exists.
 *
 * ⚠️ Does NOT clear them on a 409 or 503. Those are refusals, not deletions:
 * the account is intact and the user must stay signed in to act on the reason.
 */
export async function POST(): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) {
    return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/account/delete`, {
      method: 'POST',
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'AUTH_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  const response = NextResponse.json(body, { status: resp.status });
  if (resp.ok) {
    response.cookies.set(SESSION_ACCESS_COOKIE, '', { path: '/', maxAge: 0 });
    response.cookies.set(SESSION_REFRESH_COOKIE, '', { path: '/', maxAge: 0 });
  }
  return response;
}
