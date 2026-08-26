import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { OnboardingShell } from '../../_onboarding/ui';
import { RealtorOnboardingForm } from './onboarding-form';
import type { RealtorProfile } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Complete your profile · Maiplot Realtor' };

/**
 * Realtor onboarding / credentials submission (SCRUM-156).
 *
 * SCRUM-185 put this step back in the post-verification funnel, so most
 * realtors now complete it at /onboarding. This route remains for the ones who
 * did not: `/realtor` redirects here when `GET /realtors/me` 404s. Both render
 * the SAME component, so the two can no longer drift the way they had — this
 * page asked for ESVARBON while the in-funnel design omitted it.
 *
 * Once a profile exists they're redirected to the portal (which shows the
 * pending-approval banner). The layout already gates on a realtor session.
 */
export default async function RealtorOnboardingPage() {
  const profileRes = await sessionBackendGet<RealtorProfile>(
    `${realtorServiceUrl()}/realtors/me`,
  );
  // A profile means they've already onboarded — send them to the portal. Only a
  // definite success redirects; a 404 (not onboarded) or a transient error both
  // fall through to the form so they can submit / retry.
  if (profileRes.ok) redirect('/realtor');

  return (
    <OnboardingShell>
      <RealtorOnboardingForm />
    </OnboardingShell>
  );
}
