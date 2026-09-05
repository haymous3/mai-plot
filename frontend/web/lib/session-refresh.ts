/**
 * Access-token freshness (SCRUM-206) — pure helpers so the middleware's refresh
 * decision is testable without a request.
 *
 * The access token lives 15 minutes and auth-service rotates the refresh token
 * on every redemption (single use, SCRUM-45). That rotation is why this is
 * decided ONCE per request in middleware rather than per fetch: the dashboards
 * issue five parallel session reads, and five concurrent redemptions of the
 * same refresh token would leave four presenting an already-revoked token,
 * which auth-service treats as replay.
 */

/** Seconds of headroom. Refresh a token that is *about* to expire, so a request
 * cannot die in flight between the check and the upstream call. */
export const REFRESH_SKEW_SECONDS = 60;

/** `exp` (seconds since epoch) from a JWT payload, or null if it cannot be read.
 *
 * Does NOT verify the signature — this only decides whether to refresh. The
 * token is httpOnly and set by us, and every backend call verifies it properly,
 * so a tampered token fails there rather than here. Same reasoning as
 * `sessionRole()`. */
export function accessTokenExpiry(token: string | null | undefined): number | null {
  if (!token) return null;
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  try {
    // base64url -> base64, padded. atob exists in both Edge and Node 18+.
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    const claims = JSON.parse(atob(padded)) as { exp?: unknown };
    return typeof claims.exp === 'number' ? claims.exp : null;
  } catch {
    return null;
  }
}

/** Whether the access token should be refreshed before serving this request.
 *
 * True when there is no token, when it cannot be parsed, or when it expires
 * within the skew. An unparseable token refreshes rather than being trusted —
 * the refresh either succeeds or cleanly ends the session. */
export function needsRefresh(
  token: string | null | undefined,
  now: number = Date.now(),
  skewSeconds: number = REFRESH_SKEW_SECONDS,
): boolean {
  const exp = accessTokenExpiry(token);
  if (exp === null) return true;
  return exp - skewSeconds <= Math.floor(now / 1000);
}

/** Error codes auth-service returns when a refresh token is beyond saving.
 * Any of these means the session is genuinely over: clear the cookies and send
 * the user to sign in, rather than leaving them on an error panel. */
const DEAD_REFRESH_CODES = new Set([
  'REFRESH_TOKEN_EXPIRED',
  'REFRESH_TOKEN_REVOKED',
  'REFRESH_TOKEN_INVALID',
]);

export function isDeadRefresh(errorCode: string | null | undefined): boolean {
  return errorCode !== null && errorCode !== undefined && DEAD_REFRESH_CODES.has(errorCode);
}
