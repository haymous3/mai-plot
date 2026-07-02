/**
 * Server-side client for the backend (auth-service for now).
 *
 * Only ever called from Route Handlers / Server Components — the browser talks
 * to same-origin Next routes, which proxy here. This keeps tokens server-side.
 */

export function authServiceUrl(): string {
  return process.env.AUTH_SERVICE_URL ?? 'http://localhost:8011';
}

export function listingServiceUrl(): string {
  return process.env.LISTING_SERVICE_URL ?? 'http://localhost:8012';
}

export function realtorServiceUrl(): string {
  return process.env.REALTOR_SERVICE_URL ?? 'http://localhost:8017';
}

export function notificationServiceUrl(): string {
  return process.env.NOTIFICATION_SERVICE_URL ?? 'http://localhost:8016';
}

export function analyticsServiceUrl(): string {
  return process.env.ANALYTICS_SERVICE_URL ?? 'http://localhost:8018';
}

export function transactionServiceUrl(): string {
  return process.env.TRANSACTION_SERVICE_URL ?? 'http://localhost:8014';
}

export function loanServiceUrl(): string {
  return process.env.LOAN_SERVICE_URL ?? 'http://localhost:8015';
}

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

/** A row in the admin listing-review queue (GET /admin/listings/queue). */
export interface AdminQueueItem {
  id: string;
  seller_id: string;
  title: string;
  state: string;
  lga: string;
  asking_price_kobo: number;
  sale_type: string;
  status: string;
  seller_authority_type: string | null;
  created_at: string;
}

export interface AdminQueueResponse {
  data: AdminQueueItem[];
  pagination: Pagination;
}

export type AuthorityFilter = 'owner' | 'power_of_attorney';

/** A row in the legal-team PoA review queue (GET /admin/poa/queue). */
export interface PoaQueueItem {
  user_id: string;
  owner_name: string | null;
  submitted_at: string;
}

export interface PoaQueueResponse {
  items: PoaQueueItem[];
  pagination: Pagination;
}

/** A row in the admin realtor onboarding queue (GET /admin/realtors/queue).
 * This endpoint returns the pending list only — no pagination envelope. */
export interface RealtorQueueItem {
  id: string;
  esvarbon_number: string | null;
  years_of_experience: number | null;
  coverage_states: string[];
  coverage_lgas: string[];
  created_at: string;
}

export interface RealtorQueueResponse {
  items: RealtorQueueItem[];
}

/** A row in the in-app notification centre (GET /notifications, SCRUM-82). */
export interface NotificationItem {
  id: string;
  channel: string;
  type: string;
  title: string | null;
  body: string;
  reference_type: string | null;
  reference_id: string | null;
  is_read: boolean;
  created_at: string;
  read_at: string | null;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  next_cursor: string | null;
  unread_count: number;
}

/** Per-channel notification preferences (GET/PATCH /notifications/preferences,
 * SCRUM-122). in_app has no flag — it's always delivered. Defaults all-true. */
export interface NotificationPreferences {
  push_enabled: boolean;
  sms_enabled: boolean;
  email_enabled: boolean;
}

/** A row in the admin audit-log viewer (GET /admin/analytics/audit-log,
 * SCRUM-126). old_value/new_value are arbitrary JSON snapshots. */
export interface AuditLogEntry {
  id: string;
  actor_id: string | null;
  actor_role: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogEntry[];
  pagination: Pagination;
}

/** Repayment rollup for one loan (SCRUM-77). Money is BIGINT kobo. The counts
 * are derived server-side; overdue = pending milestone past its due date. */
export interface RepaymentProgress {
  milestone_count: number;
  paid_count: number;
  overdue_count: number;
  total_due_kobo: number;
  total_paid_kobo: number;
  next_due_date: string | null;
}

/** A row in the admin active-loans view (GET /admin/loans, SCRUM-77). */
export interface ActiveLoan {
  loan_id: string;
  buyer_id: string;
  transaction_id: string;
  status: string;
  requested_amount_kobo: number;
  title_released: boolean;
  created_at: string;
  progress: RepaymentProgress;
}

export interface ActiveLoansResponse {
  items: ActiveLoan[];
}

/** A single repayment milestone (GET /loans/{id}/repayments, SCRUM-77). */
export interface RepaymentMilestone {
  due_date: string;
  amount_due_kobo: number;
  amount_paid_kobo: number;
  status: string;
  is_overdue: boolean;
  paid_at: string | null;
  bank_reference: string | null;
}

/** Full repayment schedule for one loan — the admin drill-down. */
export interface LoanRepayments {
  loan_id: string;
  status: string;
  requested_amount_kobo: number;
  title_released: boolean;
  progress: RepaymentProgress;
  milestones: RepaymentMilestone[];
}

/** A buyer's own loan application (GET /loans/me, SCRUM-75/94). */
export interface BuyerLoan {
  id: string;
  transaction_id: string;
  bank_partner_id: string;
  requested_amount_kobo: number;
  tenure_months: number | null;
  status: string;
  bank_reference_id: string | null;
  created_at: string;
}

export interface BuyerLoansResponse {
  items: BuyerLoan[];
}

/** An active bank partner's loan product (GET /loans/bank-partners, SCRUM-94). */
export interface BankPartner {
  id: string;
  name: string;
  short_code: string;
  loan_min_kobo: number;
  loan_max_kobo: number;
  interest_rate_bps: number;
  min_tenure_months: number;
  max_tenure_months: number;
  requires_account_opening: boolean;
}

export interface BankPartnersResponse {
  items: BankPartner[];
}

/** The buyer financing summary (GET /transactions/{id}/financing-summary,
 * SCRUM-94). Money is BIGINT kobo. */
export interface FinancingProperty {
  title: string;
  property_type: string;
  address_text: string;
  lga: string;
  state: string;
  sale_type: string;
  asking_price_kobo: number;
  primary_image_url: string | null;
}

export interface FinancingSummary {
  transaction_id: string;
  stage: string;
  agreed_price_kobo: number;
  max_loan_kobo: number;
  property: FinancingProperty;
  existing_loan: { loan_id: string; status: string } | null;
}

/** Full loan detail for the status/approval page (GET /loans/{id}, SCRUM-94). */
export interface LoanDetail {
  loan_id: string;
  transaction_id: string;
  status: string;
  requested_amount_kobo: number;
  approved_amount_kobo: number | null;
  interest_rate_bps: number | null;
  tenure_months: number | null;
  monthly_instalment_kobo: number | null;
  bank_name: string;
  requires_account_opening: boolean;
  bank_account_opened: boolean;
  bank_decision_at: string | null;
  created_at: string;
  title_released: boolean;
  employment_status: string | null;
  monthly_income_kobo: number | null;
}

export interface LoginSuccess {
  ok: true;
  accessToken: string;
  refreshToken: string;
  role: string;
}

export interface LoginFailure {
  ok: false;
  status: number;
  code: string;
}

/** Call auth-service POST /auth/login. Never throws on a 4xx — returns a typed
 * failure so the caller maps it to a response. */
export async function backendLogin(email: string, password: string): Promise<LoginSuccess | LoginFailure> {
  let resp: Response;
  try {
    resp = await fetch(`${authServiceUrl()}/auth/login`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ email, password }),
      cache: 'no-store',
    });
  } catch {
    return { ok: false, status: 502, code: 'AUTH_SERVICE_UNAVAILABLE' };
  }

  if (!resp.ok) {
    let code = 'INVALID_CREDENTIALS';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // non-JSON error body — keep the default code
    }
    return { ok: false, status: resp.status, code };
  }

  const body = (await resp.json()) as {
    access_token: string;
    refresh_token: string;
    user: { role: string };
  };
  return {
    ok: true,
    accessToken: body.access_token,
    refreshToken: body.refresh_token,
    role: body.user.role,
  };
}
