import { NextResponse } from 'next/server';

import { ACCESS_COOKIE, ADMIN_LOGIN, REFRESH_COOKIE } from '@/lib/auth';

/** Clear the admin session cookies and report where to go next. */
export async function POST(): Promise<NextResponse> {
  const response = NextResponse.json({ ok: true, redirect: ADMIN_LOGIN });
  response.cookies.delete(ACCESS_COOKIE);
  response.cookies.delete(REFRESH_COOKIE);
  return response;
}
