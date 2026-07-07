import { NextRequest, NextResponse } from 'next/server';

import { backendLogin } from '@/lib/api';
import {
  SESSION_ACCESS_COOKIE,
  SESSION_REFRESH_COOKIE,
  isNonAdminRole,
  roleHome,
} from '@/lib/session';

/**
 * Shared non-admin login proxy (SCRUM-98). One login for buyer/seller/realtor:
 * authenticate via auth-service, reject admins (they use the admin surface),
 * store the tokens in httpOnly session cookies, and return the caller's role
 * home so the client can route there. Replaces the buyer-only /api/buyer/login.
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
    return NextResponse.json({ error: result.code }, { status: result.status === 502 ? 502 : 401 });
  }
  if (!isNonAdminRole(result.role)) {
    return NextResponse.json({ error: 'NOT_ALLOWED' }, { status: 403 });
  }

  const response = NextResponse.json({ ok: true, role: result.role, redirect: roleHome(result.role) });
  const secure = process.env.NODE_ENV === 'production';
  response.cookies.set(SESSION_ACCESS_COOKIE, result.accessToken, {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    path: '/',
    maxAge: FIFTEEN_MINUTES,
  });
  response.cookies.set(SESSION_REFRESH_COOKIE, result.refreshToken, {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    path: '/',
    maxAge: SEVEN_DAYS,
  });
  return response;
}
