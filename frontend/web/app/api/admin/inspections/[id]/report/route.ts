import { NextRequest, NextResponse } from 'next/server';

import { realtorServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Proxy for reading a submitted report's body during review (SCRUM-205).
 *
 * There is no admin-specific read: realtor-service's
 * `GET /inspections/{id}/report` already admits `caller.role == "admin"`, so a
 * reviewer can open exactly what they are deciding on. (That was the SCRUM-192
 * document bug — the viewer served only already-verified files, even to the
 * admin deciding whether to verify them.)
 *
 * `photo_urls` come back as short-TTL pre-signed S3 URLs, so nothing is cached
 * here and the response is passed straight through.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${realtorServiceUrl()}/inspections/${params.id}/report`, {
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }

  if (!resp.ok) {
    let code = 'REPORT_UNAVAILABLE';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // keep default
    }
    return NextResponse.json({ error: code }, { status: resp.status });
  }

  return NextResponse.json(await resp.json());
}
