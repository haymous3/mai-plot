import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { isNonAdminRole } from '@/lib/session';

/**
 * Registration proxy (SCRUM-132 → reworked SCRUM-155). Forwards the account
 * fields to auth-service /auth/register, which creates the user and emails a
 * verification magic link (SCRUM-152). email is now REQUIRED and password is
 * captured here (no post-OTP set-password step exists anymore). Only non-admin
 * roles may self-register. No session is returned — it's established when the
 * user clicks the email link (/verify-email).
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let payload: {
    phone?: unknown;
    role?: unknown;
    email?: unknown;
    password?: unknown;
    full_name?: unknown;
    seller_authority_type?: unknown;
  };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  const phone = typeof payload.phone === 'string' ? payload.phone : '';
  const role = typeof payload.role === 'string' ? payload.role : '';
  const email = typeof payload.email === 'string' ? payload.email : '';
  if (!phone || !email || !isNonAdminRole(role)) {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  // Only forward the optional fields when present — auth-service treats missing
  // password/full_name as absent, and seller_authority_type is seller-only.
  const forward: Record<string, unknown> = { phone, role, email };
  if (typeof payload.password === 'string' && payload.password) forward.password = payload.password;
  if (typeof payload.full_name === 'string' && payload.full_name) forward.full_name = payload.full_name;
  if (role === 'seller' && typeof payload.seller_authority_type === 'string') {
    forward.seller_authority_type = payload.seller_authority_type;
  }

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/register`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(forward),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'AUTH_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
