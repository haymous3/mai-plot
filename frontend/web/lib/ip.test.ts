import { describe, expect, it } from 'vitest';

import { clientIpFromForwardedFor, isIpAllowed, parseAllowlist } from './ip';

describe('parseAllowlist', () => {
  it('returns [] for empty / missing', () => {
    expect(parseAllowlist(undefined)).toEqual([]);
    expect(parseAllowlist('')).toEqual([]);
    expect(parseAllowlist('  ')).toEqual([]);
  });

  it('trims and drops blank entries', () => {
    expect(parseAllowlist('1.1.1.1, 2.2.2.2 ,, 3.3.3.3')).toEqual(['1.1.1.1', '2.2.2.2', '3.3.3.3']);
  });
});

describe('clientIpFromForwardedFor', () => {
  it('takes the left-most (original client) entry', () => {
    expect(clientIpFromForwardedFor('9.9.9.9, 10.0.0.1, 10.0.0.2')).toBe('9.9.9.9');
  });

  it('returns null when absent', () => {
    expect(clientIpFromForwardedFor(null)).toBeNull();
    expect(clientIpFromForwardedFor('')).toBeNull();
  });
});

describe('isIpAllowed', () => {
  it('allows any IP when the allowlist is empty (dev default)', () => {
    expect(isIpAllowed('1.2.3.4', [])).toBe(true);
    expect(isIpAllowed(null, [])).toBe(true);
  });

  it('allows a whitelisted IP and denies others', () => {
    const allow = ['1.1.1.1', '2.2.2.2'];
    expect(isIpAllowed('1.1.1.1', allow)).toBe(true);
    expect(isIpAllowed('3.3.3.3', allow)).toBe(false);
  });

  it('fails closed for an unknown IP when an allowlist is configured', () => {
    expect(isIpAllowed(null, ['1.1.1.1'])).toBe(false);
  });
});
