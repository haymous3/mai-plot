/**
 * Shared types for the Settings screens (SCRUM-188).
 *
 * `Account` mirrors auth-service `GET /auth/me`. Note what is NOT here: the BVN
 * and NIN appear only as `*_verified` booleans, because the service stores them
 * as bcrypt hashes and never returns the values (CLAUDE.md §4).
 */

export type Account = {
  id: string;
  role: string;
  verified_status: string;
  email: string | null;
  phone: string;
  full_name: string;
  seller_authority_type: string | null;
  poa_verified_status: string;
  bvn_verified: boolean;
  nin_verified: boolean;
  /**
   * A short-lived PRE-SIGNED URL, or null when no photo is set. Never a
   * durable link: the bucket is private, so this expires (15 min). Re-read
   * /auth/me for a fresh one rather than caching it anywhere.
   */
  avatar_url: string | null;
  /**
   * The account holder's OWN location (SCRUM-193, `user_pii.location`). Every
   * role has one. Do not confuse it with `preferred_location` below, which is
   * buyer-only and means where they want to BUY.
   */
  location: string | null;
  /**
   * Postal address (SCRUM-201, `user_pii.address`). Every role, and distinct
   * from both `location` above and `preferred_location` below — see auth
   * migration 0014 for why all three exist.
   */
  address: string | null;
  /** Buyer-only; null for other roles and for buyers who skipped the step. */
  employment_status: string | null;
  preferred_location: string | null;
  budget_kobo: number | null;
};

export type PayoutAccount = {
  account_number_masked: string;
  bank_code: string;
  account_name: string;
  recipient_ready: boolean;
};

export type NotificationPrefs = {
  push_enabled: boolean;
  sms_enabled: boolean;
  email_enabled: boolean;
  /**
   * Opt-IN, unlike the three above, which are opt-out. NDPR requires explicit
   * consent for promotional messaging, so this defaults false server-side —
   * see notification-service migration 0005. Do not "harmonise" the defaults.
   */
  marketing_enabled: boolean;
};
