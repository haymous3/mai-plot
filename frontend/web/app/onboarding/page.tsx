import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { OnboardingFlow } from './onboarding-flow';
import { isOnboardingRole, onboardingExit } from '@/lib/onboarding-steps';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionRole } from '@/lib/session-server';

export const metadata: Metadata = {
  title: 'Set up your account · Maihomme',
};

/**
 * Post-verification onboarding — SCRUM-185.
 *
 * Verification (email link or phone OTP) establishes the session and then sends
 * the user here instead of straight to their dashboard. The role comes from the
 * session JWT server-side, so the flow cannot be entered as the wrong role by
 * editing a query parameter.
 *
 * Roles that are provisioned rather than signed up — admin, legal_team,
 * bank_partner — have no onboarding and are bounced to their own home.
 */
export default function OnboardingPage() {
  const role = sessionRole();
  if (!role) redirect(SESSION_LOGIN);
  if (!isOnboardingRole(role)) redirect(onboardingExit(role));

  return <OnboardingFlow role={role} />;
}
