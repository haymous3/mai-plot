import { NextRequest, NextResponse } from 'next/server';

import { listingServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Seller edit-listing proxy (SCRUM-98). Forwards a partial JSON update to
 * listing-service PATCH /listings/{id} with the session bearer.
 */
export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });

  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${listingServiceUrl()}/listings/${encodeURIComponent(params.id)}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'LISTING_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
