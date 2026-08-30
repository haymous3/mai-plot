import { describe, expect, it } from 'vitest';

import {
  firstStep,
  isOnboardingRole,
  isSkippable,
  nextStep,
  onboardingExit,
  stepsFor,
  welcomeGreeting,
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
    expect(stepsFor('buyer')).toEqual(['buyer-profile', 'welcome']);
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
    expect(firstStep('buyer')).toBe('buyer-profile');
    expect(firstStep('seller')).toBe('seller-verification');
    expect(firstStep('realtor')).toBe('realtor-profile');
  });

  it('is null when the role has no onboarding', () => {
    expect(firstStep('admin')).toBeNull();
  });
});

describe('nextStep', () => {
  it('walks the buyer flow in order', () => {
    expect(nextStep('buyer', 'buyer-profile')).toBe('welcome');
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
    expect(nextStep('seller', 'buyer-profile')).toBeNull();
    expect(nextStep('realtor', 'buyer-profile')).toBeNull();
  });

  it('returns null for an unknown role', () => {
    expect(nextStep('admin', 'welcome')).toBeNull();
  });
});

describe('isSkippable', () => {
  // Nothing is skippable since SCRUM-201: NIN and address are required of every
  // role, so the buyer step's "Skip for now" was removed rather than left
  // offering something the submit path no longer honours.
  it('no longer allows skipping the buyer profile', () => {
    expect(isSkippable('buyer-profile')).toBe(false);
  });

  // These gate real capability: a seller cannot publish without a declared
  // authority (§8.1), and a realtor row does not exist until POST /realtors.
  it('does not allow skipping the gating steps', () => {
    expect(isSkippable('seller-verification')).toBe(false);
    expect(isSkippable('realtor-profile')).toBe(false);
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

describe('SCRUM-197 — the name is collected at registration, not in a step', () => {
  it('no role has a personal-details step any more', () => {
    // Registration asks once, for every role. A buyer step would have asked a
    // second time and shown an empty field for something already typed.
    for (const role of ['buyer', 'seller', 'realtor']) {
      expect(stepsFor(role)).not.toContain('personal-details');
    }
  });

  it('every role still ends on the welcome screen', () => {
    // That screen is where the greeting lands, so no role may skip it.
    for (const role of ['buyer', 'seller', 'realtor']) {
      const steps = stepsFor(role);
      expect(steps[steps.length - 1]).toBe('welcome');
    }
  });
});

describe('welcomeGreeting', () => {
  it('greets by given name', () => {
    expect(welcomeGreeting('Ada Obi')).toBe('Welcome, Ada!');
  });

  it('uses only the first name, however long the full one is', () => {
    // The design's greeting band is one line; a full name wraps it.
    expect(welcomeGreeting('Kolawole Oluwaseun Adeyemi')).toBe('Welcome, Kolawole!');
  });

  it('falls back to a plain welcome when there is no name', () => {
    expect(welcomeGreeting(null)).toBe('Welcome!');
    expect(welcomeGreeting(undefined)).toBe('Welcome!');
  });

  it('treats an empty stored name as absent', () => {
    // Accounts created before SCRUM-197 have full_name = "" rather than null,
    // because registration stored `full_name or ""`. "Welcome, !" would be the
    // visible cost of missing this.
    expect(welcomeGreeting('')).toBe('Welcome!');
    expect(welcomeGreeting('   ')).toBe('Welcome!');
  });

  it('tolerates leading whitespace rather than greeting nobody', () => {
    expect(welcomeGreeting('  Ada Obi ')).toBe('Welcome, Ada!');
  });
});
