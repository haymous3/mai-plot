import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { AddAccountFlow } from './add-account-flow';
import { authServiceUrl, isSwitchableRole } from '@/lib/api';
import { SESSION_LOGIN, roleHome } from '@/lib/session';
import { sessionAccessToken, sessionRole } from '@/lib/session-server';

export const metadata: Metadata = {
  title: 'Add an account · Maihomme',
};

/**
 * "Create a seller account" / "Create a buyer account" — SCRUM-236.
 *
 * Reached from the account switch (buyer menu, seller rail). The person is
 * signed in, which is what proves the account is theirs, so there is NO
 * registration form here: this page only says what carries over and asks once
 * before anything is created. It then goes to that role's onboarding.
 *
 * ⚠️ A verified NIN is required first (product decision) — the new account
 * inherits it. The NIN field is embedded HERE rather than pointing at
 * Settings, because Settings' only NIN field sits on the Financial tab, which
 * SCRUM-232 hid for every role. Sending people there would dead-end them.
 *
 * Realtors and staff are out of scope and go home; so does anyone asking for
 * the role they are already in, or one they already hold (the switch is the
 * way there, and it is in the same menu).
 */
export default async function AddAccountPage({
  searchParams,
}: {
  searchParams: { role?: string | string[] };
}) {
  const current = sessionRole();
  if (!current) redirect(SESSION_LOGIN);
  if (!isSwitchableRole(current)) redirect(roleHome(current));

  const param = Array.isArray(searchParams.role) ? searchParams.role[0] : searchParams.role;
  const target = isSwitchableRole(param) && param !== current ? param : null;
  if (!target) redirect(roleHome(current));

  const snapshot = await accountSnapshot();
  if (snapshot?.availableRoles.includes(target)) redirect(roleHome(current));

  return (
    <AddAccountFlow
      current={current}
      target={target}
      firstName={snapshot?.firstName ?? null}
      email={snapshot?.email ?? null}
      // Fails CLOSED, as onboarding does (SCRUM-228): an unreadable account
      // shows the NIN field, which costs a verified person one readable 409,
      // rather than letting an unverified one reach a Create that will refuse.
      ninVerified={snapshot?.ninVerified ?? false}
    />
  );
}

async function accountSnapshot(): Promise<{
  firstName: string | null;
  email: string | null;
  ninVerified: boolean;
  availableRoles: string[];
} | null> {
  const token = sessionAccessToken();
  if (!token) return null;
  try {
    const resp = await fetch(`${authServiceUrl()}/auth/me`, {
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
    if (!resp.ok) return null;
    const body = (await resp.json()) as {
      first_name?: string | null;
      email?: string | null;
      nin_verified?: boolean;
      available_roles?: unknown;
    };
    return {
      // The stored part only — no splitting full_name (SCRUM-231). A pre-0019
      // account simply gets the heading without a name.
      firstName: body.first_name?.trim() || null,
      email: body.email ?? null,
      ninVerified: body.nin_verified === true,
      availableRoles: Array.isArray(body.available_roles)
        ? body.available_roles.filter((r): r is string => typeof r === 'string')
        : [],
    };
  } catch {
    return null;
  }
}
