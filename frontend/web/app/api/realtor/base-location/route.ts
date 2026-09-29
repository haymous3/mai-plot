import { NextRequest, NextResponse } from 'next/server';

import { realtorServiceUrl } from '@/lib/api';
import { isInNigeria } from '@/lib/nigeria-areas';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Set the signed-in realtor's base location (SCRUM-214) — realtor-service
 * `PUT /realtors/me/base-location`. Forwards `lat` + `lng` only, as numbers,
 * and refuses a point outside Nigeria before spending the round trip (the
 * service enforces the same bounds).
 */
export async function PUT(request: NextRequest): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });

  let payload: { lat?: unknown; lng?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }
  const { lat, lng } = payload;
  if (typeof lat !== 'number' || typeof lng !== 'number' || !Number.isFinite(lat + lng)) {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }
  if (!isInNigeria(lat, lng)) {
    return NextResponse.json({ error_code: 'LOCATION_OUTSIDE_NIGERIA' }, { status: 422 });
  }

  try {
    const resp = await fetch(`${realtorServiceUrl()}/realtors/me/base-location`, {
      method: 'PUT',
      headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
      body: JSON.stringify({ lat, lng }),
      cache: 'no-store',
    });
    const body = await resp.json().catch(() => ({}));
    return NextResponse.json(body, { status: resp.status });
  } catch {
    return NextResponse.json({ error_code: 'REALTOR_SERVICE_UNAVAILABLE' }, { status: 502 });
  }
}
