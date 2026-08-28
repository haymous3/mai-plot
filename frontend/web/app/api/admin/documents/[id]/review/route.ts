import { NextRequest, NextResponse } from 'next/server';

import { documentServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Proxy for the document verify/reject decision (SCRUM-192). Attaches the
 * access token from the httpOnly cookie and calls document-service
 * POST /admin/documents/{id}/review, passing its status + error code back so
 * the UI can message 404 / 422.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });
  }

  let payload: { action?: unknown; source?: unknown; notes?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  const action = payload.action === 'verify' || payload.action === 'reject' ? payload.action : null;
  if (!action) {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }
  // Defaults to "listing" exactly as the backend does, so a malformed source
  // cannot silently redirect a decision at the wrong table.
  const source = payload.source === 'personal' ? 'personal' : 'listing';
  const notes = typeof payload.notes === 'string' ? payload.notes : undefined;

  let resp: Response;
  try {
    resp = await fetch(`${documentServiceUrl()}/admin/documents/${params.id}/review`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body: JSON.stringify({ action, source, notes }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }

  if (!resp.ok) {
    let code = 'REVIEW_FAILED';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // keep default
    }
    return NextResponse.json({ error: code }, { status: resp.status });
  }

  return NextResponse.json({ ok: true });
}
