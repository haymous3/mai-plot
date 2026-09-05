import { describe, expect, it } from 'vitest';

import {
  accessTokenExpiry,
  isDeadRefresh,
  needsRefresh,
  REFRESH_SKEW_SECONDS,
} from './session-refresh';

/** A structurally valid JWT with the given exp. Only the payload is read — the
 * signature is never verified here, so a dummy one is honest. */
function tokenWithExp(expSeconds: number | null, payload: object = {}): string {
  const claims = expSeconds === null ? payload : { ...payload, exp: expSeconds };
  const b64 = Buffer.from(JSON.stringify(claims))
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
  return `header.${b64}.signature`;
}

const NOW = Date.parse('2026-09-05T12:00:00Z');
const NOW_S = Math.floor(NOW / 1000);

describe('accessTokenExpiry', () => {
  it('reads exp from the payload', () => {
    expect(accessTokenExpiry(tokenWithExp(1234567890))).toBe(1234567890);
  });

  it('survives base64url padding', () => {
    // Payload lengths that need 0, 1 and 2 '=' of padding.
    for (const pad of ['a', 'ab', 'abc']) {
      expect(accessTokenExpiry(tokenWithExp(NOW_S, { sub: pad }))).toBe(NOW_S);
    }
  });

  it('is null for anything unreadable', () => {
    expect(accessTokenExpiry(null)).toBeNull();
    expect(accessTokenExpiry(undefined)).toBeNull();
    expect(accessTokenExpiry('')).toBeNull();
    expect(accessTokenExpiry('not-a-jwt')).toBeNull();
    expect(accessTokenExpiry('two.parts')).toBeNull();
    expect(accessTokenExpiry('header.!!!not-base64!!!.sig')).toBeNull();
  });

  it('is null when the payload has no numeric exp', () => {
    expect(accessTokenExpiry(tokenWithExp(null, { sub: 'x' }))).toBeNull();
    expect(accessTokenExpiry(tokenWithExp(null, { exp: 'soon' }))).toBeNull();
  });
});

describe('needsRefresh', () => {
  it('leaves a token with plenty of life alone', () => {
    expect(needsRefresh(tokenWithExp(NOW_S + 600), NOW)).toBe(false);
  });

  it('refreshes one that is already expired', () => {
    expect(needsRefresh(tokenWithExp(NOW_S - 1), NOW)).toBe(true);
  });

  it('refreshes inside the skew, so a request cannot die in flight', () => {
    // Just outside the skew: still fine. Just inside: refresh.
    expect(needsRefresh(tokenWithExp(NOW_S + REFRESH_SKEW_SECONDS + 5), NOW)).toBe(false);
    expect(needsRefresh(tokenWithExp(NOW_S + REFRESH_SKEW_SECONDS - 5), NOW)).toBe(true);
  });

  it('treats exactly-at-the-skew as needing a refresh', () => {
    expect(needsRefresh(tokenWithExp(NOW_S + REFRESH_SKEW_SECONDS), NOW)).toBe(true);
  });

  it('refreshes a missing or unparseable token rather than trusting it', () => {
    expect(needsRefresh(null, NOW)).toBe(true);
    expect(needsRefresh('garbage', NOW)).toBe(true);
  });

  it('honours a zero skew — the liveness endpoint asks "usable right now"', () => {
    // 10s of life left: due for refresh, but still usable for this request.
    const token = tokenWithExp(NOW_S + 10);
    expect(needsRefresh(token, NOW)).toBe(true);
    expect(needsRefresh(token, NOW, 0)).toBe(false);
  });
});

describe('isDeadRefresh', () => {
  it('recognises the three codes that end a session', () => {
    expect(isDeadRefresh('REFRESH_TOKEN_EXPIRED')).toBe(true);
    expect(isDeadRefresh('REFRESH_TOKEN_REVOKED')).toBe(true);
    expect(isDeadRefresh('REFRESH_TOKEN_INVALID')).toBe(true);
  });

  it('does not sign the user out for a transient failure', () => {
    // A 5xx or an unknown code must leave the cookies alone.
    expect(isDeadRefresh('INTERNAL_ERROR')).toBe(false);
    expect(isDeadRefresh(null)).toBe(false);
    expect(isDeadRefresh(undefined)).toBe(false);
    expect(isDeadRefresh('')).toBe(false);
  });
});
