-- =============================================================================
-- Maiplot — Demo seed data (idempotent)
-- =============================================================================
-- Populates a coherent end-to-end demo world: buyers, sellers, realtors, admin,
-- listings, offers, transactions across the state machine, inspections, loans,
-- escrow/payments, commissions and notifications.
--
-- Safe to re-run: every row uses a fixed UUID and is deleted-then-reinserted.
-- Your 3 real accounts (…@gmail.com) are never touched.
--
-- All demo users log in with password:  Password123!
--   admin@demo.maiplot.ng      (admin — general admin surfaces)
--   legal@demo.maiplot.ng      (legal_team — PoA review queue)
--   buyer1@demo.maiplot.ng     Chidi Okafor
--   buyer2@demo.maiplot.ng     Aisha Bello
--   buyer3@demo.maiplot.ng     Tunde Adewale
--   seller1@demo.maiplot.ng    Ngozi Eze         (owner)
--   seller2@demo.maiplot.ng    Emeka Nwosu       (power_of_attorney, verified)
--   seller3@demo.maiplot.ng    Fatima Yusuf      (owner)
--   seller4@demo.maiplot.ng    Ibrahim Sani      (power_of_attorney, PENDING — in PoA queue)
--   realtor1@demo.maiplot.ng   Bola Ahmed        (approved)
--   realtor2@demo.maiplot.ng   Grace Peter       (approved)
--
-- Money is BIGINT kobo (1 NGN = 100 kobo).
-- Run: docker exec -i maiplot-postgres psql -U maiplot -d maiplot < scripts/seed_demo_data.sql
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 0. Clean up any prior demo data (children first). Scoped strictly to the
--    fixed UUIDs / demo emails below, so real data is left intact.
-- ---------------------------------------------------------------------------
DELETE FROM notifications             WHERE id::text LIKE 'd9%';
DELETE FROM notification_preferences  WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@demo.maiplot.ng');
DELETE FROM commissions               WHERE id::text LIKE 'd7%';
DELETE FROM loan_repayment_milestones WHERE id::text LIKE 'd8%';
DELETE FROM loans                     WHERE id::text LIKE 'd5%';
DELETE FROM escrow_ledger             WHERE id::text LIKE 'da%';
DELETE FROM payment_events            WHERE id::text LIKE 'db%';
DELETE FROM transaction_events        WHERE id::text LIKE 'dc%';
DELETE FROM inspections               WHERE id::text LIKE 'd4%';
DELETE FROM transactions              WHERE id::text LIKE 'd3%';
DELETE FROM offers                    WHERE id::text LIKE 'd2%';
DELETE FROM saved_listings            WHERE id::text LIKE 'de%';
DELETE FROM listing_interests         WHERE id::text LIKE 'df%';
DELETE FROM listing_media             WHERE id::text LIKE 'dd%';
DELETE FROM listing_documents         WHERE id::text LIKE 'd6%';
DELETE FROM property_listings         WHERE id::text LIKE 'd1%';
DELETE FROM bank_partners             WHERE id::text LIKE 'd0bank%' OR short_code IN ('SHB','GTM');
DELETE FROM payout_accounts           WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@demo.maiplot.ng');
DELETE FROM buyer_profiles            WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@demo.maiplot.ng');
DELETE FROM realtors                  WHERE id IN (SELECT id FROM users WHERE email LIKE '%@demo.maiplot.ng');
DELETE FROM user_pii                  WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@demo.maiplot.ng');
-- Auth children created at runtime by logins / push opt-ins (not by this seed),
-- but they FK to users so must go before the users delete for a clean re-run.
DELETE FROM refresh_tokens            WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@demo.maiplot.ng');
DELETE FROM push_subscriptions        WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@demo.maiplot.ng');
DELETE FROM auth_credentials          WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@demo.maiplot.ng');
DELETE FROM users                     WHERE email LIKE '%@demo.maiplot.ng';

-- ---------------------------------------------------------------------------
-- 1. Users
-- ---------------------------------------------------------------------------
INSERT INTO users (id, role, email, verified_status, seller_authority_type, poa_verified_status, is_active) VALUES
 ('d0000000-0000-0000-0000-000000000001','admin',  'admin@demo.maiplot.ng',   'fully_verified', NULL,                'not_applicable', true),
 ('d0000000-0000-0000-0000-000000000002','legal_team','legal@demo.maiplot.ng','fully_verified', NULL,                'not_applicable', true),
 ('d0000000-0000-0000-0000-000000000011','buyer',  'buyer1@demo.maiplot.ng',  'fully_verified', NULL,                'not_applicable', true),
 ('d0000000-0000-0000-0000-000000000012','buyer',  'buyer2@demo.maiplot.ng',  'fully_verified', NULL,                'not_applicable', true),
 ('d0000000-0000-0000-0000-000000000013','buyer',  'buyer3@demo.maiplot.ng',  'id_verified',    NULL,                'not_applicable', true),
 ('d0000000-0000-0000-0000-000000000021','seller', 'seller1@demo.maiplot.ng', 'fully_verified', 'owner',             'not_applicable', true),
 ('d0000000-0000-0000-0000-000000000022','seller', 'seller2@demo.maiplot.ng', 'fully_verified', 'power_of_attorney', 'verified',       true),
 ('d0000000-0000-0000-0000-000000000023','seller', 'seller3@demo.maiplot.ng', 'fully_verified', 'owner',             'not_applicable', true),
 ('d0000000-0000-0000-0000-000000000024','seller', 'seller4@demo.maiplot.ng', 'phone_verified', 'power_of_attorney', 'pending',         true),
 ('d0000000-0000-0000-0000-000000000031','realtor','realtor1@demo.maiplot.ng','fully_verified', NULL,                'not_applicable', true),
 ('d0000000-0000-0000-0000-000000000032','realtor','realtor2@demo.maiplot.ng','fully_verified', NULL,                'not_applicable', true);

-- Credentials — every demo user shares password "Password123!" (bcrypt)
INSERT INTO auth_credentials (user_id, password_hash)
SELECT id, '$2b$12$YSkpV6UlgD2TGE42oNSpo.uk9N/mgc2iQjNFj4Cp.oirYqgAIUUGm'
FROM users WHERE email LIKE '%@demo.maiplot.ng';

-- PII (phone unique, full_name required). BVN/NIN would be bcrypt hashes; omitted here.
INSERT INTO user_pii (user_id, phone, full_name, poa_document_owner_name, poa_document_s3_key, employment_status, monthly_income_kobo) VALUES
 ('d0000000-0000-0000-0000-000000000001','+2348030000001','Maiplot Admin',   NULL,               NULL,                          NULL,           NULL),
 ('d0000000-0000-0000-0000-000000000002','+2348030000002','Maiplot Legal',   NULL,               NULL,                          NULL,           NULL),
 ('d0000000-0000-0000-0000-000000000011','+2348030000011','Chidi Okafor',    NULL,               NULL,                          'employed',     85000000),
 ('d0000000-0000-0000-0000-000000000012','+2348030000012','Aisha Bello',     NULL,               NULL,                          'self_employed',120000000),
 ('d0000000-0000-0000-0000-000000000013','+2348030000013','Tunde Adewale',   NULL,               NULL,                          'employed',     65000000),
 ('d0000000-0000-0000-0000-000000000021','+2348030000021','Ngozi Eze',       NULL,               NULL,                          NULL,           NULL),
 ('d0000000-0000-0000-0000-000000000022','+2348030000022','Emeka Nwosu',     'Chief B. Nwosu',   's3://demo/poa/emeka.pdf',     NULL,           NULL),
 ('d0000000-0000-0000-0000-000000000023','+2348030000023','Fatima Yusuf',    NULL,               NULL,                          NULL,           NULL),
 ('d0000000-0000-0000-0000-000000000024','+2348030000024','Ibrahim Sani',    'Alhaji K. Sani',   's3://demo/poa/ibrahim.pdf',   NULL,           NULL),
 ('d0000000-0000-0000-0000-000000000031','+2348030000031','Bola Ahmed',      NULL,               NULL,                          NULL,           NULL),
 ('d0000000-0000-0000-0000-000000000032','+2348030000032','Grace Peter',     NULL,               NULL,                          NULL,           NULL);

-- Buyer profiles
INSERT INTO buyer_profiles (id, user_id, employment_status, preferred_location, budget_kobo) VALUES
 ('d0b00000-0000-0000-0000-000000000011','d0000000-0000-0000-0000-000000000011','employed',     'Lagos',         9000000000),
 ('d0b00000-0000-0000-0000-000000000012','d0000000-0000-0000-0000-000000000012','self_employed','Abuja',        16000000000),
 ('d0b00000-0000-0000-0000-000000000013','d0000000-0000-0000-0000-000000000013','employed',     'Port Harcourt', 6000000000);

-- Realtor profiles (id == user id). Both approved by admin.
INSERT INTO realtors (id, esvarbon_number, years_of_experience, coverage_states, coverage_lgas, completed_deals, approval_status, approved_by, approved_at, base_location) VALUES
 ('d0000000-0000-0000-0000-000000000031','ESV-2021-04412', 7, ARRAY['Lagos'],         ARRAY['Eti-Osa','Lagos Island','Surulere'], 12, 'approved','d0000000-0000-0000-0000-000000000001', now() - interval '120 days', ST_SetSRID(ST_MakePoint(3.4210,6.4281),4326)::geography),
 ('d0000000-0000-0000-0000-000000000032','ESV-2022-09873', 4, ARRAY['Abuja','Lagos'], ARRAY['Abuja Municipal','Gwarinpa'],        5,  'approved','d0000000-0000-0000-0000-000000000001', now() - interval '80 days',  ST_SetSRID(ST_MakePoint(7.4913,9.0579),4326)::geography);

-- Payout accounts (sellers + realtors)
INSERT INTO payout_accounts (user_id, account_number, bank_code, account_name) VALUES
 ('d0000000-0000-0000-0000-000000000021','0123456701','058','Ngozi Eze'),
 ('d0000000-0000-0000-0000-000000000023','0123456703','011','Fatima Yusuf'),
 ('d0000000-0000-0000-0000-000000000031','0123456731','057','Bola Ahmed'),
 ('d0000000-0000-0000-0000-000000000032','0123456732','033','Grace Peter');

-- Notification preferences (defaults)
INSERT INTO notification_preferences (user_id, push_enabled, sms_enabled, email_enabled)
SELECT id, true, true, true FROM users WHERE email LIKE '%@demo.maiplot.ng';

-- ---------------------------------------------------------------------------
-- 2. Bank partners
-- ---------------------------------------------------------------------------
INSERT INTO bank_partners (id, name, short_code, api_base_url, loan_min_kobo, loan_max_kobo, interest_rate_bps, min_tenure_months, max_tenure_months, requires_account_opening, is_active) VALUES
 ('d0ba0000-0000-0000-0000-00000000da01','Sterling Homes Bank','SHB','https://bank-001.demo.local', 500000000, 10000000000, 2200, 12, 240, true, true),
 ('d0ba0000-0000-0000-0000-00000000da02','GTBank Mortgage',    'GTM','https://bank-002.demo.local',1000000000, 15000000000, 1900, 24, 300, true, true);

-- ---------------------------------------------------------------------------
-- 3. Property listings
--    id d1..  ·  seller ids: s1=…21 s2=…22(PoA) s3=…23  ·  real seller reused
--    Lagos (3.42,6.44) · Port Harcourt (7.01,4.82) · Abuja (7.49,9.06)
-- ---------------------------------------------------------------------------
INSERT INTO property_listings
 (id, seller_id, property_type, title, description, address_text, location, lga, state, size_sqm, asking_price_kobo, sale_type, urgency_tag, status, doc_verification_status, view_count, interest_count, expires_at, created_at) VALUES
 ('d1000000-0000-0000-0000-000000000001','d0000000-0000-0000-0000-000000000021','residential','3-Bed Flat, Lekki Phase 1','Spacious 3-bedroom flat, all rooms ensuite, 24/7 power.','12 Admiralty Way, Lekki Phase 1', ST_SetSRID(ST_MakePoint(3.4720,6.4430),4326)::geography,'Eti-Osa','Lagos',180, 8500000000,'distress','7_days','active','verified', 342, 8, now()+interval '7 days',  now()-interval '3 days'),
 ('d1000000-0000-0000-0000-000000000002','d0000000-0000-0000-0000-000000000021','land','500sqm Land, Ajah','Dry land, C of O, in a gated estate.','Sangotedo, Ajah', ST_SetSRID(ST_MakePoint(3.5810,6.4670),4326)::geography,'Eti-Osa','Lagos',500, 3500000000,'normal',NULL,'active','verified', 121, 3, now()+interval '90 days', now()-interval '10 days'),
 ('d1000000-0000-0000-0000-000000000003','d0000000-0000-0000-0000-000000000022','commercial','Warehouse, Trans-Amadi','1,200sqm warehouse with loading bay and office block.','Trans-Amadi Industrial Layout', ST_SetSRID(ST_MakePoint(7.0330,4.8090),4326)::geography,'Port Harcourt','Rivers',1200, 12000000000,'distress','14_days','active','verified', 210, 5, now()+interval '14 days', now()-interval '5 days'),
 ('d1000000-0000-0000-0000-000000000004','d0000000-0000-0000-0000-000000000023','residential','4-Bed Duplex, Gwarinpa','Fully detached duplex with BQ, fitted kitchen.','7th Avenue, Gwarinpa', ST_SetSRID(ST_MakePoint(7.4090,9.1100),4326)::geography,'Abuja Municipal','FCT',420, 15000000000,'normal',NULL,'active','verified', 288, 6, now()+interval '90 days', now()-interval '14 days'),
 ('d1000000-0000-0000-0000-000000000005','d0000000-0000-0000-0000-000000000023','residential','2-Bed Apartment, Yaba','Renovated 2-bed, close to tech hub.','Herbert Macaulay Way, Yaba', ST_SetSRID(ST_MakePoint(3.3760,6.5090),4326)::geography,'Lagos Mainland','Lagos',95, 4500000000,'distress','30_days','under_offer','verified', 456, 11, now()+interval '30 days', now()-interval '20 days'),
 ('d1000000-0000-0000-0000-000000000006','d0000000-0000-0000-0000-000000000022','land','1000sqm Land, Ibeju-Lekki','Two plots, survey plan available, awaiting verification.','Eleko, Ibeju-Lekki', ST_SetSRID(ST_MakePoint(3.7010,6.4300),4326)::geography,'Ibeju-Lekki','Lagos',1000, 6000000000,'normal',NULL,'pending_review','pending', 0, 0, NULL, now()-interval '1 day'),
 ('d1000000-0000-0000-0000-000000000007','03831c21-9a0d-4e20-a574-7cf72d13dfa8','commercial','Office Space, Central Area','Grade-A office, 600sqm, central district.','Central Business District', ST_SetSRID(ST_MakePoint(7.4930,9.0360),4326)::geography,'Abuja Municipal','FCT',600, 9500000000,'normal',NULL,'active','verified', 175, 4, now()+interval '90 days', now()-interval '8 days'),
 ('d1000000-0000-0000-0000-000000000008','d0000000-0000-0000-0000-000000000021','residential','Bungalow, GRA Phase 2','3-bed bungalow, quiet neighbourhood.','GRA Phase 2, Port Harcourt', ST_SetSRID(ST_MakePoint(7.0060,4.8280),4326)::geography,'Port Harcourt','Rivers',260, 5500000000,'distress','7_days','active','verified', 198, 7, now()+interval '7 days',  now()-interval '2 days'),
 ('d1000000-0000-0000-0000-000000000009','d0000000-0000-0000-0000-000000000023','residential','Terrace, Ikoyi','Luxury 4-bed terrace, sold via Maiplot.','Bourdillon Road, Ikoyi', ST_SetSRID(ST_MakePoint(3.4380,6.4520),4326)::geography,'Eti-Osa','Lagos',380, 21000000000,'normal',NULL,'sold','verified', 812, 22, NULL, now()-interval '75 days'),
 ('d1000000-0000-0000-0000-00000000000a','d0000000-0000-0000-0000-000000000021','land','800sqm Land, Epe','Land near the expressway, listing paused by seller.','Epe Town', ST_SetSRID(ST_MakePoint(3.9830,6.5840),4326)::geography,'Epe','Lagos',800, 2800000000,'normal',NULL,'paused','verified', 44, 1, NULL, now()-interval '30 days'),
 ('d1000000-0000-0000-0000-00000000000b','d0000000-0000-0000-0000-000000000023','residential','Mini Flat, Surulere','Compact mini flat, great rental yield.','Adeniran Ogunsanya, Surulere', ST_SetSRID(ST_MakePoint(3.3510,6.4980),4326)::geography,'Surulere','Lagos',48, 2200000000,'distress','14_days','under_offer','verified', 263, 9, now()+interval '14 days', now()-interval '12 days'),
 ('d1000000-0000-0000-0000-00000000000c','d0000000-0000-0000-0000-000000000022','residential','3-Bed, Lugbe','Estate house with title, inspection completed.','Lugbe District', ST_SetSRID(ST_MakePoint(7.3760,8.9760),4326)::geography,'Abuja Municipal','FCT',210, 4800000000,'normal',NULL,'under_offer','verified', 301, 10, now()+interval '90 days', now()-interval '18 days'),
 ('d1000000-0000-0000-0000-00000000000d','d0000000-0000-0000-0000-000000000021','residential','Semi-Detached, Magodo','4-bed semi-detached, loan application in progress.','Magodo GRA Phase 2', ST_SetSRID(ST_MakePoint(3.3830,6.6210),4326)::geography,'Kosofe','Lagos',300, 7500000000,'distress','30_days','under_offer','verified', 389, 13, now()+interval '30 days', now()-interval '16 days'),
 ('d1000000-0000-0000-0000-00000000000e','d0000000-0000-0000-0000-000000000023','residential','Bungalow, Kubwa','3-bed bungalow, loan approved, awaiting disbursement.','Phase 4, Kubwa', ST_SetSRID(ST_MakePoint(7.3400,9.1520),4326)::geography,'Bwari','FCT',240, 6800000000,'normal',NULL,'under_offer','verified', 254, 8, now()+interval '90 days', now()-interval '22 days');

-- Listing media (photos). Placeholder CDN urls.
INSERT INTO listing_media (id, listing_id, media_type, s3_key, cdn_url, sort_order) VALUES
 ('dd000000-0000-0000-0000-000000000101','d1000000-0000-0000-0000-000000000001','photo','media/l1/1.jpg','https://cdn.maiplot.ng/demo/l1-1.jpg',0),
 ('dd000000-0000-0000-0000-000000000102','d1000000-0000-0000-0000-000000000001','photo','media/l1/2.jpg','https://cdn.maiplot.ng/demo/l1-2.jpg',1),
 ('dd000000-0000-0000-0000-000000000103','d1000000-0000-0000-0000-000000000001','photo','media/l1/3.jpg','https://cdn.maiplot.ng/demo/l1-3.jpg',2),
 ('dd000000-0000-0000-0000-000000000201','d1000000-0000-0000-0000-000000000002','photo','media/l2/1.jpg','https://cdn.maiplot.ng/demo/l2-1.jpg',0),
 ('dd000000-0000-0000-0000-000000000301','d1000000-0000-0000-0000-000000000003','photo','media/l3/1.jpg','https://cdn.maiplot.ng/demo/l3-1.jpg',0),
 ('dd000000-0000-0000-0000-000000000302','d1000000-0000-0000-0000-000000000003','photo','media/l3/2.jpg','https://cdn.maiplot.ng/demo/l3-2.jpg',1),
 ('dd000000-0000-0000-0000-000000000401','d1000000-0000-0000-0000-000000000004','photo','media/l4/1.jpg','https://cdn.maiplot.ng/demo/l4-1.jpg',0),
 ('dd000000-0000-0000-0000-000000000402','d1000000-0000-0000-0000-000000000004','photo','media/l4/2.jpg','https://cdn.maiplot.ng/demo/l4-2.jpg',1),
 ('dd000000-0000-0000-0000-000000000501','d1000000-0000-0000-0000-000000000005','photo','media/l5/1.jpg','https://cdn.maiplot.ng/demo/l5-1.jpg',0),
 ('dd000000-0000-0000-0000-000000000701','d1000000-0000-0000-0000-000000000007','photo','media/l7/1.jpg','https://cdn.maiplot.ng/demo/l7-1.jpg',0),
 ('dd000000-0000-0000-0000-000000000801','d1000000-0000-0000-0000-000000000008','photo','media/l8/1.jpg','https://cdn.maiplot.ng/demo/l8-1.jpg',0),
 ('dd000000-0000-0000-0000-000000000901','d1000000-0000-0000-0000-000000000009','photo','media/l9/1.jpg','https://cdn.maiplot.ng/demo/l9-1.jpg',0),
 ('dd000000-0000-0000-0000-000000000b01','d1000000-0000-0000-0000-00000000000b','photo','media/lb/1.jpg','https://cdn.maiplot.ng/demo/lb-1.jpg',0),
 ('dd000000-0000-0000-0000-000000000c01','d1000000-0000-0000-0000-00000000000c','photo','media/lc/1.jpg','https://cdn.maiplot.ng/demo/lc-1.jpg',0),
 ('dd000000-0000-0000-0000-000000000d01','d1000000-0000-0000-0000-00000000000d','photo','media/ld/1.jpg','https://cdn.maiplot.ng/demo/ld-1.jpg',0),
 ('dd000000-0000-0000-0000-000000000e01','d1000000-0000-0000-0000-00000000000e','photo','media/le/1.jpg','https://cdn.maiplot.ng/demo/le-1.jpg',0);

-- Listing documents (title docs)
INSERT INTO listing_documents (id, listing_id, document_type, s3_key, verification_status, verified_by_user_id, watermark_applied) VALUES
 ('d6d00000-0000-0000-0000-000000000001','d1000000-0000-0000-0000-000000000001','c_of_o','docs/l1/cofo.pdf','verified','d0000000-0000-0000-0000-000000000001',true),
 ('d6d00000-0000-0000-0000-000000000003','d1000000-0000-0000-0000-000000000003','deed_of_assignment','docs/l3/deed.pdf','verified','d0000000-0000-0000-0000-000000000001',true),
 ('d6d00000-0000-0000-0000-000000000006','d1000000-0000-0000-0000-000000000006','survey_plan','docs/l6/survey.pdf','pending',NULL,false),
 ('d6d00000-0000-0000-0000-000000000009','d1000000-0000-0000-0000-000000000009','c_of_o','docs/l9/cofo.pdf','verified','d0000000-0000-0000-0000-000000000001',true);

-- ---------------------------------------------------------------------------
-- 4. Buyer engagement: saved listings + expressed interest
-- ---------------------------------------------------------------------------
INSERT INTO saved_listings (id, buyer_id, listing_id) VALUES
 ('de000000-0000-0000-0000-000000000001','d0000000-0000-0000-0000-000000000011','d1000000-0000-0000-0000-000000000001'),
 ('de000000-0000-0000-0000-000000000002','d0000000-0000-0000-0000-000000000011','d1000000-0000-0000-0000-000000000003'),
 ('de000000-0000-0000-0000-000000000003','d0000000-0000-0000-0000-000000000011','d1000000-0000-0000-0000-000000000004'),
 ('de000000-0000-0000-0000-000000000004','d0000000-0000-0000-0000-000000000012','d1000000-0000-0000-0000-000000000002'),
 ('de000000-0000-0000-0000-000000000005','d0000000-0000-0000-0000-000000000012','d1000000-0000-0000-0000-000000000008'),
 ('de000000-0000-0000-0000-000000000006','d0000000-0000-0000-0000-000000000013','d1000000-0000-0000-0000-000000000001'),
 ('de000000-0000-0000-0000-000000000007','d0000000-0000-0000-0000-000000000013','d1000000-0000-0000-0000-000000000007'),
 ('de000000-0000-0000-0000-000000000008','4da5400f-d798-4663-99d7-7944f2b9dc11','d1000000-0000-0000-0000-000000000004');

INSERT INTO listing_interests (id, buyer_id, listing_id, message) VALUES
 ('df000000-0000-0000-0000-000000000001','d0000000-0000-0000-0000-000000000012','d1000000-0000-0000-0000-000000000001','Is the price negotiable? Ready to move fast.'),
 ('df000000-0000-0000-0000-000000000002','d0000000-0000-0000-0000-000000000013','d1000000-0000-0000-0000-000000000007','Please share inspection availability.'),
 ('df000000-0000-0000-0000-000000000003','d0000000-0000-0000-0000-000000000011','d1000000-0000-0000-0000-000000000008','Interested — can we arrange a viewing this week?');

-- ---------------------------------------------------------------------------
-- 5. Offers
-- ---------------------------------------------------------------------------
INSERT INTO offers (id, listing_id, buyer_id, offered_price_kobo, note, status, counter_price_kobo, expires_at) VALUES
 ('d2000000-0000-0000-0000-000000000001','d1000000-0000-0000-0000-000000000001','d0000000-0000-0000-0000-000000000012', 8000000000,'Offer slightly below asking.','pending',   NULL,       now()+interval '3 days'),
 ('d2000000-0000-0000-0000-000000000002','d1000000-0000-0000-0000-000000000002','d0000000-0000-0000-0000-000000000013', 3000000000,'First offer.',                'countered', 3300000000, now()+interval '2 days'),
 ('d2000000-0000-0000-0000-000000000003','d1000000-0000-0000-0000-000000000003','d0000000-0000-0000-0000-000000000011',10500000000,'Cash buyer.',                 'rejected',  NULL,       now()-interval '1 day'),
 ('d2000000-0000-0000-0000-000000000004','d1000000-0000-0000-0000-000000000004','d0000000-0000-0000-0000-000000000011',14500000000,'Interested at this price.',   'pending',   NULL,       now()+interval '4 days'),
 ('d2000000-0000-0000-0000-000000000005','d1000000-0000-0000-0000-000000000008','d0000000-0000-0000-0000-000000000013', 5300000000,'Withdrawn — found another.',  'withdrawn', NULL,       now()-interval '2 days'),
 -- accepted offers that spawned transactions
 ('d2000000-0000-0000-0000-0000000000a1','d1000000-0000-0000-0000-000000000005','d0000000-0000-0000-0000-000000000011', 4300000000,'Accepted.','accepted',NULL, now()+interval '2 days'),
 ('d2000000-0000-0000-0000-0000000000a2','d1000000-0000-0000-0000-00000000000b','d0000000-0000-0000-0000-000000000012', 2200000000,'Accepted.','accepted',NULL, now()+interval '2 days'),
 ('d2000000-0000-0000-0000-0000000000a3','d1000000-0000-0000-0000-00000000000c','d0000000-0000-0000-0000-000000000013', 4800000000,'Accepted.','accepted',NULL, now()+interval '2 days'),
 ('d2000000-0000-0000-0000-0000000000a4','d1000000-0000-0000-0000-00000000000d','d0000000-0000-0000-0000-000000000011', 7500000000,'Accepted.','accepted',NULL, now()+interval '2 days'),
 ('d2000000-0000-0000-0000-0000000000a5','d1000000-0000-0000-0000-00000000000e','d0000000-0000-0000-0000-000000000012', 6800000000,'Accepted.','accepted',NULL, now()+interval '2 days'),
 ('d2000000-0000-0000-0000-0000000000a6','d1000000-0000-0000-0000-000000000009','d0000000-0000-0000-0000-000000000013',20500000000,'Accepted.','accepted',NULL, now()-interval '60 days');

-- ---------------------------------------------------------------------------
-- 6. Transactions (spanning the state machine) + events
--    T1 offer_accepted · T2 inspection_scheduled · T3 inspection_completed
--    T4 loan_applied · T5 loan_approved · T6 completed
-- ---------------------------------------------------------------------------
INSERT INTO transactions (id, listing_id, buyer_id, seller_id, realtor_id, agreed_price_kobo, platform_fee_kobo, loan_id, stage, lock_expires_at, created_at) VALUES
 ('d3000000-0000-0000-0000-000000000001','d1000000-0000-0000-0000-000000000005','d0000000-0000-0000-0000-000000000011','d0000000-0000-0000-0000-000000000023',NULL,                                4300000000, NULL, NULL,                                   'offer_accepted',      now()+interval '48 hours', now()-interval '1 day'),
 ('d3000000-0000-0000-0000-000000000002','d1000000-0000-0000-0000-00000000000b','d0000000-0000-0000-0000-000000000012','d0000000-0000-0000-0000-000000000023','d0000000-0000-0000-0000-000000000031',2200000000, NULL, NULL,                                   'inspection_scheduled',now()+interval '60 hours', now()-interval '2 days'),
 ('d3000000-0000-0000-0000-000000000003','d1000000-0000-0000-0000-00000000000c','d0000000-0000-0000-0000-000000000013','d0000000-0000-0000-0000-000000000022','d0000000-0000-0000-0000-000000000032',4800000000, NULL, NULL,                                   'inspection_completed',now()+interval '40 hours', now()-interval '4 days'),
 ('d3000000-0000-0000-0000-000000000004','d1000000-0000-0000-0000-00000000000d','d0000000-0000-0000-0000-000000000011','d0000000-0000-0000-0000-000000000021',NULL,                                7500000000, NULL, 'd5000000-0000-0000-0000-000000000004', 'loan_applied',        now()+interval '36 hours', now()-interval '3 days'),
 ('d3000000-0000-0000-0000-000000000005','d1000000-0000-0000-0000-00000000000e','d0000000-0000-0000-0000-000000000012','d0000000-0000-0000-0000-000000000023',NULL,                                6800000000, NULL, 'd5000000-0000-0000-0000-000000000005', 'loan_approved',       now()+interval '24 hours', now()-interval '6 days'),
 ('d3000000-0000-0000-0000-000000000006','d1000000-0000-0000-0000-000000000009','d0000000-0000-0000-0000-000000000013','d0000000-0000-0000-0000-000000000023','d0000000-0000-0000-0000-000000000031',20500000000, 512500000, NULL,                                  'completed',           NULL,                      now()-interval '60 days');

INSERT INTO transaction_events (id, transaction_id, event_type, from_stage, to_stage, triggered_by, created_at) VALUES
 -- T1
 ('dc000000-0000-0000-0000-000000000101','d3000000-0000-0000-0000-000000000001','offer_accepted',    NULL,                  'offer_accepted',      'd0000000-0000-0000-0000-000000000023', now()-interval '1 day'),
 -- T2
 ('dc000000-0000-0000-0000-000000000201','d3000000-0000-0000-0000-000000000002','offer_accepted',    NULL,                  'offer_accepted',      'd0000000-0000-0000-0000-000000000023', now()-interval '2 days'),
 ('dc000000-0000-0000-0000-000000000202','d3000000-0000-0000-0000-000000000002','inspection_scheduled','offer_accepted',    'inspection_scheduled','d0000000-0000-0000-0000-000000000031', now()-interval '1 day'),
 -- T3
 ('dc000000-0000-0000-0000-000000000301','d3000000-0000-0000-0000-000000000003','offer_accepted',    NULL,                  'offer_accepted',      'd0000000-0000-0000-0000-000000000022', now()-interval '4 days'),
 ('dc000000-0000-0000-0000-000000000302','d3000000-0000-0000-0000-000000000003','inspection_scheduled','offer_accepted',    'inspection_scheduled','d0000000-0000-0000-0000-000000000032', now()-interval '3 days'),
 ('dc000000-0000-0000-0000-000000000303','d3000000-0000-0000-0000-000000000003','inspection_completed','inspection_scheduled','inspection_completed','d0000000-0000-0000-0000-000000000032', now()-interval '2 days'),
 -- T4
 ('dc000000-0000-0000-0000-000000000401','d3000000-0000-0000-0000-000000000004','offer_accepted',    NULL,                  'offer_accepted',      'd0000000-0000-0000-0000-000000000021', now()-interval '3 days'),
 ('dc000000-0000-0000-0000-000000000402','d3000000-0000-0000-0000-000000000004','loan_applied',      'offer_accepted',      'loan_applied',        'd0000000-0000-0000-0000-000000000011', now()-interval '2 days'),
 -- T5
 ('dc000000-0000-0000-0000-000000000501','d3000000-0000-0000-0000-000000000005','offer_accepted',    NULL,                  'offer_accepted',      'd0000000-0000-0000-0000-000000000023', now()-interval '6 days'),
 ('dc000000-0000-0000-0000-000000000502','d3000000-0000-0000-0000-000000000005','loan_applied',      'offer_accepted',      'loan_applied',        'd0000000-0000-0000-0000-000000000012', now()-interval '5 days'),
 ('dc000000-0000-0000-0000-000000000503','d3000000-0000-0000-0000-000000000005','loan_approved',     'loan_applied',        'loan_approved',       NULL,                                   now()-interval '2 days'),
 -- T6 (full journey)
 ('dc000000-0000-0000-0000-000000000601','d3000000-0000-0000-0000-000000000006','offer_accepted',    NULL,                  'offer_accepted',      'd0000000-0000-0000-0000-000000000023', now()-interval '60 days'),
 ('dc000000-0000-0000-0000-000000000602','d3000000-0000-0000-0000-000000000006','inspection_completed','offer_accepted',    'inspection_completed','d0000000-0000-0000-0000-000000000031', now()-interval '52 days'),
 ('dc000000-0000-0000-0000-000000000603','d3000000-0000-0000-0000-000000000006','payment_held',      'inspection_completed', 'payment_held',        'd0000000-0000-0000-0000-000000000013', now()-interval '40 days'),
 ('dc000000-0000-0000-0000-000000000604','d3000000-0000-0000-0000-000000000006','title_held',        'payment_held',        'title_held',          'd0000000-0000-0000-0000-000000000001', now()-interval '20 days'),
 ('dc000000-0000-0000-0000-000000000605','d3000000-0000-0000-0000-000000000006','completed',         'title_held',          'completed',           'd0000000-0000-0000-0000-000000000001', now()-interval '15 days');

-- ---------------------------------------------------------------------------
-- 7. Inspections
-- ---------------------------------------------------------------------------
INSERT INTO inspections (id, transaction_id, realtor_id, proposed_date, confirmed_date, status, gps_lat, gps_lng, report_submitted_at, report_data, assignment_expires_at, created_at) VALUES
 ('d4000000-0000-0000-0000-000000000002','d3000000-0000-0000-0000-000000000002','d0000000-0000-0000-0000-000000000031', now()+interval '2 days', NULL,                    'pending',   NULL,   NULL,   NULL,                    NULL,                                        now()+interval '2 hours', now()-interval '1 day'),
 ('d4000000-0000-0000-0000-000000000003','d3000000-0000-0000-0000-000000000003','d0000000-0000-0000-0000-000000000032', now()-interval '3 days', now()-interval '2 days', 'completed', 8.9760, 7.3760, now()-interval '2 days', '{"structure":"good","access_road":"tarred","occupancy":"vacant","notes":"Property matches listing. Minor repainting needed."}'::jsonb, now()-interval '2 days', now()-interval '3 days'),
 ('d4000000-0000-0000-0000-000000000006','d3000000-0000-0000-0000-000000000006','d0000000-0000-0000-0000-000000000031', now()-interval '55 days',now()-interval '54 days','completed', 6.4520, 3.4380, now()-interval '53 days','{"structure":"excellent","access_road":"tarred","occupancy":"vacant","notes":"Premium finish, move-in ready."}'::jsonb, now()-interval '54 days', now()-interval '56 days');

-- ---------------------------------------------------------------------------
-- 8. Loans (+ repayment milestones for the approved one)
--    Loan cap = 50% of agreed price.
-- ---------------------------------------------------------------------------
INSERT INTO loans (id, transaction_id, buyer_id, bank_partner_id, requested_amount_kobo, approved_amount_kobo, interest_rate_bps, tenure_months, monthly_instalment_kobo, status, bank_reference_id, bank_decision_at, bank_account_opened, created_at) VALUES
 ('d5000000-0000-0000-0000-000000000004','d3000000-0000-0000-0000-000000000004','d0000000-0000-0000-0000-000000000011','d0ba0000-0000-0000-0000-00000000da01', 3750000000, NULL,       NULL, NULL, NULL,      'under_review', 'SHB-APP-100482', NULL,                    false, now()-interval '2 days'),
 ('d5000000-0000-0000-0000-000000000005','d3000000-0000-0000-0000-000000000005','d0000000-0000-0000-0000-000000000012','d0ba0000-0000-0000-0000-00000000da02', 3400000000, 3400000000, 1900, 240,  54800000,  'approved',     'GTM-APP-772013', now()-interval '2 days', true,  now()-interval '5 days');

INSERT INTO loan_repayment_milestones (id, loan_id, due_date, amount_due_kobo, amount_paid_kobo, status) VALUES
 ('d8000000-0000-0000-0000-000000000501','d5000000-0000-0000-0000-000000000005', (now()+interval '30 days')::date, 54800000, 0, 'pending'),
 ('d8000000-0000-0000-0000-000000000502','d5000000-0000-0000-0000-000000000005', (now()+interval '60 days')::date, 54800000, 0, 'pending'),
 ('d8000000-0000-0000-0000-000000000503','d5000000-0000-0000-0000-000000000005', (now()+interval '90 days')::date, 54800000, 0, 'pending');

-- ---------------------------------------------------------------------------
-- 9. Money trail for the completed deal T6 (agreed ₦205,000,000)
--    Buyer deposit → escrow → platform fee + seller disbursement + commission.
--    Deposit > ₦10M so the escrow entry is dual-approved.
-- ---------------------------------------------------------------------------
INSERT INTO payment_events (id, idempotency_key, payer_id, payee_id, transaction_id, amount_kobo, payment_type, provider, provider_reference, status, created_at) VALUES
 ('db000000-0000-0000-0000-000000000601','db111111-0000-0000-0000-000000000601','d0000000-0000-0000-0000-000000000013','d0000000-0000-0000-0000-000000000023','d3000000-0000-0000-0000-000000000006',20500000000,'buyer_deposit',      'paystack','PSK_DEP_9f2a', 'completed', now()-interval '40 days'),
 ('db000000-0000-0000-0000-000000000602','db111111-0000-0000-0000-000000000602','d0000000-0000-0000-0000-000000000023',NULL,                                  'd3000000-0000-0000-0000-000000000006',  512500000,'platform_fee',       'paystack','PSK_FEE_9f2b', 'completed', now()-interval '16 days'),
 ('db000000-0000-0000-0000-000000000603','db111111-0000-0000-0000-000000000603','d0000000-0000-0000-0000-000000000023','d0000000-0000-0000-0000-000000000023','d3000000-0000-0000-0000-000000000006',19577500000,'seller_disbursement','paystack','PSK_SEL_9f2c', 'completed', now()-interval '15 days'),
 ('db000000-0000-0000-0000-000000000604','db111111-0000-0000-0000-000000000604','d0000000-0000-0000-0000-000000000023','d0000000-0000-0000-0000-000000000031','d3000000-0000-0000-0000-000000000006',  410000000,'realtor_commission', 'paystack','PSK_COM_9f2d', 'completed', now()-interval '14 days');

INSERT INTO escrow_ledger (id, transaction_id, entry_type, amount_kobo, description, payment_event_id, requires_dual_approval, approved_by_1, approved_by_2, approved_at, created_at) VALUES
 ('da000000-0000-0000-0000-000000000601','d3000000-0000-0000-0000-000000000006','credit',20500000000,'Buyer deposit received',      'db000000-0000-0000-0000-000000000601', true,  'd0000000-0000-0000-0000-000000000001','d0000000-0000-0000-0000-000000000001', now()-interval '39 days', now()-interval '40 days'),
 ('da000000-0000-0000-0000-000000000602','d3000000-0000-0000-0000-000000000006','debit',   512500000,'Platform fee',                'db000000-0000-0000-0000-000000000602', false, NULL,                                  NULL,                                  NULL,                       now()-interval '16 days'),
 ('da000000-0000-0000-0000-000000000603','d3000000-0000-0000-0000-000000000006','debit', 19577500000,'Seller disbursement (net)',   'db000000-0000-0000-0000-000000000603', true,  'd0000000-0000-0000-0000-000000000001','d0000000-0000-0000-0000-000000000001', now()-interval '15 days', now()-interval '15 days'),
 ('da000000-0000-0000-0000-000000000604','d3000000-0000-0000-0000-000000000006','debit',   410000000,'Realtor commission (2%)',     'db000000-0000-0000-0000-000000000604', false, NULL,                                  NULL,                                  NULL,                       now()-interval '14 days');

-- ---------------------------------------------------------------------------
-- 10. Commissions
--     T6 closed → available; T3 in-flight → pending.
-- ---------------------------------------------------------------------------
INSERT INTO commissions (id, realtor_id, transaction_id, inspection_id, amount_kobo, rate_bps, status, available_at, created_at) VALUES
 ('d7000000-0000-0000-0000-000000000006','d0000000-0000-0000-0000-000000000031','d3000000-0000-0000-0000-000000000006','d4000000-0000-0000-0000-000000000006', 410000000, 200, 'available', now()-interval '12 days', now()-interval '15 days'),
 ('d7000000-0000-0000-0000-000000000003','d0000000-0000-0000-0000-000000000032','d3000000-0000-0000-0000-000000000003','d4000000-0000-0000-0000-000000000003',  96000000, 200, 'pending',   now()+interval '30 days', now()-interval '2 days');

-- ---------------------------------------------------------------------------
-- 11. Notifications (in-app), a mix of read / unread
-- ---------------------------------------------------------------------------
INSERT INTO notifications (id, user_id, channel, type, title, body, reference_type, reference_id, is_read, sent_at, created_at) VALUES
 ('d9000000-0000-0000-0000-000000000001','d0000000-0000-0000-0000-000000000011','in_app','offer_accepted','Offer accepted','Your offer on 2-Bed Apartment, Yaba was accepted.','transaction','d3000000-0000-0000-0000-000000000001', false, now()-interval '1 day',  now()-interval '1 day'),
 ('d9000000-0000-0000-0000-000000000002','d0000000-0000-0000-0000-000000000011','in_app','loan_update','Loan application received','Sterling Homes Bank is reviewing your loan application.','loan','d5000000-0000-0000-0000-000000000004', true,  now()-interval '2 days', now()-interval '2 days'),
 ('d9000000-0000-0000-0000-000000000003','d0000000-0000-0000-0000-000000000012','in_app','inspection_scheduled','Inspection scheduled','A realtor has been assigned to inspect Mini Flat, Surulere.','transaction','d3000000-0000-0000-0000-000000000002', false, now()-interval '1 day',  now()-interval '1 day'),
 ('d9000000-0000-0000-0000-000000000004','d0000000-0000-0000-0000-000000000012','in_app','loan_update','Loan approved','GTBank Mortgage approved your ₦34,000,000 loan.','loan','d5000000-0000-0000-0000-000000000005', false, now()-interval '2 days', now()-interval '2 days'),
 ('d9000000-0000-0000-0000-000000000005','d0000000-0000-0000-0000-000000000013','in_app','inspection_completed','Inspection completed','The inspection report for 3-Bed, Lugbe is ready.','transaction','d3000000-0000-0000-0000-000000000003', true,  now()-interval '2 days', now()-interval '2 days'),
 ('d9000000-0000-0000-0000-000000000006','d0000000-0000-0000-0000-000000000013','in_app','deal_completed','Congratulations!','Your purchase of Terrace, Ikoyi is complete. Title transferred.','transaction','d3000000-0000-0000-0000-000000000006', true,  now()-interval '15 days', now()-interval '15 days'),
 ('d9000000-0000-0000-0000-000000000007','d0000000-0000-0000-0000-000000000021','in_app','new_offer','New offer received','You have a new offer on 500sqm Land, Ajah.','listing','d1000000-0000-0000-0000-000000000002', false, now()-interval '6 hours', now()-interval '6 hours'),
 ('d9000000-0000-0000-0000-000000000008','d0000000-0000-0000-0000-000000000023','in_app','listing_under_offer','Listing under offer','2-Bed Apartment, Yaba is now locked under offer for 72 hours.','listing','d1000000-0000-0000-0000-000000000005', false, now()-interval '1 day',  now()-interval '1 day'),
 ('d9000000-0000-0000-0000-000000000009','d0000000-0000-0000-0000-000000000031','in_app','inspection_assigned','New inspection assignment','You have been assigned to inspect Mini Flat, Surulere. Accept within 2 hours.','inspection','d4000000-0000-0000-0000-000000000002', false, now()-interval '1 hour',  now()-interval '1 hour'),
 ('d9000000-0000-0000-0000-00000000000a','d0000000-0000-0000-0000-000000000031','in_app','commission_available','Commission available','Your ₦4,100,000 commission for Terrace, Ikoyi is now available.','commission','d7000000-0000-0000-0000-000000000006', true,  now()-interval '12 days', now()-interval '12 days'),
 ('d9000000-0000-0000-0000-00000000000b','d0000000-0000-0000-0000-000000000032','in_app','report_submitted','Report submitted','Your inspection report for 3-Bed, Lugbe was submitted successfully.','inspection','d4000000-0000-0000-0000-000000000003', true,  now()-interval '2 days', now()-interval '2 days'),
 ('d9000000-0000-0000-0000-00000000000c','d0000000-0000-0000-0000-000000000001','in_app','dual_approval','Dual approval required','An escrow movement above ₦10,000,000 needs a second admin approval.','transaction','d3000000-0000-0000-0000-000000000006', false, now()-interval '15 days', now()-interval '15 days');

COMMIT;
