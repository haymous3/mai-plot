import type { Metadata } from 'next';

import { ComingSoon } from '../coming-soon';

export const metadata: Metadata = { title: 'Profile · Maiplot Realtor' };

export default function RealtorProfilePage() {
  return (
    <ComingSoon
      title="Profile"
      subtitle="Your realtor credentials and coverage"
      note="Your profile and ESVARBON credentials view is landing soon."
    />
  );
}
