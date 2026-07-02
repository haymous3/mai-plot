import { NextResponse } from 'next/server';

import { BUYER_ACCESS_COOKIE, BUYER_LOGIN, BUYER_REFRESH_COOKIE } from '@/lib/buyer-auth';

/** Clear the buyer session cookies and report where to go next. */
export async function POST(): Promise<NextResponse> {
  const response = NextResponse.json({ ok: true, redirect: BUYER_LOGIN });
  response.cookies.delete(BUYER_ACCESS_COOKIE);
  response.cookies.delete(BUYER_REFRESH_COOKIE);
  return response;
}
