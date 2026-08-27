import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { buyerBackendSend } from '@/lib/buyer-server-api';

/**
 * Same-origin proxy for NIN verification (SCRUM-189, replaces the BVN route).
 *
 * Forwards {nin} to auth-service POST /auth/verify/nin with the session token.
 * The NIN is never persisted here and never logged — it passes straight through
 * to auth-service, which stores only a bcrypt hash plus a peppered HMAC lookup
 * (CLAUDE.md §4).
 *
 * ⚠️ This endpoint only became usable by non-owner-sellers in SCRUM-189, which
 * removed the `role == seller AND authority == owner` gate on
 * /auth/verify/nin. Before that a buyer was hard-403'd here, which is the whole
 * reason the funnel used to collect a BVN.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let payload: { nin?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }
  const nin = typeof payload.nin === 'string' ? payload.nin : '';

  const { status, body } = await buyerBackendSend('POST', `${authServiceUrl()}/auth/verify/nin`, {
    nin,
  });
  return NextResponse.json(body, { status });
}
