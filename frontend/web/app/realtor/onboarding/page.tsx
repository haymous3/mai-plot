import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { RealtorHeader } from '../realtor-header';
import { RealtorOnboardingForm } from './onboarding-form';
import type { RealtorProfile } from '@/lib/api';
import { realtorServiceUrl } from '@/lib/api';
import { sessionBackendGet } from '@/lib/session-api';

export const metadata: Metadata = { title: 'Complete your profile · Maiplot Realtor' };

/**
 * Realtor onboarding / credentials submission (SCRUM-156). Since SCRUM-155,
 * realtors register + verify email but submit their ESVARBON credentials here
 * (there is no in-funnel step anymore). `GET /realtors/me` 404s until they do;
 * once a profile exists they're redirected to the portal (which shows the
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
    <main className="mx-auto max-w-6xl px-8 py-8">
      <RealtorHeader
        title="Complete your realtor profile"
        subtitle="Submit your credentials to start receiving inspection assignments"
      />
      <p className="mt-4 max-w-xl text-sm text-ink-600">
        Your email is verified. One more step: add your ESVARBON licence and a credentials document
        so our team can approve your account. You&rsquo;ll be able to explore the portal while your
        application is under review.
      </p>
      <RealtorOnboardingForm />
    </main>
  );
}
