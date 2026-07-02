import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { isNonAdminRole } from '@/lib/session';

/**
 * Registration proxy (SCRUM-132). Forwards {phone, role, email?} to auth-service
 * /auth/register, which creates the user and sends the OTP. No password here —
 * it's set after OTP verify (POST /api/auth/set-password). Only non-admin roles
 * may self-register.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let payload: { phone?: unknown; role?: unknown; email?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  const phone = typeof payload.phone === 'string' ? payload.phone : '';
  const role = typeof payload.role === 'string' ? payload.role : '';
  const email = typeof payload.email === 'string' ? payload.email : undefined;
  if (!phone || !isNonAdminRole(role)) {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/register`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ phone, role, email }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'AUTH_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
