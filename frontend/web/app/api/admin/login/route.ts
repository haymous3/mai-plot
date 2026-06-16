import { NextRequest, NextResponse } from 'next/server';

import { backendLogin } from '@/lib/api';
import { ACCESS_COOKIE, ADMIN_HOME, isAdminRole, REFRESH_COOKIE } from '@/lib/auth';

/**
 * Admin login proxy (SCRUM-59). The browser posts credentials here (same
 * origin); we call auth-service, enforce that the account is an admin/legal_team
 * role, and on success store the tokens in httpOnly cookies. The token is never
 * returned to client JS.
 *
 * Failed-login auditing (writing audit_log) is a backend concern handled in
 * auth-service — tracked separately (SCRUM-116).
 */
const FIFTEEN_MINUTES = 15 * 60;
const SEVEN_DAYS = 7 * 24 * 60 * 60;

export async function POST(request: NextRequest): Promise<NextResponse> {
  let payload: { email?: unknown; password?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  const email = typeof payload.email === 'string' ? payload.email : '';
  const password = typeof payload.password === 'string' ? payload.password : '';
  if (!email || !password) {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  const result = await backendLogin(email, password);
  if (!result.ok) {
    const status = result.status === 502 ? 502 : 401;
    return NextResponse.json({ error: result.code }, { status });
  }

  if (!isAdminRole(result.role)) {
    // Valid credentials, but not an admin account — this is an admin surface.
    return NextResponse.json({ error: 'NOT_ADMIN' }, { status: 403 });
  }

  const response = NextResponse.json({ ok: true, redirect: ADMIN_HOME });
  const secure = process.env.NODE_ENV === 'production';
  response.cookies.set(ACCESS_COOKIE, result.accessToken, {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    path: '/',
    maxAge: FIFTEEN_MINUTES,
  });
  response.cookies.set(REFRESH_COOKIE, result.refreshToken, {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    path: '/',
    maxAge: SEVEN_DAYS,
  });
  return response;
}
