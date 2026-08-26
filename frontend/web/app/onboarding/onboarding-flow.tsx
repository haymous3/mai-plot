'use client';

import { useState } from 'react';

import { BuyerProfileStep, PersonalDetailsStep } from '../_onboarding/buyer-steps';
import { RealtorProfileStep, SellerVerificationStep } from '../_onboarding/seller-realtor-steps';
import { OnboardingShell } from '../_onboarding/ui';
import { Welcome } from '../_onboarding/welcome';
import {
  firstStep,
  nextStep,
  type OnboardingRole,
  type OnboardingStep,
} from '@/lib/onboarding-steps';

/**
 * Drives the role's step sequence — SCRUM-185.
 *
 * State is deliberately in-memory and forward-only. Each step POSTs to a real
 * endpoint as it completes, so there is no back navigation to offer: going back
 * would re-submit an identity check that has already been accepted. A user who
 * abandons mid-flow simply lands on their dashboard next sign-in, with the
 * point-of-need gates (BVN at loan-apply, PoA at listing creation) still in
 * place as the backstop they have always been.
 *
 * The first name is threaded through from the details step purely so the
 * welcome screen can greet by name — there is no GET /auth/me to read it back.
 */
export function OnboardingFlow({ role }: { role: OnboardingRole }) {
  const [step, setStep] = useState<OnboardingStep>(() => firstStep(role) ?? 'welcome');
  const [firstName, setFirstName] = useState<string | null>(null);

  function advance(from: OnboardingStep) {
    setStep(nextStep(role, from) ?? 'welcome');
  }

  return (
    <OnboardingShell>
      {step === 'personal-details' && (
        <PersonalDetailsStep
          onDone={(fullName) => {
            setFirstName(fullName.split(/\s+/)[0] ?? null);
            advance('personal-details');
          }}
        />
      )}

      {step === 'buyer-profile' && <BuyerProfileStep onDone={() => advance('buyer-profile')} />}

      {step === 'seller-verification' && (
        <SellerVerificationStep onDone={() => advance('seller-verification')} />
      )}

      {step === 'realtor-profile' && (
        <RealtorProfileStep onDone={() => advance('realtor-profile')} />
      )}

      {step === 'welcome' && <Welcome role={role} firstName={firstName} />}
    </OnboardingShell>
  );
}
