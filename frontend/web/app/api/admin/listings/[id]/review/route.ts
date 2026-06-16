import { NextRequest, NextResponse } from 'next/server';

import { listingServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Proxy for the admin listing-review decision (SCRUM-60). The browser posts
 * here; we attach the access token from the httpOnly cookie and call
 * listing-service POST /admin/listings/{id}/review, passing its status + error
 * code straight back so the UI can message 404 / 422 precisely.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });
  }

  let payload: { action?: unknown; comment?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  const action = payload.action === 'approve' || payload.action === 'reject' ? payload.action : null;
  if (!action) {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }
  const comment = typeof payload.comment === 'string' ? payload.comment : undefined;

  let resp: Response;
  try {
    resp = await fetch(`${listingServiceUrl()}/admin/listings/${params.id}/review`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body: JSON.stringify({ action, comment }),
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
