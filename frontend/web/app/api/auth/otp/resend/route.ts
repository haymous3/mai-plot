import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';

/**
 * Resend the registration OTP (backend SCRUM-176). Public — the caller isn't
 * verified yet. Proxies auth-service POST /auth/otp/resend, which answers a
 * generic 202 whether or not the number has an unverified account (no
 * enumeration); we mirror that and pass the 429 / 422 codes through so the
 * page can message them.
 *
 * Mirrors app/api/auth/verify-email/resend — same contract, different channel.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let payload: { phone?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  const phone = typeof payload.phone === 'string' ? payload.phone : '';
  if (!phone) {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/otp/resend`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ phone }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error: 'AUTH_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  if (resp.status === 202) {
    return NextResponse.json({ ok: true }, { status: 202 });
  }
  const body = (await resp.json().catch(() => ({}))) as { error_code?: string };
  return NextResponse.json({ error: body.error_code ?? 'RESEND_FAILED' }, { status: resp.status });
}
