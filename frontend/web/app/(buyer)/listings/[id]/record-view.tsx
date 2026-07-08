'use client';

import { useEffect } from 'react';

import { recordRecentlyViewed, type RecentListingInput } from '@/lib/recently-viewed';

/** Records the opened listing into the recently-viewed cache (SCRUM-136).
 * Renders nothing — it exists so the server-rendered detail page can seed the
 * client-side offline cache without becoming a client component itself. */
export function RecordView({ listing }: { listing: RecentListingInput }) {
  useEffect(() => {
    recordRecentlyViewed(listing);
    // Re-run only when the listing identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listing.id]);

  return null;
}
