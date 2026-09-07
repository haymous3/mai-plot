import { NextRequest, NextResponse } from 'next/server';

import { realtorServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Proxy for placing a waiting inspection with a realtor (SCRUM-208). Attaches
 * the admin access token from the httpOnly cookie and calls realtor-service
 * POST /admin/inspections/{id}/assign, passing its status + error code back so
 * the UI can tell 404 (gone) from 409 (someone else placed it first) from 422
 * (that realtor is not approved).
 *
 * The 409 matters most: two admins working the same queue is the normal case,
 * and "already has a realtor" has to read as "refresh", not as a failure.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });
  }

  let payload: { realtor_id?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }
  const realtorId = typeof payload.realtor_id === 'string' ? payload.realtor_id : null;
  if (!realtorId) {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${realtorServiceUrl()}/admin/inspections/${params.id}/assign`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body: JSON.stringify({ realtor_id: realtorId }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }

  if (!resp.ok) {
    let code = 'ASSIGN_FAILED';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // keep the default
    }
    return NextResponse.json({ error: code }, { status: resp.status });
  }

  return NextResponse.json(await resp.json());
}
