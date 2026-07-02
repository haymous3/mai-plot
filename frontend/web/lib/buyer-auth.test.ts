import { describe, expect, it } from 'vitest';

import { BUYER_HOME, BUYER_LOGIN, isBuyerRole } from './buyer-auth';

describe('isBuyerRole', () => {
  it('accepts the buyer role only', () => {
    expect(isBuyerRole('buyer')).toBe(true);
  });

  it('rejects other roles and nullish values', () => {
    expect(isBuyerRole('admin')).toBe(false);
    expect(isBuyerRole('seller')).toBe(false);
    expect(isBuyerRole('realtor')).toBe(false);
    expect(isBuyerRole(null)).toBe(false);
    expect(isBuyerRole(undefined)).toBe(false);
  });
});

describe('buyer routes', () => {
  it('home is the dashboard, login is /login', () => {
    expect(BUYER_HOME).toBe('/dashboard');
    expect(BUYER_LOGIN).toBe('/login');
  });
});
