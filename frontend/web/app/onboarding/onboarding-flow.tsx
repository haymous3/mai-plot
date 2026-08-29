'use client';

import { useState } from 'react';

import { BuyerProfileStep } from '../_onboarding/buyer-steps';
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
 * point-of-need gates (NIN at loan-apply, PoA at listing creation) still in
 * place as the backstop they have always been.
 *
 * The greeting name arrives from the SERVER (SCRUM-197). It used to be threaded
 * out of the details step in React state, which meant it survived neither a
 * reload nor a role whose flow never had that step — which was every role but
 * buyer. `GET /auth/me` has existed since SCRUM-188; the page reads it and
 * passes it in.
 */
export function OnboardingFlow({
  role,
  fullName,
}: {
  role: OnboardingRole;
  /** The account holder's name, from GET /auth/me. Null when never set. */
  fullName?: string | null;
}) {
  const [step, setStep] = useState<OnboardingStep>(() => firstStep(role) ?? 'welcome');

  function advance(from: OnboardingStep) {
    setStep(nextStep(role, from) ?? 'welcome');
  }

  return (
    <OnboardingShell>
      {step === 'buyer-profile' && <BuyerProfileStep onDone={() => advance('buyer-profile')} />}

      {step === 'seller-verification' && (
        <SellerVerificationStep onDone={() => advance('seller-verification')} />
      )}

      {step === 'realtor-profile' && (
        <RealtorProfileStep onDone={() => advance('realtor-profile')} />
      )}

      {step === 'welcome' && <Welcome role={role} fullName={fullName} />}
    </OnboardingShell>
  );
}
