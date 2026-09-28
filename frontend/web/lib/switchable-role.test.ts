import { describe, expect, it } from 'vitest';

import { isSwitchableRole } from './api';

// SCRUM-236: the guard every shared-login route runs on client input before it
// reaches auth-service. Only buyer and seller share a sign-in.
describe('isSwitchableRole', () => {
  it('accepts buyer and seller', () => {
    expect(isSwitchableRole('buyer')).toBe(true);
    expect(isSwitchableRole('seller')).toBe(true);
  });

  it('rejects realtor, staff and anything that is not a role string', () => {
    for (const value of ['realtor', 'admin', 'legal_team', '', 'Buyer', null, undefined, 1, ['buyer']]) {
      expect(isSwitchableRole(value)).toBe(false);
    }
  });
});
