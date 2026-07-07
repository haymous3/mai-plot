import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Buyer-profile proxy (SCRUM-132). The buyer onboarding "Personal Information"
 * screen posts optional buying-capacity fields (employment status, preferred
 * location, budget in kobo); we forward them to auth-service
 * POST /auth/buyer/profile with the session bearer.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) {
    return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  }

  let payload: {
    employment_status?: unknown;
    preferred_location?: unknown;
    budget_kobo?: unknown;
  };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error_code: 'INVALID_REQUEST' }, { status: 400 });
  }
  const body = {
    employment_status:
      typeof payload.employment_status === 'string' ? payload.employment_status : null,
    preferred_location:
      typeof payload.preferred_location === 'string' ? payload.preferred_location : null,
    budget_kobo: typeof payload.budget_kobo === 'number' ? payload.budget_kobo : null,
  };

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/buyer/profile`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'AUTH_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const respBody = await resp.json().catch(() => ({}));
  return NextResponse.json(respBody, { status: resp.status });
}
