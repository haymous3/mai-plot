import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { SESSION_ACCESS_COOKIE, SESSION_REFRESH_COOKIE } from '@/lib/session';

/**
 * Finish a password reset (SCRUM-191). Proxies auth-service
 * POST /auth/password/reset. The token arrives in the BODY, not the query
 * string, so it never lands in server access logs — same reasoning as
 * /api/auth/verify-email.
 *
 * Unlike that route this one sets NO session cookies: the backend deliberately
 * issues no JWT pair, because whoever holds the link may be an attacker who
 * reached the mailbox, and a live session would outlive the real owner's
 * counter-reset. The user signs in with the new password instead.
 *
 * It does the opposite — it CLEARS any session cookies this browser still
 * holds. A reset revokes every refresh token server-side, so a cookie sitting
 * here is already dead; leaving it would put the browser in a half-signed-in
 * state where the shell renders but every request 401s.
 *
 * Error codes bubble through so the page can tell an expired link from an
 * invalid one from a password the server judged too weak:
 * RESET_TOKEN_EXPIRED | RESET_TOKEN_INVALID | PASSWORD_TOO_WEAK.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let payload: { token?: unknown; new_password?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  const token = typeof payload.token === 'string' ? payload.token : '';
  const newPassword = typeof payload.new_password === 'string' ? payload.new_password : '';
  if (!token || !newPassword) {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/password/reset`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ token, new_password: newPassword }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error: 'AUTH_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = (await resp.json().catch(() => ({}))) as {
    message?: string;
    error_code?: string;
  };

  if (!resp.ok) {
    return NextResponse.json(
      { error: body.error_code ?? 'RESET_TOKEN_INVALID' },
      { status: resp.status },
    );
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.delete(SESSION_ACCESS_COOKIE);
  response.cookies.delete(SESSION_REFRESH_COOKIE);
  return response;
}
