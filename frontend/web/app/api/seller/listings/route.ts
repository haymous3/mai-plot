import { NextRequest, NextResponse } from 'next/server';

import { listingServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Seller create-listing proxy (SCRUM-98). Forwards the wizard's JSON payload to
 * listing-service POST /listings with the session bearer. Create returns the new
 * listing_id, which the wizard then uses to upload media + documents.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
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
    resp = await fetch(`${listingServiceUrl()}/listings`, {
      method: 'POST',
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
