import { NextRequest, NextResponse } from 'next/server';

import { listingServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

const ACTIONS = new Set(['pause', 'unpause', 'take_down', 'expire']);

/**
 * Proxy for acting on a live listing (SCRUM-215). Attaches the admin access
 * token from the httpOnly cookie and calls listing-service
 * POST /admin/listings/{id}/status, passing its status + error code straight
 * back.
 *
 * Two codes matter to the UI and must not be flattened into one another:
 * `LISTING_UNDER_OFFER` (422) means a live deal is holding the listing and the
 * admin has to resolve the transaction, while `LISTING_STATUS_CONFLICT` (409)
 * means somebody else already moved it and a refresh is the fix.
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
  const action = typeof payload.action === 'string' ? payload.action : '';
  if (!ACTIONS.has(action)) {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }
  const reason = typeof payload.reason === 'string' ? payload.reason : undefined;

  let resp: Response;
  try {
    resp = await fetch(`${listingServiceUrl()}/admin/listings/${params.id}/status`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body: JSON.stringify({ action, reason }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }

  if (!resp.ok) {
    let code = 'ACTION_FAILED';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // keep the default
    }
    return NextResponse.json({ error: code }, { status: resp.status });
  }

  return NextResponse.json(await resp.json());
}
