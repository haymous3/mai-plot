import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';

/**
 * Start a password reset (SCRUM-191). Public — the caller cannot sign in, which
 * is the whole point. Proxies auth-service POST /auth/password/forgot.
 *
 * That endpoint answers a byte-identical 202 whether or not the address has an
 * account, so it cannot be used to enumerate users. This route mirrors that
 * exactly: it must never branch on whether the address was known, because a
 * difference here would reintroduce through the BFF precisely what the API
 * refuses to leak. Only the 429 / 422 codes pass through, so the page can
 * message a rate limit or a malformed address.
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
    resp = await fetch(`${authServiceUrl()}/auth/password/forgot`, {
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
  return NextResponse.json({ error: body.error_code ?? 'FORGOT_FAILED' }, { status: resp.status });
}
