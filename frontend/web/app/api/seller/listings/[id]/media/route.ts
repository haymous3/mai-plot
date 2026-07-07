import { NextRequest, NextResponse } from 'next/server';

import { listingServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Seller media-upload proxy (SCRUM-98). Forwards a multipart image/video to
 * listing-service POST /listings/{id}/media (re-sending the parsed FormData so
 * fetch sets a fresh multipart boundary).
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  let resp: Response;
  try {
    resp = await fetch(
      `${listingServiceUrl()}/listings/${encodeURIComponent(params.id)}/media`,
      { method: 'POST', headers: { authorization: `Bearer ${token}` }, body: form, cache: 'no-store' },
    );
  } catch {
    return NextResponse.json({ error_code: 'LISTING_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
