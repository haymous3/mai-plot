import { NextRequest, NextResponse } from 'next/server';

import { realtorServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Proxy for creating an inspection on a deal (SCRUM-213). Attaches the admin
 * access token from the httpOnly cookie and calls realtor-service
 * POST /admin/inspections.
 *
 * `realtor_id` is required here even though the backend treats it as optional:
 * omitting it asks the service to pick by proximity, and no realtor onboarded
 * through the product has a base location, so that path answers 503 for
 * essentially every deal. This screen exists because an admin is choosing.
 *
 * The backend's error codes are passed through verbatim — 409
 * INSPECTION_ALREADY_ACTIVE is the one that matters, and it has to read as
 * "this deal already has one", not as a failure to act on.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: 'NO_SESSION' }, { status: 401 });
  }

  let payload: { transaction_id?: unknown; proposed_date?: unknown; realtor_id?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }
  const transactionId = typeof payload.transaction_id === 'string' ? payload.transaction_id : null;
  const proposedDate = typeof payload.proposed_date === 'string' ? payload.proposed_date : null;
  const realtorId = typeof payload.realtor_id === 'string' ? payload.realtor_id : null;
  if (!transactionId || !proposedDate || !realtorId) {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${realtorServiceUrl()}/admin/inspections`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body: JSON.stringify({
        transaction_id: transactionId,
        proposed_date: proposedDate,
        realtor_id: realtorId,
      }),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error: 'BACKEND_UNAVAILABLE' }, { status: 502 });
  }

  if (!resp.ok) {
    let code = 'CREATE_FAILED';
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
