import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Profile proxy (SCRUM-132). The onboarding "Personal details" screen posts the
 * full name (+ optional email) here after OTP verify established the session; we
 * forward it to auth-service /auth/profile with the session access token as
 * bearer (token stays server-side).
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) {
    return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  }

  let payload: { full_name?: unknown; email?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }
  const full_name = typeof payload.full_name === 'string' ? payload.full_name : '';
  const email = typeof payload.email === 'string' && payload.email ? payload.email : null;

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/profile`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body: JSON.stringify({ full_name, email }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'AUTH_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
