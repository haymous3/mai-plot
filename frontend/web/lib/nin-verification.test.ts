import { describe, expect, it } from 'vitest';

import { isCompleteNin, ninIsSettled, ninOutcome } from './nin-verification';

describe('isCompleteNin', () => {
  it('accepts exactly 11 digits', () => {
    expect(isCompleteNin('12345678901')).toBe(true);
  });

  it('rejects anything shorter, longer or non-numeric', () => {
    expect(isCompleteNin('1234567890')).toBe(false);
    expect(isCompleteNin('123456789012')).toBe(false);
    expect(isCompleteNin('1234567890a')).toBe(false);
    expect(isCompleteNin('')).toBe(false);
  });

  it('ignores surrounding whitespace', () => {
    expect(isCompleteNin('  12345678901  ')).toBe(true);
  });
});

describe('ninIsSettled', () => {
  it('lets a verified NIN through', () => {
    expect(ninIsSettled('verified')).toBe(true);
  });

  it('lets a PENDING NIN through', () => {
    // Ninja's `review` — a partially matching name is not a fraud signal, and
    // blocking on it would strand a real person behind a middle name.
    expect(ninIsSettled('pending')).toBe(true);
  });

  it('holds everything else', () => {
    expect(ninIsSettled('idle')).toBe(false);
    expect(ninIsSettled('checking')).toBe(false);
    expect(ninIsSettled('error')).toBe(false);
  });
});

describe('ninOutcome', () => {
  it('reads a plain 2xx as verified with nothing to say', () => {
    expect(ninOutcome(true, { status: 'verified' })).toEqual({
      status: 'verified',
      message: null,
      retryable: false,
    });
  });

  it('reads a 2xx carrying status=pending as pending, not verified', () => {
    // The route answers 202 for both, so the BODY is the only thing that
    // separates "done" from "a human should look at this".
    const out = ninOutcome(true, { status: 'pending' });
    expect(out.status).toBe('pending');
    expect(out.message).toBeTruthy();
  });

  it('treats a rejected NIN as retryable — nothing was stored', () => {
    const out = ninOutcome(false, { error_code: 'NIN_NOT_VERIFIED' });
    expect(out.status).toBe('error');
    expect(out.retryable).toBe(true);
    expect(out.message).toMatch(/did not match your name/i);
  });

  it('treats an already-verified NIN as NOT retryable', () => {
    // has_nin answers 409 from then on, so re-firing can only ever fail.
    const out = ninOutcome(false, { error_code: 'NIN_ALREADY_VERIFIED' });
    expect(out.retryable).toBe(false);
  });

  it('does not reveal whose account holds an already-verified NIN', () => {
    // auth-service will not distinguish "yours" from "someone else's"; the
    // copy must not imply it can.
    const out = ninOutcome(false, { error_code: 'NIN_ALREADY_VERIFIED' });
    expect(out.message).not.toMatch(/your account|another account|someone else/i);
  });

  it('maps a format rejection to the digit count', () => {
    expect(ninOutcome(false, { error_code: 'NIN_FORMAT_INVALID' }).message).toMatch(/11 digits/);
  });

  it('treats a provider outage as retryable', () => {
    const out = ninOutcome(false, { error_code: 'NIN_VERIFICATION_UNAVAILABLE' });
    expect(out.status).toBe('error');
    expect(out.retryable).toBe(true);
  });

  it('falls back to a retryable error for an unmapped code', () => {
    const out = ninOutcome(false, { error_code: 'SOMETHING_NEW' });
    expect(out.status).toBe('error');
    expect(out.retryable).toBe(true);
    expect(out.message).toBeTruthy();
  });

  it('falls back when the body carries no code at all', () => {
    expect(ninOutcome(false, {}).status).toBe('error');
  });

  it('never reports a failure as settled', () => {
    for (const code of [
      'NIN_FORMAT_INVALID',
      'NIN_ALREADY_VERIFIED',
      'NIN_NOT_VERIFIED',
      'NIN_VERIFICATION_UNAVAILABLE',
      'ANYTHING_ELSE',
    ]) {
      expect(ninIsSettled(ninOutcome(false, { error_code: code }).status)).toBe(false);
    }
  });
});
