import { NextRequest, NextResponse } from 'next/server';

import { documentServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Streams a document through to the reviewer's viewer (SCRUM-192). Reads the
 * httpOnly cookie token and proxies document-service
 * GET /admin/documents/{id}/file, passing the bytes straight back — the object
 * is never exposed via a public or pre-signed URL, and access stays auth-gated
 * end to end. Mirrors the PoA document proxy (SCRUM-61).
 *
 * Note this is NOT /api/documents/personal/{id}/view: that one serves the
 * owner their own document and only when verified. A reviewer needs the
 * unverified ones, which is the whole point of the admin route behind this.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });
  }

  // Only ever the two known values — an unrecognised source is not forwarded,
  // so a crafted query string cannot probe the backend's routing.
  const requested = request.nextUrl.searchParams.get('source');
  const source = requested === 'personal' ? 'personal' : 'listing';

  let resp: Response;
  try {
    resp = await fetch(
      `${documentServiceUrl()}/admin/documents/${params.id}/file?source=${source}`,
      {
        headers: { authorization: `Bearer ${token}` },
        cache: 'no-store',
      },
    );
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }

  if (!resp.ok) {
    let code = 'DOCUMENT_FAILED';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // keep default
    }
    return NextResponse.json({ error: code }, { status: resp.status });
  }

  const body = await resp.arrayBuffer();
  return new NextResponse(body, {
    status: 200,
    headers: {
      'content-type': resp.headers.get('content-type') ?? 'application/octet-stream',
      // Render inline in the viewer; never index or cache a private document.
      'content-disposition': 'inline',
      'cache-control': 'private, no-store',
      // The backend already pins the content type to pdf/jpeg/png; repeat
      // nosniff here because this response is what the browser actually sees.
      'x-content-type-options': 'nosniff',
    },
  });
}
