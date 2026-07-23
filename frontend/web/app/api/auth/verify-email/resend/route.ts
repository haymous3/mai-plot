import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';

/**
 * Resend the verification magic link (SCRUM-157; backend SCRUM-154). Public —
 * the caller isn't verified yet. Proxies auth-service
 * POST /auth/verify/email/resend, which answers a generic 202 whether or not
 * the address has an unverified account (no enumeration); we mirror that and
 * pass the 429 / 422 codes through so the page can message them.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let payload: { email?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  const email = typeof payload.email === 'string' ? payload.email : '';
  if (!email) {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/verify/email/resend`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ email }),
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
