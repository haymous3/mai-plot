import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { isOnboardingRole } from '@/lib/onboarding-steps';
import { roleHome, SESSION_ACCESS_COOKIE, SESSION_REFRESH_COOKIE } from '@/lib/session';

/**
 * Registration OTP-verify proxy (SCRUM-132). Forwards {phone, otp} to
 * auth-service /auth/otp/verify; on success the returned tokens establish the
 * shared non-admin session (httpOnly cookies) and we hand back the role's home.
 * The tokens never reach client JS.
 */
const FIFTEEN_MINUTES = 15 * 60;
const SEVEN_DAYS = 7 * 24 * 60 * 60;

export async function POST(request: NextRequest): Promise<NextResponse> {
  let payload: { phone?: unknown; otp?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  const phone = typeof payload.phone === 'string' ? payload.phone : '';
  const otp = typeof payload.otp === 'string' ? payload.otp : '';
  if (!phone || !otp) {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/otp/verify`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ phone, otp, purpose: 'registration' }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'AUTH_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = (await resp.json().catch(() => ({}))) as {
    access_token?: string;
    refresh_token?: string;
    user?: { role?: string };
    error_code?: string;
  };
  if (!resp.ok || !body.access_token || !body.refresh_token) {
    return NextResponse.json(body, { status: resp.ok ? 502 : resp.status });
  }

  const role = body.user?.role ?? 'buyer';
  // SCRUM-185: verification now hands off to onboarding rather than straight to
  // the dashboard. Roles that are provisioned rather than signed up (admin,
  // legal_team, bank_partner) have no onboarding and still go to their own home.
  const destination = isOnboardingRole(role) ? '/onboarding' : roleHome(role);
  const response = NextResponse.json({ ok: true, role, redirect: destination });
  const secure = process.env.NODE_ENV === 'production';
  response.cookies.set(SESSION_ACCESS_COOKIE, body.access_token, {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    path: '/',
    maxAge: FIFTEEN_MINUTES,
  });
  response.cookies.set(SESSION_REFRESH_COOKIE, body.refresh_token, {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    path: '/',
    maxAge: SEVEN_DAYS,
  });
  return response;
}
