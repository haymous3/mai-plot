import { NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { sessionAccessToken } from '@/lib/session-server';

/**
 * Account read for the Settings screens (SCRUM-188).
 *
 * Proxies auth-service `GET /auth/me` with the session bearer so the token
 * stays server-side. The response carries `bvn_verified` / `nin_verified`
 * booleans only — never the values or their hashes (CLAUDE.md §4).
 */
export async function GET(): Promise<NextResponse> {
  const token = sessionAccessToken();
  if (!token) {
    return NextResponse.json({ error_code: 'NO_SESSION' }, { status: 401 });
  }

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/me`, {
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json({ error_code: 'AUTH_SERVICE_UNAVAILABLE' }, { status: 502 });
  }

  const body = await resp.json().catch(() => ({}));
  return NextResponse.json(body, { status: resp.status });
}
