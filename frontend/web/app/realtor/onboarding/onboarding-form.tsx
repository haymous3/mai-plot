'use client';

import { useRouter } from 'next/navigation';

import { RealtorProfileStep } from '../../_onboarding/seller-realtor-steps';

/**
 * Standalone realtor onboarding, for a realtor who reached the portal without
 * a profile — `/realtor` redirects here when `GET /realtors/me` 404s.
 *
 * SCRUM-185 folded this into the shared `RealtorProfileStep` rather than
 * keeping a second implementation of the same form. There used to be two,
 * and they had already drifted: this one asked for ESVARBON, the in-funnel
 * design did not. One component means one answer — which is also why removing
 * the credentials upload (SCRUM-219) was a single edit rather than two.
 */
export function RealtorOnboardingForm() {
  const router = useRouter();
  return (
    <RealtorProfileStep
      onDone={() => {
        router.replace('/realtor');
        router.refresh();
      }}
    />
  );
}
