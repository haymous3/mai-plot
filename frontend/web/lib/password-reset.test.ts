import { describe, expect, it } from 'vitest';

import {
  canSubmitReset,
  meetsPasswordRules,
  PASSWORD_RULES,
  resetPhaseForError,
} from './password-reset';

describe('resetPhaseForError', () => {
  it('ends the flow on the two dead-link codes', () => {
    expect(resetPhaseForError('RESET_TOKEN_EXPIRED')).toBe('expired');
    expect(resetPhaseForError('RESET_TOKEN_INVALID')).toBe('invalid');
  });

  // The backend checks strength only after the token proves out and does not
  // burn it on that path, so the link is still usable. Routing this to a
  // terminal phase would throw away a live link over a typo.
  it('keeps the user on the form for a weak password', () => {
    expect(resetPhaseForError('PASSWORD_TOO_WEAK')).toBeNull();
  });

  it('treats unknown and missing codes as retryable, not as a dead link', () => {
    expect(resetPhaseForError('AUTH_SERVICE_UNAVAILABLE')).toBeNull();
    expect(resetPhaseForError('SOMETHING_NEW')).toBeNull();
    expect(resetPhaseForError(undefined)).toBeNull();
  });
});

describe('PASSWORD_RULES', () => {
  // These mirror is_strong() in auth-service. If that changes, this fails first.
  it('states exactly the three rules the server enforces', () => {
    expect(PASSWORD_RULES.map((r) => r.label)).toEqual([
      'At least 8 characters',
      'An uppercase letter',
      'A number',
    ]);
  });

  it('scores each rule independently', () => {
    const [length, upper, digit] = PASSWORD_RULES;
    expect(length.test('Abcdefg1')).toBe(true);
    expect(length.test('Abc1')).toBe(false);
    expect(upper.test('abcdefg1')).toBe(false);
    expect(upper.test('Abcdefg1')).toBe(true);
    expect(digit.test('Abcdefgh')).toBe(false);
    expect(digit.test('Abcdefg1')).toBe(true);
  });
});

describe('meetsPasswordRules', () => {
  it('accepts a password satisfying all three', () => {
    expect(meetsPasswordRules('Password1')).toBe(true);
  });

  it.each([
    ['too short', 'Pass1'],
    ['no uppercase', 'password1'],
    ['no digit', 'Passwordy'],
    ['empty', ''],
  ])('rejects %s', (_label, value) => {
    expect(meetsPasswordRules(value)).toBe(false);
  });
});

describe('canSubmitReset', () => {
  it('allows a matching pair', () => {
    expect(canSubmitReset('Password1', 'Password1', false)).toBe(true);
  });

  it('blocks a mismatch', () => {
    expect(canSubmitReset('Password1', 'Password2', false)).toBe(false);
  });

  it('blocks an empty field', () => {
    expect(canSubmitReset('', '', false)).toBe(false);
    expect(canSubmitReset('Password1', '', false)).toBe(false);
  });

  it('blocks a double submit while in flight', () => {
    expect(canSubmitReset('Password1', 'Password1', true)).toBe(false);
  });

  // Deliberate: the checklist is guidance, not a gate. A weak password reaches
  // the server and comes back with a real reason, rather than leaving the user
  // staring at a disabled button with no explanation.
  it('does NOT gate on the strength rules', () => {
    expect(meetsPasswordRules('weak')).toBe(false);
    expect(canSubmitReset('weak', 'weak', false)).toBe(true);
  });
});
