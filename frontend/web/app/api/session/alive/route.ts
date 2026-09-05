import { NextRequest, NextResponse } from 'next/server';

import { SESSION_ACCESS_COOKIE } from '@/lib/session';
import { needsRefresh } from '@/lib/session-refresh';

/**
 * Is the shared session still usable? (SCRUM-206)
 *
 * Deliberately cheap: it reads the cookie and checks `exp`, and never calls a
 * backend. Middleware has already had a chance to refresh this request, so by
 * the time the handler runs the cookie is either fresh or beyond saving.
 *
 * Exists for the report wizard, which uploads several photos in one multipart
 * POST. Discovering a dead session *after* pushing the upload wastes the
 * realtor's data and their time, and the form state only lives in the browser.
 * Asking first costs one tiny request.
 */
export function GET(request: NextRequest): NextResponse {
  const token = request.cookies.get(SESSION_ACCESS_COOKIE)?.value ?? null;
  // Zero skew: the question here is "can this request succeed right now",
  // not "should it be refreshed soon".
  const alive = token !== null && !needsRefresh(token, Date.now(), 0);
  return NextResponse.json({ alive }, { status: alive ? 200 : 401 });
}
