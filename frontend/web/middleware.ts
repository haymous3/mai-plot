import { NextRequest, NextResponse } from 'next/server';

import { ACCESS_COOKIE, ADMIN_LOGIN } from '@/lib/auth';
import { clientIpFromForwardedFor, isIpAllowed, parseAllowlist } from '@/lib/ip';

/**
 * Admin-surface gate (SCRUM-59), runs before any /admin or /api/admin route:
 *
 *  1. IP allowlist — a non-whitelisted IP gets an immediate 403, before the
 *     login page or any admin API renders (AC: "Non-whitelisted IPs see 403
 *     immediately"). Empty allowlist = allow any (dev default).
 *  2. Auth gate — an unauthenticated request to a protected /admin page is
 *     redirected to the login page. (This is UX, not the security boundary:
 *     the backend validates the JWT on every actual admin API call.)
 */
export function middleware(request: NextRequest): NextResponse {
  const allowlist = parseAllowlist(process.env.ADMIN_IP_ALLOWLIST);
  const ip = clientIpFromForwardedFor(request.headers.get('x-forwarded-for')) ?? request.ip ?? null;
  if (!isIpAllowed(ip, allowlist)) {
    return new NextResponse('Forbidden', { status: 403 });
  }

  const { pathname } = request.nextUrl;
  const isLogin = pathname === ADMIN_LOGIN;
  const isApi = pathname.startsWith('/api/admin');
  const hasSession = request.cookies.has(ACCESS_COOKIE);

  // Unauthenticated admin *page* requests go to login; the login page itself
  // and the API routes are exempt (the API enforces auth on its own).
  if (!isLogin && !isApi && !hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = ADMIN_LOGIN;
    return NextResponse.redirect(url);
  }

  // Already signed in and hitting the login page -> send to the dashboard.
  if (isLogin && hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = '/admin/listings/queue';
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/admin/:path*', '/api/admin/:path*'],
};
