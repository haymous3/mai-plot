/**
 * Server-side backend access for shared-session (non-admin) pages (SCRUM-98).
 *
 * The buyer/seller/realtor surfaces all use the same `mp_user_*` session cookie,
 * so these are the buyer helpers re-exported under session-neutral names. Use
 * them from seller/realtor Server Components + route handlers.
 */
export {
  buyerBackendGet as sessionBackendGet,
  buyerBackendSend as sessionBackendSend,
} from '@/lib/buyer-server-api';
