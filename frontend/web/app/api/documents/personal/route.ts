import { NextRequest, NextResponse } from 'next/server';

import { documentServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * My Documents proxy (SCRUM-188) — document-service `/documents/personal`.
 *
 * ⚠️ Note the path: `/documents/personal`, NOT `/documents/mine`. That one is
 * the SELLER documents list (every document across the caller's listings,
 * SCRUM-98) — a different collection with a different owner model.
 *
 * The multipart body is re-sent as parsed FormData so fetch sets its own
 * boundary, matching the PoA and avatar proxies.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) {
    return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  }

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${documentServiceUrl()}/documents/personal`, {
      method: 'POST',
      headers: { authorization: `Bearer ${token}` },
      body: form,
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'DOCUMENT_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) {
    return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  }

  // Forward only the one parameter the endpoint accepts, rather than passing
  // the caller's query string through untouched.
  const category = request.nextUrl.searchParams.get('category');
  const suffix = category ? `?category=${encodeURIComponent(category)}` : '';

  let resp: Response;
  try {
    resp = await fetch(`${documentServiceUrl()}/documents/personal${suffix}`, {
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'DOCUMENT_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
