import { redirect } from 'next/navigation';

import { RealtorNav } from './realtor-nav';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionAccessToken, sessionRole } from '@/lib/session-server';

/** Realtor portal shell (SCRUM-140). Gates every /realtor page on a realtor
 * session; a signed-out visitor goes to the login, a non-realtor to their own
 * role home. Mirrors the seller shell. */
export default function RealtorLayout({ children }: { children: React.ReactNode }) {
  if (!sessionAccessToken()) redirect(`${SESSION_LOGIN}?role=realtor`);
  const role = sessionRole();
  if (role !== 'realtor') redirect(role === 'seller' ? '/seller' : role === 'buyer' ? '/dashboard' : SESSION_LOGIN);

  return (
    <div className="flex min-h-screen bg-[#f7f9f8]">
      <RealtorNav />
      <div className="flex-1 overflow-x-hidden">{children}</div>
    </div>
  );
}
