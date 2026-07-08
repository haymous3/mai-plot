import { NextResponse } from 'next/server';

import { documentServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Seller document-view proxy (SCRUM-98). Streams the watermarked bytes from
 * document-service GET /documents/{id}/view with the session bearer. Only
 * verified documents are viewable; others return the upstream 403/404 JSON.
 */
export async function GET(
  _req: Request,
  { params }: { params: { id: string } },
): Promise<Response> {
  const token = sessionAccessToken();
  if (!token) return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });

  let resp: Response;
  try {
    resp = await fetch(
      `${documentServiceUrl()}/documents/${encodeURIComponent(params.id)}/view`,
      { headers: { authorization: `Bearer ${token}` }, cache: 'no-store' },
    );
  } catch {
    return NextResponse.json({ error_code: 'DOCUMENT_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const contentType = resp.headers.get('content-type') ?? 'application/octet-stream';
  const body = await resp.arrayBuffer();
  return new Response(body, { status: resp.status, headers: { 'content-type': contentType } });
}
