import { describe, expect, it } from 'vitest';

import { isNonAdminRole, roleHome } from './session';

describe('isNonAdminRole', () => {
  it('accepts buyer/seller/realtor', () => {
    expect(isNonAdminRole('buyer')).toBe(true);
    expect(isNonAdminRole('seller')).toBe(true);
    expect(isNonAdminRole('realtor')).toBe(true);
  });

  it('rejects admin and nullish', () => {
    expect(isNonAdminRole('admin')).toBe(false);
    expect(isNonAdminRole('legal_team')).toBe(false);
    expect(isNonAdminRole(null)).toBe(false);
    expect(isNonAdminRole(undefined)).toBe(false);
  });
});

describe('roleHome', () => {
  it('routes each role to its landing', () => {
    expect(roleHome('buyer')).toBe('/dashboard');
    expect(roleHome('seller')).toBe('/seller');
    expect(roleHome('realtor')).toBe('/realtor');
  });

  it('falls back to the buyer dashboard for an unknown role', () => {
    expect(roleHome('something')).toBe('/dashboard');
  });
});
