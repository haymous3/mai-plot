/**
 * Server-only backend access for admin pages (SCRUM-60).
 *
 * Reads the access token from the httpOnly cookie and calls the backend with a
 * bearer header — so the token stays server-side. Used by Server Components and
 * Route Handlers, never the browser. (next/headers `cookies()` already enforces
 * the server-only boundary at runtime.)
 */

import { cookies } from 'next/headers';

import { ACCESS_COOKIE } from '@/lib/auth';

export function accessToken(): string | null {
  return cookies().get(ACCESS_COOKIE)?.value ?? null;
}

export type BackendResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; code: string };

/** Authenticated server-side fetch + JSON decode. Returns a typed result
 * instead of throwing on HTTP errors so callers can branch (401 -> login,
 * 4xx -> message). A missing token short-circuits to 401. */
export async function backendGet<T>(url: string): Promise<BackendResult<T>> {
  const token = accessToken();
  if (!token) return { ok: false, status: 401, code: 'NO_SESSION' };

  let resp: Response;
  try {
    resp = await fetch(url, {
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
  } catch {
    return { ok: false, status: 502, code: 'BACKEND_UNAVAILABLE' };
  }

  if (!resp.ok) {
    let code = 'REQUEST_FAILED';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // non-JSON error — keep default
    }
    return { ok: false, status: resp.status, code };
  }

  return { ok: true, data: (await resp.json()) as T };
}
