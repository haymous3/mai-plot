import type { NextResponse } from 'next/server';

import { SESSION_ACCESS_COOKIE, SESSION_REFRESH_COOKIE } from '@/lib/session';

const FIFTEEN_MINUTES = 15 * 60;
const SEVEN_DAYS = 7 * 24 * 60 * 60;

/**
 * Write a fresh non-admin session onto a response — the pair auth-service
 * returns from login, a role switch or an added role (SCRUM-236). One place,
 * so the three routes cannot drift on flags or lifetimes.
 */
export function applySessionCookies(
  response: NextResponse,
  accessToken: string,
  refreshToken: string,
): NextResponse {
  const secure = process.env.NODE_ENV === 'production';
  response.cookies.set(SESSION_ACCESS_COOKIE, accessToken, {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    path: '/',
    maxAge: FIFTEEN_MINUTES,
  });
  response.cookies.set(SESSION_REFRESH_COOKIE, refreshToken, {
    httpOnly: true,
    secure,
    sameSite: 'lax',
    path: '/',
    maxAge: SEVEN_DAYS,
  });
  return response;
}
