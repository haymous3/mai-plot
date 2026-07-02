import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { buyerBackendSend } from '@/lib/buyer-server-api';

/** Same-origin proxy for BVN verification (SCRUM-94, step 1 of the loan wizard).
 * Forwards {bvn} to auth-service POST /auth/verify/bvn with the buyer token. The
 * BVN is never persisted here and never logged — it passes straight through to
 * auth-service, which stores only a bcrypt hash. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let payload: { bvn?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }
  const bvn = typeof payload.bvn === 'string' ? payload.bvn : '';

  const { status, body } = await buyerBackendSend('POST', `${authServiceUrl()}/auth/verify/bvn`, {
    bvn,
  });
  return NextResponse.json(body, { status });
}
