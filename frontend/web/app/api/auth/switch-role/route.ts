import type { NextRequest, NextResponse } from 'next/server';

import { roleSessionRoute } from '@/lib/role-session-route';

/** Move the session to the caller's other account on the same sign-in —
 * buyer to seller or back (SCRUM-236). Body: `{ role }`. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  return roleSessionRoute(request, 'switch-role');
}
