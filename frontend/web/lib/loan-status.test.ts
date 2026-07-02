import { describe, expect, it } from 'vitest';

import { loanStatusLabel } from './format';

describe('loanStatusLabel', () => {
  it('maps known loan statuses to friendly labels', () => {
    expect(loanStatusLabel('under_review')).toBe('Under review');
    expect(loanStatusLabel('approved')).toBe('Approved');
    expect(loanStatusLabel('fully_repaid')).toBe('Fully repaid');
  });

  it('title-cases an unknown status as a fallback', () => {
    expect(loanStatusLabel('some_new_status')).toBe('Some new status');
  });
});
