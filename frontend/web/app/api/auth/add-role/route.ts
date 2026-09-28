import type { NextRequest, NextResponse } from 'next/server';

import { roleSessionRoute } from '@/lib/role-session-route';

/** Create the caller's buyer or seller account on their existing sign-in and
 * move the session into it (SCRUM-236). Body: `{ role }`. Needs a verified NIN
 * — `409 NIN_VERIFICATION_REQUIRED` otherwise. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  return roleSessionRoute(request, 'add-role');
}
