import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Buyer BVN-verify proxy for the onboarding flow (SCRUM-185).
 *
 * ⚠️ WHY THIS EXISTS ALONGSIDE `/api/buyer/bvn-verify`, which hits the same
 * upstream endpoint: the two read DIFFERENT cookies. `/api/buyer/*` uses
 * `BUYER_ACCESS_COOKIE` via `buyerBackendSend`, which is set when a buyer signs
 * in; onboarding runs on `SESSION_ACCESS_COOKIE`, set by /auth/verify/email and
 * /auth/otp/verify. Reusing the buyer route here would 401 every time, because
 * the buyer cookie does not exist yet.
 *
 * This mirrors `/api/auth/seller/nin`, which SCRUM-132 added for exactly the
 * same reason on the seller side.
 *
 * The BVN is never persisted or logged here — it passes straight through to
 * auth-service, which stores only a bcrypt hash (CLAUDE.md §4).
 *
 * NOTE ON THE DESIGN: the export asks buyers for a NIN, but /auth/verify/nin is
 * hard-gated to sellers with owner authority (403 NIN_NOT_ELIGIBLE). BVN is the
 * buyer identity check and has no role gate. Product owner confirmed the swap.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) {
    return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  }

  let payload: { bvn?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }
  const bvn = typeof payload.bvn === 'string' ? payload.bvn : '';

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/verify/bvn`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body: JSON.stringify({ bvn }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'AUTH_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
