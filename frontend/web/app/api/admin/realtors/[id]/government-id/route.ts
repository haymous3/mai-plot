import { NextRequest, NextResponse } from 'next/server';

import { realtorServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Auth-gated viewer for a realtor's uploaded ID document (SCRUM-62). Reads the
 * httpOnly cookie token and calls realtor-service GET
 * /admin/realtors/{id}/government-id, which mints a short-TTL pre-signed S3 URL
 * (the document is never public) and audits the access. We redirect the viewer
 * (iframe) to that signed URL so S3/CloudFront serves the bytes directly. On
 * error we pass the backend status + code straight back.
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
    resp = await fetch(`${realtorServiceUrl()}/admin/realtors/${params.id}/government-id`, {
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

  const body = (await resp.json()) as { url?: string };
  if (!body.url) {
    return NextResponse.json({ error: 'DOCUMENT_FAILED' }, { status: 502 });
  }
  return NextResponse.redirect(body.url, { status: 302, headers: { 'cache-control': 'private, no-store' } });
}
