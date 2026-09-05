import { NextRequest, NextResponse } from 'next/server';

import { realtorServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Same-origin multipart proxy for realtor onboarding (SCRUM-132). The
 * "Realtor Profile" onboarding step posts its coverage area and credentials
 * document here (no ESVARBON number since SCRUM-207 — the realtor is verified
 * by an admin and issued a registration number instead); we forward the
 * FormData to realtor-service
 * POST /realtors with the session access token (role=realtor JWT). Multipart, so
 * we re-send the parsed FormData (fetch sets the boundary) rather than JSON.
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
    resp = await fetch(`${realtorServiceUrl()}/realtors`, {
      method: 'POST',
      headers: { authorization: `Bearer ${token}` },
      body: form,
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'REALTOR_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
