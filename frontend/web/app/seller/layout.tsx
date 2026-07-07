import { redirect } from 'next/navigation';

import { SellerNav } from './seller-nav';
import { SESSION_LOGIN } from '@/lib/session';
import { sessionAccessToken, sessionRole } from '@/lib/session-server';

/** Seller dashboard shell (SCRUM-98). Gates every /seller page on a seller
 * session; a signed-out visitor goes to the login, a non-seller to their own
 * role home. */
export default function SellerLayout({ children }: { children: React.ReactNode }) {
  if (!sessionAccessToken()) redirect(`${SESSION_LOGIN}?role=seller`);
  const role = sessionRole();
  if (role !== 'seller') redirect(role === 'buyer' ? '/dashboard' : SESSION_LOGIN);

  return (
    <div className="flex min-h-screen bg-[#f7f9f8]">
      <SellerNav />
      <div className="flex-1 overflow-x-hidden">{children}</div>
    </div>
  );
}
