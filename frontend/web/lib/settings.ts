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
};
