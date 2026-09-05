import { NextRequest, NextResponse } from 'next/server';

import { authServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE, ADMIN_LOGIN } from '@/lib/auth';
import { clientIpFromForwardedFor, isIpAllowed, parseAllowlist } from '@/lib/ip';
import { SESSION_ACCESS_COOKIE, SESSION_LOGIN, SESSION_REFRESH_COOKIE } from '@/lib/session';
import { isDeadRefresh, needsRefresh } from '@/lib/session-refresh';

const FIFTEEN_MINUTES = 15 * 60;
const SEVEN_DAYS = 7 * 24 * 60 * 60;

/**
 * Two separate jobs, split by path (SCRUM-59 admin gate, SCRUM-206 session
 * refresh). They share a file only because Next.js allows one middleware.
 *
 * ⚠️ The IP allowlist applies to /admin ONLY. The matcher below is broad, so
 * the admin branch must stay behind its path check — running the allowlist on
 * the public site would 403 every visitor.
 */
export async function middleware(request: NextRequest): Promise<NextResponse> {
  const { pathname } = request.nextUrl;
  if (pathname.startsWith('/admin') || pathname.startsWith('/api/admin')) {
    return adminGate(request);
  }
  return refreshSession(request);
}

/**
 * Admin-surface gate (SCRUM-59), unchanged:
 *
 *  1. IP allowlist — a non-whitelisted IP gets an immediate 403, before the
 *     login page or any admin API renders. Empty allowlist = allow any (dev).
 *  2. Auth gate — an unauthenticated request to a protected /admin page is
 *     redirected to the login page. (UX, not the security boundary: the
 *     backend validates the JWT on every actual admin API call.)
 */
function adminGate(request: NextRequest): NextResponse {
  const allowlist = parseAllowlist(process.env.ADMIN_IP_ALLOWLIST);
  const ip = clientIpFromForwardedFor(request.headers.get('x-forwarded-for')) ?? request.ip ?? null;
  if (!isIpAllowed(ip, allowlist)) {
    return new NextResponse('Forbidden', { status: 403 });
  }

  const { pathname } = request.nextUrl;
  const isLogin = pathname === ADMIN_LOGIN;
  const isApi = pathname.startsWith('/api/admin');
  const hasSession = request.cookies.has(ACCESS_COOKIE);

  if (!isLogin && !isApi && !hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = ADMIN_LOGIN;
    return NextResponse.redirect(url);
  }

  if (isLogin && hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = '/admin/listings/queue';
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

/**
 * Keep the shared buyer/seller/realtor session alive (SCRUM-206).
 *
 * The access token lives 15 minutes; auth-service has always exposed
 * `/auth/token/refresh` and the refresh token has always been stored — but
 * nothing redeemed it, so every session died after 15 minutes and the user was
 * bounced back to the password prompt. Worst inside the inspection report
 * wizard: a long form with photo uploads whose submit returned NO_SESSION and
 * lost the lot.
 *
 * Refreshing here rather than in the fetch helper is deliberate, for two
 * reasons that rule the helper out entirely:
 *
 *  1. Refresh tokens ROTATE and are single use (SCRUM-45). The dashboards issue
 *     five parallel session reads; five concurrent redemptions would leave four
 *     presenting an already-revoked token, which auth-service treats as replay.
 *     Middleware runs once per request, so the race cannot happen.
 *  2. Server Components cannot set cookies — only Route Handlers, Server
 *     Actions and middleware can. A refresh in the helper could not persist the
 *     new pair even if the race were solved.
 *
 * Proactive, not reactive: a token inside the expiry skew is replaced before
 * the page or proxy runs, so no user-visible request has to fail first. That
 * also covers the wizard, whose multipart POST passes through here on its way
 * to the API proxy.
 */
async function refreshSession(request: NextRequest): Promise<NextResponse> {
  const access = request.cookies.get(SESSION_ACCESS_COOKIE)?.value ?? null;
  const refresh = request.cookies.get(SESSION_REFRESH_COOKIE)?.value ?? null;

  // Nothing to keep alive. A signed-out visitor is normal on public pages, and
  // the gated layouts do their own redirect.
  if (!refresh) return NextResponse.next();
  if (!needsRefresh(access)) return NextResponse.next();

  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/token/refresh`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
      cache: 'no-store',
    });
  } catch {
    // auth-service unreachable. Leave the cookies alone and let the request
    // through — a transient outage must not sign everybody out.
    return NextResponse.next();
  }

  if (!resp.ok) {
    const body = (await resp.json().catch(() => ({}))) as { error_code?: string };
    if (isDeadRefresh(body.error_code)) return endSession(request);
    // Some other failure (5xx, malformed). Same reasoning as the catch above.
    return NextResponse.next();
  }

  const body = (await resp.json().catch(() => ({}))) as {
    access_token?: string;
    refresh_token?: string;
  };
  if (!body.access_token || !body.refresh_token) return NextResponse.next();

  // Hand the NEW access token to this same request, so the page it is about to
  // render reads the fresh one rather than the expired cookie it arrived with.
  const headers = new Headers(request.headers);
  const forwarded = replaceCookie(
    request.headers.get('cookie') ?? '',
    SESSION_ACCESS_COOKIE,
    body.access_token,
  );
  headers.set('cookie', forwarded);

  const response = NextResponse.next({ request: { headers } });
  const secure = process.env.NODE_ENV === 'production';
  response.cookies.set(SESSION_ACCESS_COOKIE, body.access_token, {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    path: '/',
    maxAge: FIFTEEN_MINUTES,
  });
  // The refresh token rotated — persist the new one or the next refresh
  // presents a revoked token and reads as replay.
  response.cookies.set(SESSION_REFRESH_COOKIE, body.refresh_token, {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    path: '/',
    maxAge: SEVEN_DAYS,
  });
  return response;
}

/** The refresh token is genuinely finished. Clear both cookies so the user is
 * not left holding a dead session, and send page requests to sign in. API
 * requests are left to answer 401 themselves — redirecting a fetch to an HTML
 * login page is worse than an honest status. */
function endSession(request: NextRequest): NextResponse {
  const isApi = request.nextUrl.pathname.startsWith('/api/');
  const response = isApi
    ? NextResponse.next()
    : NextResponse.redirect(new URL(`${SESSION_LOGIN}?expired=1`, request.url));
  response.cookies.set(SESSION_ACCESS_COOKIE, '', { path: '/', maxAge: 0 });
  response.cookies.set(SESSION_REFRESH_COOKIE, '', { path: '/', maxAge: 0 });
  return response;
}

/** Swap one cookie's value in a Cookie header, leaving the rest untouched. */
function replaceCookie(header: string, name: string, value: string): string {
  const parts = header
    .split(';')
    .map((p) => p.trim())
    .filter((p) => p.length > 0 && !p.startsWith(`${name}=`));
  parts.push(`${name}=${value}`);
  return parts.join('; ');
}

export const config = {
  // Everything except Next's own assets and static files. The admin branch is
  // path-guarded inside, so widening this does not extend the IP allowlist.
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|txt|xml|webmanifest)$).*)',
  ],
};
