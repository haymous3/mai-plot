/**
 * Server-side client for the backend (auth-service for now).
 *
 * Only ever called from Route Handlers / Server Components — the browser talks
 * to same-origin Next routes, which proxy here. This keeps tokens server-side.
 */

export function authServiceUrl(): string {
  return process.env.AUTH_SERVICE_URL ?? 'http://localhost:8011';
}

export interface LoginSuccess {
  ok: true;
  accessToken: string;
  refreshToken: string;
  role: string;
}

export interface LoginFailure {
  ok: false;
  status: number;
  code: string;
}

/** Call auth-service POST /auth/login. Never throws on a 4xx — returns a typed
 * failure so the caller maps it to a response. */
export async function backendLogin(email: string, password: string): Promise<LoginSuccess | LoginFailure> {
  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/login`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ email, password }),
      cache: 'no-store',
    });
  } catch {
    return { ok: false, status: 502, code: 'AUTH_SERVICE_UNAVAILABLE' };
  }

  if (!resp.ok) {
    let code = 'INVALID_CREDENTIALS';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // non-JSON error body — keep the default code
    }
    return { ok: false, status: resp.status, code };
  }

  const body = (await resp.json()) as {
    access_token: string;
    refresh_token: string;
    user: { role: string };
  };
  return {
    ok: true,
    accessToken: body.access_token,
    refreshToken: body.refresh_token,
    role: body.user.role,
  };
}
