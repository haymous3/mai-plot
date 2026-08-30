import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * NIN verification proxy, for any role (SCRUM-201).
 *
 * `/auth/verify/nin` has had NO role gate since SCRUM-189 — NIN is the
 * platform-wide identity check — so a realtor can use it exactly as a buyer or
 * seller does. This route exists because the two that already forward to it are
 * named for the roles that happened to need them first
 * (`/api/auth/seller/nin`, `/api/buyer/nin-verify`), and pointing the realtor
 * step at either would have been misleading rather than merely untidy.
 *
 * ⚠️ Those two are now duplicates of this one. Collapsing them wants its own
 * ticket: both are live in the buyer and seller flows, and the tidy-up has no
 * bearing on the realtor gap this closes.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) {
    return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  }

  let payload: { nin?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }
  if (typeof payload.nin !== 'string') {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/verify/nin`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      // Only the NIN is forwarded, never the whole body — the value is
      // bcrypt-hashed server-side and must not pick up passengers here.
      body: JSON.stringify({ nin: payload.nin }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'AUTH_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
