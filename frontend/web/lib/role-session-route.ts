import { NextRequest, NextResponse } from 'next/server';

import { backendRoleSession, isSwitchableRole } from '@/lib/api';
import { SESSION_ACCESS_COOKIE, SESSION_REFRESH_COOKIE, roleHome } from '@/lib/session';
import { applySessionCookies } from '@/lib/session-cookies';

/**
 * The body of POST /api/auth/switch-role and /api/auth/add-role (SCRUM-236).
 *
 * Reads the session from the httpOnly cookies — the browser never holds either
 * token — calls auth-service, and replaces the cookies with the pair for the
 * account now in use. The refresh token being left is sent along so the backend
 * revokes it; without that every switch would leave a live 7-day token behind.
 *
 * `redirect` is where the client goes next: the role's home for a switch, and
 * onboarding for a brand-new account, which still has that role's own steps
 * (a seller declares owner / power of attorney there).
 */
export async function roleSessionRoute(
  request: NextRequest,
  action: 'switch-role' | 'add-role',
): Promise<NextResponse> {
  let payload: { role?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }
  if (!isSwitchableRole(payload.role)) {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  const accessToken = request.cookies.get(SESSION_ACCESS_COOKIE)?.value;
  if (!accessToken) {
    return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });
  }
  const refreshToken = request.cookies.get(SESSION_REFRESH_COOKIE)?.value ?? null;

  const result = await backendRoleSession(action, accessToken, payload.role, refreshToken);
  if (!result.ok) {
    return NextResponse.json({ error: result.code }, { status: result.status });
  }

  const redirect = action === 'add-role' ? '/onboarding' : roleHome(result.role);
  return applySessionCookies(
    NextResponse.json({ ok: true, role: result.role, redirect }),
    result.accessToken,
    result.refreshToken,
  );
}
