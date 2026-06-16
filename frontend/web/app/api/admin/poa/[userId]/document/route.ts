import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Streams a PoA document through to the legal-team viewer (SCRUM-61). Reads the
 * httpOnly cookie token and proxies auth-service GET /admin/poa/{user_id}/document,
 * passing the bytes + content-type straight back — the document is never exposed
 * via a public/pre-signed URL, and access stays auth-gated end to end.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { userId: string } },
): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/admin/poa/${params.userId}/document`, {
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
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
      // Render inline in the viewer; never index a private legal document.
      'content-disposition': 'inline',
      'cache-control': 'private, no-store',
    },
  });
}
