import { NextRequest, NextResponse } from 'next/server';

import { backendLogin, isSwitchableRole } from '@/lib/api';
import { isNonAdminRole, roleHome } from '@/lib/session';
import { applySessionCookies } from '@/lib/session-cookies';

/**
 * Shared non-admin login proxy (SCRUM-98). One login for buyer/seller/realtor:
 * authenticate via auth-service, reject admins (they use the admin surface),
 * store the tokens in httpOnly session cookies, and return the caller's role
 * home so the client can route there. Replaces the buyer-only /api/buyer/login.
 *
 * The credential field is `identifier` (SCRUM-207): an email address, or an
 * approved realtor's Maihomme registration number. `email` is still accepted so
 * a client cached from before the change keeps working through a deploy.
 *
 * `role` (SCRUM-236) is the sign-in page's Buyer / Seller choice, forwarded as
 * a PREFERENCE: a person whose sign-in opens both lands on the one they picked,
 * and on the buyer one when they picked nothing. Anything else is dropped here
 * rather than forwarded, so the backend never sees an unexpected value.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let payload: { identifier?: unknown; email?: unknown; password?: unknown; role?: unknown };
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }
  const identifier =
    typeof payload.identifier === 'string'
      ? payload.identifier
      : typeof payload.email === 'string'
        ? payload.email
        : '';
  const password = typeof payload.password === 'string' ? payload.password : '';
  if (!identifier || !password) {
    return NextResponse.json({ error: 'INVALID_REQUEST' }, { status: 400 });
  }
  const preferredRole = isSwitchableRole(payload.role) ? payload.role : undefined;

  const result = await backendLogin(identifier, password, preferredRole);
  if (!result.ok) {
    return NextResponse.json({ error: result.code }, { status: result.status === 502 ? 502 : 401 });
  }
  if (!isNonAdminRole(result.role)) {
    return NextResponse.json({ error: 'NOT_ALLOWED' }, { status: 403 });
  }

  return applySessionCookies(
    NextResponse.json({ ok: true, role: result.role, redirect: roleHome(result.role) }),
    result.accessToken,
    result.refreshToken,
  );
}
