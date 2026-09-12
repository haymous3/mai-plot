import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { OnboardingFlow } from './onboarding-flow';
import { authServiceUrl } from '@/lib/api';
import { isOnboardingRole, onboardingExit } from '@/lib/onboarding-steps';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionAccessToken, sessionRole } from '@/lib/session-server';

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
export default async function OnboardingPage() {
  const role = sessionRole();
  if (!role) redirect(SESSION_LOGIN);
  if (!isOnboardingRole(role)) redirect(onboardingExit(role));

  // The name for the closing greeting (SCRUM-197), read here rather than
  // threaded out of a step in client state — that only ever worked for buyers,
  // and only until a reload. Best-effort: a failure here degrades to a plain
  // "Welcome!", never to a broken onboarding.
  const { fullName, ninVerified } = await accountSnapshot();

  return <OnboardingFlow role={role} fullName={fullName} ninVerified={ninVerified} />;
}

/**
 * The two facts onboarding needs from GET /auth/me, in one read.
 *
 * ⚠️ THE TWO FIELDS FAIL IN OPPOSITE DIRECTIONS, ON PURPOSE. A failed read
 * degrades `fullName` to null (a plain "Welcome!") and `ninVerified` to FALSE
 * (the NIN field is shown). Defaulting `ninVerified` to true on a failure would
 * silently skip a required identity step; showing the field to someone who has
 * already verified merely costs them a 409 they can read. Fail closed.
 *
 * `nin_verified` resolves through the identity link (SCRUM-225): a second
 * account whose root holds the NIN reads as verified here, which is what lets
 * SCRUM-228 skip the field for them rather than dead-ending them on a 409.
 */
async function accountSnapshot(): Promise<{ fullName: string | null; ninVerified: boolean }> {
  const absent = { fullName: null, ninVerified: false };
  const token = sessionAccessToken();
  if (!token) return absent;
  try {
    const resp = await fetch(`${authServiceUrl()}/auth/me`, {
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
    if (!resp.ok) return absent;
    const body = (await resp.json()) as { full_name?: string | null; nin_verified?: boolean };
    return {
      // Registration stores `full_name or ""`, so an account that predates
      // SCRUM-197 has an empty string rather than null. Treat it as absent.
      fullName: body.full_name?.trim() || null,
      ninVerified: body.nin_verified === true,
    };
  } catch {
    return absent;
  }
}
