import { NextRequest, NextResponse } from 'next/server';

import { backendLogin } from '@/lib/api';
import { BUYER_ACCESS_COOKIE, BUYER_HOME, BUYER_REFRESH_COOKIE, isBuyerRole } from '@/lib/buyer-auth';

/**
 * Buyer login proxy (SCRUM-94). The browser posts credentials here (same
 * origin); we call auth-service, enforce that the account is a buyer, and on
 * success store the tokens in httpOnly cookies. The token is never returned to
 * client JS. Temporary gate — the designed auth screens land in a later ticket.
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

  if (!isBuyerRole(result.role)) {
    return NextResponse.json({ error: 'NOT_BUYER' }, { status: 403 });
  }

  const response = NextResponse.json({ ok: true, redirect: BUYER_HOME });
  const secure = process.env.NODE_ENV === 'production';
  response.cookies.set(BUYER_ACCESS_COOKIE, result.accessToken, {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    path: '/',
    maxAge: FIFTEEN_MINUTES,
  });
  response.cookies.set(BUYER_REFRESH_COOKIE, result.refreshToken, {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    path: '/',
    maxAge: SEVEN_DAYS,
  });
  return response;
}
