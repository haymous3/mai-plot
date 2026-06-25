import type { Metadata } from 'next';
import { redirect } from 'next/navigation';

import { AdminNav } from '../../admin-nav';
import { PreferencesForm } from './preferences-form';
import type { NotificationPreferences } from '@/lib/api';
import { notificationServiceUrl } from '@/lib/api';
import { ADMIN_LOGIN } from '@/lib/auth';
import { backendGet } from '@/lib/server-api';

export const metadata: Metadata = {
  title: 'Notification settings · Maiplot',
  robots: { index: false, follow: false },
};

export default async function NotificationSettingsPage() {
  const result = await backendGet<NotificationPreferences>(
    `${notificationServiceUrl()}/notifications/preferences`,
  );
  if (!result.ok && result.status === 401) {
    redirect(ADMIN_LOGIN);
  }

  return (
    <div className="min-h-screen bg-bone">
      <AdminNav active="settings" count={null} />

      <main className="mx-auto max-w-2xl px-6 py-12">
        <p className="text-xs uppercase tracking-[0.2em] text-ink-300">Settings</p>
        <h1 className="mt-2 font-display text-3xl text-ink-900">Notifications</h1>
        <p className="mt-3 max-w-prose text-sm text-ink-500">
          Choose how you&apos;d like to be notified. In-app notifications are always on; you can mute
          the other channels here.
        </p>

        <div className="mt-8">
          {!result.ok ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center text-sm text-red-700">
              Could not load your preferences ({result.code}). Please retry.
            </div>
          ) : (
            <PreferencesForm initial={result.data} />
          )}
        </div>
      </main>
    </div>
  );
}
