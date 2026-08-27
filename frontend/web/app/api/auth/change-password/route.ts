import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { SESSION_ACCESS_COOKIE, SESSION_REFRESH_COOKIE } from '@/lib/session';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Change-password proxy for the Settings Security tab (SCRUM-188).
 *
 * ⚠️ CLEARS THE SESSION COOKIES ON SUCCESS. auth-service revokes every refresh
 * token when the password changes, so the cookies this browser holds are
 * already dead in every way that matters: the refresh token is revoked, and the
 * access token merely has not expired yet. Leaving them set would hand the user
 * a session that looks live and then fails confusingly a few minutes later.
 * Clearing here lets the UI send them straight to sign-in, which is what the
 * endpoint's own message tells them to do.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) {
    return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  }

  let payload: { current_password?: unknown; new_password?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/change-password`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        current_password:
          typeof payload.current_password === 'string' ? payload.current_password : '',
        new_password: typeof payload.new_password === 'string' ? payload.new_password : '',
      }),
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
