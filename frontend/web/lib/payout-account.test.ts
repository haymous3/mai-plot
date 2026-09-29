import { describe, expect, it } from 'vitest';

import { cleanAccountNumber, isCompleteAccountNumber, payoutErrorMessage } from './payout-account';

// SCRUM-223 — the form only asks the bank once the number is a complete NUBAN,
// so these guard both correctness and the number of lookups we spend.
describe('account number helpers', () => {
  it('keeps digits only and caps at ten', () => {
    expect(cleanAccountNumber('0123-456 789')).toBe('0123456789');
    expect(cleanAccountNumber('012345678901234')).toBe('0123456789');
    expect(cleanAccountNumber('abc')).toBe('');
  });

  it('treats exactly ten digits as complete', () => {
    expect(isCompleteAccountNumber('0123456789')).toBe(true);
    expect(isCompleteAccountNumber('012345678')).toBe(false);
    expect(isCompleteAccountNumber('01234567890')).toBe(false);
    expect(isCompleteAccountNumber('01234a6789')).toBe(false);
  });
});

describe('payoutErrorMessage', () => {
  it('tells a bad number apart from a bank outage', () => {
    expect(payoutErrorMessage('ACCOUNT_NOT_RESOLVED')).toMatch(/doesn.t recognise/);
    expect(payoutErrorMessage('RECIPIENT_UNAVAILABLE')).toMatch(/try again/);
  });

  it('names the password problems', () => {
    expect(payoutErrorMessage('PASSWORD_INCORRECT')).toBe('That password is incorrect.');
    expect(payoutErrorMessage('REAUTH_RATE_LIMITED')).toMatch(/Too many/);
  });

  it('falls back for anything unknown', () => {
    expect(payoutErrorMessage(undefined)).toMatch(/Something went wrong/);
    expect(payoutErrorMessage('WHO_KNOWS')).toMatch(/Something went wrong/);
  });
});
