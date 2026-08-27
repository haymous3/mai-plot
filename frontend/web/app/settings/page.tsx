import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { SettingsClient } from './settings-client';
import { authServiceUrl, notificationServiceUrl, transactionServiceUrl } from '@/lib/api';
import { roleHome, SESSION_LOGIN } from '@/lib/session';
import { sessionAccessToken, sessionRole } from '@/lib/session-server';
import type { Account, NotificationPrefs, PayoutAccount } from '@/lib/settings';

export const metadata: Metadata = { title: 'Settings · Maihomme' };

/**
 * Account settings — SCRUM-188. Reached from the avatar menu, which has linked
 * here since SCRUM-95 with nothing behind it.
 *
 * Server-rendered so the three reads happen before paint and the panels start
 * pre-filled — the whole point of `GET /auth/me`, which did not exist until now.
 *
 * Deliberately outside the (buyer) route group: the design replaces the app
 * header with its own bar, and the same page serves sellers and realtors.
 */

async function get<T>(url: string, token: string): Promise<T | null> {
  try {
    const resp = await fetch(url, {
      headers: { authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
    if (!resp.ok) return null;
    return (await resp.json()) as T;
  } catch {
    return null;
  }
}

export default async function SettingsPage() {
  const token = sessionAccessToken();
  if (!token) redirect(SESSION_LOGIN);

  const account = await get<Account>(`${authServiceUrl()}/auth/me`, token);
  // No account behind a live token means it was soft-deleted or deactivated —
  // treat it as signed out rather than rendering an empty form.
  if (!account) redirect(SESSION_LOGIN);

  // Both are optional context: a user with no payout account or no saved
  // preferences still gets a working page, so a failure here degrades to
  // defaults rather than blocking the whole screen.
  const [payout, prefs] = await Promise.all([
    get<PayoutAccount>(`${transactionServiceUrl()}/payout-account`, token),
    get<NotificationPrefs>(`${notificationServiceUrl()}/notifications/preferences`, token),
  ]);

  return (
    <SettingsClient
      account={account}
      payout={payout}
      prefs={
        prefs ?? {
          push_enabled: true,
          sms_enabled: true,
          email_enabled: true,
          // Opt-IN by default (NDPR §9) — the one flag that
          // does NOT fall back to enabled.
          marketing_enabled: false,
        }
      }
      home={roleHome(sessionRole() ?? 'buyer')}
    />
  );
}
