import { NextRequest, NextResponse } from 'next/server';

import { realtorServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Proxy for the realtor review decision (SCRUM-62). Attaches the access token
 * from the httpOnly cookie and calls realtor-service POST
 * /admin/realtors/{id}/review, passing its status + error code back so the UI can
 * message 404/409/422. Only approve/reject are offered in the queue (suspend
 * applies to already-approved realtors, which never appear here).
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });
  }

  let payload: { action?: unknown; reason?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  const action = payload.action === 'approve' || payload.action === 'reject' ? payload.action : null;
  if (!action) {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }
  const reason = typeof payload.reason === 'string' ? payload.reason : undefined;

  let resp: Response;
  try {
    resp = await fetch(`${realtorServiceUrl()}/admin/realtors/${params.id}/review`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body: JSON.stringify({ action, reason }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }

  if (!resp.ok) {
    let code = 'REVIEW_FAILED';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // keep default
    }
    return NextResponse.json({ error: code }, { status: resp.status });
  }

  return NextResponse.json({ ok: true });
}
