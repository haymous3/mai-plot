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
  it('home is the dashboard, login is the buyer variant of /login', () => {
    expect(BUYER_HOME).toBe('/dashboard');
    // `?role=buyer`, not bare `/login`: bare `/login` is the role picker
    // (SCRUM-235), and a buyer bounced off a protected page should land on
    // the buyer form, not be asked which account they have.
    expect(BUYER_LOGIN).toBe('/login?role=buyer');
  });
});
