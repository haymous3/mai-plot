import { NextResponse } from 'next/server';

import { documentServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/** Delete one of the caller's personal documents (SCRUM-188). */
export async function DELETE(
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
    resp = await fetch(`${documentServiceUrl()}/documents/personal/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'DOCUMENT_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
