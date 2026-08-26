import { describe, expect, it } from 'vitest';

import {
  firstStep,
  isOnboardingRole,
  isSkippable,
  nextStep,
  onboardingExit,
  stepsFor,
} from './onboarding-steps';

describe('isOnboardingRole', () => {
  it('accepts the three signup roles', () => {
    expect(isOnboardingRole('buyer')).toBe(true);
    expect(isOnboardingRole('seller')).toBe(true);
    expect(isOnboardingRole('realtor')).toBe(true);
  });

  // admin / legal_team / bank_partner are provisioned, not signed up, and have
  // no onboarding to run.
  it('rejects the provisioned roles', () => {
    expect(isOnboardingRole('admin')).toBe(false);
    expect(isOnboardingRole('legal_team')).toBe(false);
    expect(isOnboardingRole('bank_partner')).toBe(false);
    expect(isOnboardingRole('')).toBe(false);
  });
});

describe('stepsFor', () => {
  it('gives the buyer two collection steps then welcome', () => {
    expect(stepsFor('buyer')).toEqual(['personal-details', 'buyer-profile', 'welcome']);
  });

  it('gives the seller one verification step then welcome', () => {
    expect(stepsFor('seller')).toEqual(['seller-verification', 'welcome']);
  });

  it('gives the realtor one profile step then welcome', () => {
    expect(stepsFor('realtor')).toEqual(['realtor-profile', 'welcome']);
  });

  it('every role ends on welcome', () => {
    for (const role of ['buyer', 'seller', 'realtor']) {
      const steps = stepsFor(role);
      expect(steps[steps.length - 1]).toBe('welcome');
    }
  });

  it('gives an unknown role nothing rather than a default flow', () => {
    expect(stepsFor('admin')).toEqual([]);
  });
});

describe('firstStep', () => {
  it('returns the role-specific entry point', () => {
    expect(firstStep('buyer')).toBe('personal-details');
    expect(firstStep('seller')).toBe('seller-verification');
    expect(firstStep('realtor')).toBe('realtor-profile');
  });

  it('is null when the role has no onboarding', () => {
    expect(firstStep('admin')).toBeNull();
  });
});

describe('nextStep', () => {
  it('walks the buyer flow in order', () => {
    expect(nextStep('buyer', 'personal-details')).toBe('buyer-profile');
    expect(nextStep('buyer', 'buyer-profile')).toBe('welcome');
  });

  it('returns null at the end of a flow', () => {
    expect(nextStep('buyer', 'welcome')).toBeNull();
    expect(nextStep('seller', 'welcome')).toBeNull();
  });

  // A step from another role's flow means the caller is confused. Ending the
  // flow is safer than guessing a position and dropping the user somewhere
  // that posts to an endpoint their role cannot use.
  it('returns null for a step that is not in the role flow', () => {
    expect(nextStep('buyer', 'seller-verification')).toBeNull();
    expect(nextStep('seller', 'personal-details')).toBeNull();
    expect(nextStep('realtor', 'buyer-profile')).toBeNull();
  });

  it('returns null for an unknown role', () => {
    expect(nextStep('admin', 'welcome')).toBeNull();
  });
});

describe('isSkippable', () => {
  // The design draws "Skip for now" only on the buyer profile step, and every
  // field on it is optional server-side.
  it('allows skipping the buyer profile', () => {
    expect(isSkippable('buyer-profile')).toBe(true);
  });

  // These gate real capability: a seller cannot publish without a declared
  // authority (§8.1), and a realtor row does not exist until POST /realtors.
  it('does not allow skipping the gating steps', () => {
    expect(isSkippable('seller-verification')).toBe(false);
    expect(isSkippable('realtor-profile')).toBe(false);
    expect(isSkippable('personal-details')).toBe(false);
    expect(isSkippable('welcome')).toBe(false);
  });
});

describe('onboardingExit', () => {
  it('matches where verification used to send each role directly', () => {
    expect(onboardingExit('buyer')).toBe('/dashboard');
    expect(onboardingExit('seller')).toBe('/seller');
    expect(onboardingExit('realtor')).toBe('/realtor');
  });
});
