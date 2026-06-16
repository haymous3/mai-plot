/**
 * IP allowlist gate for the admin surface (SCRUM-59).
 *
 * Admin routes are restricted to a configured set of IPs (CLAUDE.md: admin
 * endpoints require JWT *and* an IP whitelist; Kong enforces this at the edge,
 * this is defence in depth at the app layer). An empty allowlist means
 * "allow any" — the dev/local default.
 *
 * Pure + dependency-free so it is unit-tested without a request.
 */

/** Parse a comma-separated allowlist env value into trimmed, non-empty IPs. */
export function parseAllowlist(raw: string | undefined | null): string[] {
  if (!raw) return [];
  return raw
    .split(',')
    .map((ip) => ip.trim())
    .filter((ip) => ip.length > 0);
}

/**
 * The client IP from an `x-forwarded-for` header (left-most entry is the
 * original client; the rest are proxies). Returns null when absent.
 */
export function clientIpFromForwardedFor(forwardedFor: string | null | undefined): string | null {
  if (!forwardedFor) return null;
  const first = forwardedFor.split(',')[0]?.trim();
  return first && first.length > 0 ? first : null;
}

/**
 * Whether `ip` may access the admin surface given the allowlist. An empty
 * allowlist allows everything (dev). A configured allowlist denies an unknown
 * or null client IP — fail closed.
 */
export function isIpAllowed(ip: string | null, allowlist: string[]): boolean {
  if (allowlist.length === 0) return true;
  if (!ip) return false;
  return allowlist.includes(ip);
}
