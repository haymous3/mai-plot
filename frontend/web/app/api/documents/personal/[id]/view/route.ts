import { NextResponse } from 'next/server';

import { documentServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Mint a short-TTL pre-signed URL for one of the caller's own documents
 * (SCRUM-188).
 *
 * Returns the URL rather than redirecting to it: a redirect would put the
 * signed URL in the browser's history and the referrer chain, and it expires
 * in minutes. The client opens it directly instead.
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) {
    return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  }

  const { id } = await params;
  let resp: Response;
  try {
    resp = await fetch(
      `${documentServiceUrl()}/documents/personal/${encodeURIComponent(id)}/view`,
      { headers: { authorization: `Bearer ${token}` }, cache: 'no-store' },
    );
  } catch {
    return NextResponse.json({ error_code: 'DOCUMENT_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
