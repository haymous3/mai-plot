import { describe, expect, it } from 'vitest';

import { ADMIN_HOME, isAdminRole } from './auth';

describe('isAdminRole', () => {
  it('accepts the privileged dashboard roles', () => {
    expect(isAdminRole('admin')).toBe(true);
    expect(isAdminRole('legal_team')).toBe(true);
  });

  it('rejects regular user roles and nullish values', () => {
    expect(isAdminRole('seller')).toBe(false);
    expect(isAdminRole('buyer')).toBe(false);
    expect(isAdminRole('realtor')).toBe(false);
    expect(isAdminRole(null)).toBe(false);
    expect(isAdminRole(undefined)).toBe(false);
  });
});

describe('ADMIN_HOME', () => {
  it('is the listing review queue (AC6 redirect target)', () => {
    expect(ADMIN_HOME).toBe('/admin/listings/queue');
  });
});
