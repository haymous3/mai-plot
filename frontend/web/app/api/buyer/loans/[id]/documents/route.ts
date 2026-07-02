import { NextRequest, NextResponse } from 'next/server';

import { documentServiceUrl } from '@/lib/api';
import { buyerAccessToken } from '@/lib/buyer-server-api';

/**
 * Same-origin multipart proxy for buyer loan-document upload (SCRUM-131).
 * Forwards the wizard's file + document_type to document-service
 * POST /loans/{id}/documents with the server-side buyer token. Multipart, so we
 * re-send the parsed FormData (fetch sets the boundary) rather than JSON.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = buyerAccessToken();
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
    resp = await fetch(
      `${documentServiceUrl()}/loans/${encodeURIComponent(params.id)}/documents`,
      { method: 'POST', headers: { authorization: `Bearer ${token}` }, body: form, cache: 'no-store' },
    );
  } catch {
    return NextResponse.json({ error_code: 'DOCUMENT_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
