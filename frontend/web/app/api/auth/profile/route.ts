import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Profile proxy (SCRUM-132). The onboarding "Personal details" screen posts the
 * full name (+ optional email) here after OTP verify established the session; we
 * forward it to auth-service /auth/profile with the session access token as
 * bearer (token stays server-side).
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) {
    return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  }

  let payload: {
    full_name?: unknown;
    first_name?: unknown;
    last_name?: unknown;
    email?: unknown;
    location?: unknown;
    address?: unknown;
  };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }

  // ⚠️ THIS IS A WHITELIST, AND IT HAD BEEN LOSING DATA SINCE SCRUM-201.
  // Written for SCRUM-132 to forward `full_name` and `email`, and never
  // widened when SCRUM-193 added `location` and SCRUM-201 added `address` —
  // so every address typed into onboarding was accepted with a 200 and
  // discarded here. Found while adding the name parts (SCRUM-231). A field
  // not named below reaches nothing, with no error anywhere.
  //
  // `location` and `address` are forwarded ONLY when present: auth-service
  // distinguishes "omitted, leave it alone" from "sent as empty, clear it"
  // (pydantic `model_fields_set`), and forwarding a default would collapse
  // the two and make a saved address impossible to keep on an unrelated edit.
  const forward: Record<string, unknown> = {};
  if (typeof payload.full_name === 'string') forward.full_name = payload.full_name;
  if (typeof payload.first_name === 'string') forward.first_name = payload.first_name;
  if (typeof payload.last_name === 'string') forward.last_name = payload.last_name;
  forward.email = typeof payload.email === 'string' && payload.email ? payload.email : null;
  if ('location' in payload) forward.location = payload.location;
  if ('address' in payload) forward.address = payload.address;

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/profile`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body: JSON.stringify(forward),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'AUTH_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
