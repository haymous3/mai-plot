import { NextRequest, NextResponse } from 'next/server';

import { realtorServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Same-origin multipart proxy for inspection-report submission (SCRUM-140). The
 * report wizard posts its checklist fields + photos here; we forward the
 * FormData to realtor-service POST /inspections/{id}/report with the realtor's
 * session token. Multipart, so we re-send the parsed FormData (fetch sets the
 * boundary) rather than JSON. The backend enforces accepted+on/after-date, GPS
 * within 1km, and the photo minimum.
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
      `${realtorServiceUrl()}/inspections/${encodeURIComponent(params.id)}/report`,
      { method: 'POST', headers: { authorization: `Bearer ${token}` }, body: form, cache: 'no-store' },
    );
  } catch {
    return NextResponse.json({ error_code: 'REALTOR_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
