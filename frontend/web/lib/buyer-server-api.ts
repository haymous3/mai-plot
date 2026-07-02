/**
 * Server-only backend access for buyer pages (SCRUM-94).
 *
 * Mirrors lib/server-api.ts but reads the buyer access cookie. Used by Server
 * Components and buyer Route Handlers so the token stays server-side.
 */

import { cookies } from 'next/headers';

import { BUYER_ACCESS_COOKIE } from '@/lib/buyer-auth';

export function buyerAccessToken(): string | null {
  return cookies().get(BUYER_ACCESS_COOKIE)?.value ?? null;
}

export type BackendResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; code: string };

/** Authenticated server-side GET for the buyer session. Returns a typed result
 * instead of throwing so callers can branch (401 -> login, 4xx -> message). */
export async function buyerBackendGet<T>(url: string): Promise<BackendResult<T>> {
  const token = buyerAccessToken();
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

/** Raw authenticated backend call for a buyer proxy route. Returns the backend
 * status + parsed JSON so the proxy can mirror them to the browser (the token
 * stays server-side). A missing token is 401; an unreachable backend is 502. */
export async function buyerBackendSend(
  method: 'GET' | 'POST',
  url: string,
  body?: unknown,
): Promise<{ status: number; body: unknown }> {
  const token = buyerAccessToken();
  if (!token) return { status: 401, body: { error_code: 'NO_SESSION' } };

  let resp: Response;
  try {
    resp = await fetch(url, {
      method,
      headers: {
        authorization: `Bearer ${token}`,
        ...(body !== undefined ? { 'content-type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: 'no-store',
    });
  } catch {
    return { status: 502, body: { error_code: 'BACKEND_UNAVAILABLE' } };
  }

  let parsed: unknown = null;
  try {
    parsed = await resp.json();
  } catch {
    parsed = null;
  }
  return { status: resp.status, body: parsed };
}
