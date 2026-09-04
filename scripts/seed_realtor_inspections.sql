-- =============================================================================
-- Maiplot — Realtor inspection + report-review demo data (idempotent)
-- =============================================================================
-- Walks the realtor flow end to end against the exported design:
-- Assigned Inspections -> accept -> the 5-section report wizard -> Report
-- History -> admin review -> resubmit.
--
-- STACKS ON TOP OF scripts/seed_demo_data.sql — run that first. It reuses that
-- world's realtor (realtor1@demo.maiplot.ng, "Bola Ahmed") and sellers, and
-- only adds the six properties the design draws plus their inspections.
--
-- Safe to re-run: every row has a fixed UUID and is deleted then reinserted.
-- Prefixes used here (distinct from the main seed's d1/d3/d4/dd):
--   f1…  property_listings      f3…  transactions
--   e1…  inspections            fd…  listing_media
--   b…   demo buyers            (see the note on buyer refs below)
--
-- ---------------------------------------------------------------------------
-- Two deliberate demo-only choices, both worth knowing:
--
-- 1. BUYER + INSPECTION UUIDS ARE HAND-PICKED so their first 8 hex characters
--    differ. The UI shows `str(uuid)[:8]` as the reference (the same convention
--    the seller offer/deal views use), and the main seed's ids all start
--    "d0000000"/"d4000000" — so every row rendered an identical reference and
--    looked broken. Production ids are gen_random_uuid(), where those 8
--    characters are random. These echo the design's BYR-7824 / BYR-5631 / …
--    so the screen reads like the artboard.
--
-- 2. PHOTOS POINT AT picsum.photos, not the main seed's cdn.maiplot.ng
--    placeholders, which resolve to nothing. The design's table and cards are
--    mostly thumbnail, so broken images make it impossible to judge. Fixed
--    seeds per property, so each keeps the same photo between runs.
--
-- Dates are RELATIVE, not the artboard's fixed April dates, so the flow is
-- actually walkable: one inspection is reportable right now, one acceptance
-- window is about to lapse, and one is due today so the dashboard's
-- "Upcoming Today" tile is non-zero.
--
-- Run: docker exec -i maiplot-postgres psql -U maiplot -d maiplot < scripts/seed_realtor_inspections.sql
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 0. Clean up a prior run (children first). Scoped to this script's prefixes.
--    audit_log is append-only (DB triggers block DELETE) so its rows are left;
--    they are harmless history.
-- ---------------------------------------------------------------------------
DELETE FROM inspections       WHERE id::text LIKE 'e1%';
DELETE FROM transactions      WHERE id::text LIKE 'f3%';
DELETE FROM listing_media     WHERE id::text LIKE 'fd%';
DELETE FROM property_listings WHERE id::text LIKE 'f1%';
DELETE FROM user_pii          WHERE user_id::text LIKE 'b%' AND user_id IN (SELECT id FROM users WHERE email LIKE 'demo-buyer%@demo.maiplot.ng');
DELETE FROM users             WHERE email LIKE 'demo-buyer%@demo.maiplot.ng';

-- ---------------------------------------------------------------------------
-- 1. Buyers, one per inspection, with references that echo the design.
-- ---------------------------------------------------------------------------
INSERT INTO users (id, role, email, verified_status, seller_authority_type, poa_verified_status, is_active) VALUES
 ('b7824000-0000-0000-0000-000000000001','buyer','demo-buyer-7824@demo.maiplot.ng','fully_verified',NULL,'not_applicable',true),
 ('b5631000-0000-0000-0000-000000000002','buyer','demo-buyer-5631@demo.maiplot.ng','fully_verified',NULL,'not_applicable',true),
 ('b9042000-0000-0000-0000-000000000003','buyer','demo-buyer-9042@demo.maiplot.ng','fully_verified',NULL,'not_applicable',true),
 ('b1205000-0000-0000-0000-000000000004','buyer','demo-buyer-1205@demo.maiplot.ng','fully_verified',NULL,'not_applicable',true),
 ('b4456000-0000-0000-0000-000000000005','buyer','demo-buyer-4456@demo.maiplot.ng','fully_verified',NULL,'not_applicable',true),
 ('b8821000-0000-0000-0000-000000000006','buyer','demo-buyer-8821@demo.maiplot.ng','fully_verified',NULL,'not_applicable',true);

INSERT INTO user_pii (user_id, phone, full_name) VALUES
 ('b7824000-0000-0000-0000-000000000001','+2348040000001','Chinelo Obi'),
 ('b5631000-0000-0000-0000-000000000002','+2348040000002','Yusuf Danladi'),
 ('b9042000-0000-0000-0000-000000000003','+2348040000003','Amaka Eze'),
 ('b1205000-0000-0000-0000-000000000004','+2348040000004','Segun Adeyemi'),
 ('b4456000-0000-0000-0000-000000000005','+2348040000005','Halima Bello'),
 ('b8821000-0000-0000-0000-000000000006','+2348040000006','Peter Okon');

-- ---------------------------------------------------------------------------
-- 2. The six properties the design draws.
--    property_type is constrained to land|residential|commercial, so the
--    artboard's richer labels ("Villa", "Office Space") map onto those three —
--    the UI shows Land / House / Commercial and does not invent the rest.
--    Sellers are the main seed's: s1=…21 (owner) s2=…22 (PoA) s3=…23 (owner).
-- ---------------------------------------------------------------------------
INSERT INTO property_listings
 (id, seller_id, property_type, title, description, address_text, location, lga, state, size_sqm, asking_price_kobo, sale_type, urgency_tag, status, doc_verification_status, view_count, interest_count, expires_at, created_at) VALUES
 ('f1000000-0000-0000-0000-000000000001','d0000000-0000-0000-0000-000000000021','land','2 Plots of Land','Two adjoining plots, survey plan and C of O available.','Lekki Phase 1', ST_SetSRID(ST_MakePoint(3.4720,6.4430),4326)::geography,'Eti-Osa','Lagos',1000, 1500000000,'distress','7_days','under_offer','verified', 412, 14, now()+interval '7 days', now()-interval '9 days'),
 ('f1000000-0000-0000-0000-000000000002','d0000000-0000-0000-0000-000000000023','residential','Modern Duplex','4-bedroom detached duplex with BQ and fitted kitchen.','Victoria Island', ST_SetSRID(ST_MakePoint(3.4210,6.4281),4326)::geography,'Lagos Island','Lagos',320, 18500000000,'normal',NULL,'under_offer','verified', 508, 19, now()+interval '90 days', now()-interval '15 days'),
 ('f1000000-0000-0000-0000-000000000003','d0000000-0000-0000-0000-000000000022','commercial','Commercial Plot','Corner commercial plot on a tarred road, ideal for retail.','Ikeja GRA', ST_SetSRID(ST_MakePoint(3.3510,6.5810),4326)::geography,'Ikeja','Lagos',800, 9800000000,'normal',NULL,'under_offer','verified', 233, 7, now()+interval '90 days', now()-interval '11 days'),
 ('f1000000-0000-0000-0000-000000000004','d0000000-0000-0000-0000-000000000021','residential','Luxury Villa','6-bedroom waterfront villa, private jetty access.','Banana Island', ST_SetSRID(ST_MakePoint(3.4450,6.4560),4326)::geography,'Ikoyi','Lagos',900, 65000000000,'normal',NULL,'under_offer','verified', 921, 31, now()+interval '90 days', now()-interval '20 days'),
 ('f1000000-0000-0000-0000-000000000005','d0000000-0000-0000-0000-000000000023','residential','3 Bedroom Apartment','Well-finished 3-bed apartment in a serviced estate.','Ajah', ST_SetSRID(ST_MakePoint(3.5810,6.4670),4326)::geography,'Eti-Osa','Lagos',140, 5600000000,'normal',NULL,'under_offer','verified', 287, 9, now()+interval '90 days', now()-interval '26 days'),
 ('f1000000-0000-0000-0000-000000000006','d0000000-0000-0000-0000-000000000022','commercial','Office Space','Open-plan office floor, fibre-ready, secure parking.','Lekki Phase 2', ST_SetSRID(ST_MakePoint(3.5290,6.4410),4326)::geography,'Eti-Osa','Lagos',450, 7200000000,'distress','14_days','under_offer','verified', 344, 12, now()+interval '14 days', now()-interval '29 days');

-- Cover photos. picsum.photos with a fixed seed per property — real images, so
-- the table thumbnails and the wizard's property panel actually render.
INSERT INTO listing_media (id, listing_id, media_type, s3_key, cdn_url, sort_order) VALUES
 ('fd000000-0000-0000-0000-000000000101','f1000000-0000-0000-0000-000000000001','photo','media/f1/1.jpg','https://picsum.photos/seed/maiplot-plots/640/480',0),
 ('fd000000-0000-0000-0000-000000000102','f1000000-0000-0000-0000-000000000001','photo','media/f1/2.jpg','https://picsum.photos/seed/maiplot-plots-2/640/480',1),
 ('fd000000-0000-0000-0000-000000000201','f1000000-0000-0000-0000-000000000002','photo','media/f2/1.jpg','https://picsum.photos/seed/maiplot-duplex/640/480',0),
 ('fd000000-0000-0000-0000-000000000301','f1000000-0000-0000-0000-000000000003','photo','media/f3/1.jpg','https://picsum.photos/seed/maiplot-commercial/640/480',0),
 ('fd000000-0000-0000-0000-000000000401','f1000000-0000-0000-0000-000000000004','photo','media/f4/1.jpg','https://picsum.photos/seed/maiplot-villa/640/480',0),
 ('fd000000-0000-0000-0000-000000000501','f1000000-0000-0000-0000-000000000005','photo','media/f5/1.jpg','https://picsum.photos/seed/maiplot-apartment/640/480',0),
 ('fd000000-0000-0000-0000-000000000601','f1000000-0000-0000-0000-000000000006','photo','media/f6/1.jpg','https://picsum.photos/seed/maiplot-office/640/480',0);

-- ---------------------------------------------------------------------------
-- 3. Transactions — one per property, each with its own buyer.
-- ---------------------------------------------------------------------------
INSERT INTO transactions (id, listing_id, buyer_id, seller_id, realtor_id, agreed_price_kobo, platform_fee_kobo, loan_id, stage, lock_expires_at, created_at) VALUES
 ('f3000000-0000-0000-0000-000000000001','f1000000-0000-0000-0000-000000000001','b7824000-0000-0000-0000-000000000001','d0000000-0000-0000-0000-000000000021','d0000000-0000-0000-0000-000000000031', 1500000000, NULL, NULL,'inspection_scheduled', now()+interval '60 hours', now()-interval '3 days'),
 ('f3000000-0000-0000-0000-000000000002','f1000000-0000-0000-0000-000000000002','b5631000-0000-0000-0000-000000000002','d0000000-0000-0000-0000-000000000023','d0000000-0000-0000-0000-000000000031',18500000000, NULL, NULL,'inspection_scheduled', now()+interval '60 hours', now()-interval '4 days'),
 ('f3000000-0000-0000-0000-000000000003','f1000000-0000-0000-0000-000000000003','b9042000-0000-0000-0000-000000000003','d0000000-0000-0000-0000-000000000022','d0000000-0000-0000-0000-000000000031', 9800000000, NULL, NULL,'offer_accepted',       now()+interval '70 hours', now()-interval '1 day'),
 ('f3000000-0000-0000-0000-000000000004','f1000000-0000-0000-0000-000000000004','b1205000-0000-0000-0000-000000000004','d0000000-0000-0000-0000-000000000021','d0000000-0000-0000-0000-000000000031',65000000000, NULL, NULL,'offer_accepted',       now()+interval '71 hours', now()-interval '1 day'),
 ('f3000000-0000-0000-0000-000000000005','f1000000-0000-0000-0000-000000000005','b4456000-0000-0000-0000-000000000005','d0000000-0000-0000-0000-000000000023','d0000000-0000-0000-0000-000000000031', 5600000000, NULL, NULL,'inspection_completed', NULL,                      now()-interval '12 days'),
 ('f3000000-0000-0000-0000-000000000006','f1000000-0000-0000-0000-000000000006','b8821000-0000-0000-0000-000000000006','d0000000-0000-0000-0000-000000000022','d0000000-0000-0000-0000-000000000031', 7200000000, NULL, NULL,'inspection_completed', NULL,                      now()-interval '16 days');

-- ---------------------------------------------------------------------------
-- 4. The inspections — one per state the design and the review flow can be in.
--
--   E1000001  2 Plots of Land      accepted, confirmed EARLIER TODAY
--                                  -> the report wizard is open RIGHT NOW.
--                                     Start here to walk the 5 sections.
--   E1000002  Modern Duplex        accepted, confirmed in 2 days
--                                  -> Scheduled; the wizard explains it is not
--                                     open yet rather than 404ing.
--   E1000003  Commercial Plot      pending, ~90 min left on the 2-hour window
--                                  -> Accept / propose-another-time.
--   E1000004  Luxury Villa         pending, ~12 min left
--                                  -> the countdown goes red (urgent < 15 min).
--   E1000005  3 Bedroom Apartment  reported and APPROVED
--                                  -> green Admin Feedback, no Resubmit.
--   E1000006  Office Space         reported and REJECTED with a reason
--                                  -> red Admin Feedback + a working Resubmit.
--
-- report_reviewed_by is the main seed's admin (…0001).
-- ---------------------------------------------------------------------------
INSERT INTO inspections
 (id, transaction_id, realtor_id, proposed_date, confirmed_date, status, gps_lat, gps_lng,
  report_submitted_at, report_data, assignment_expires_at, created_at,
  report_review_status, report_reviewed_at, report_reviewed_by, report_review_note, report_revision) VALUES

 ('e1000001-0000-0000-0000-000000000001','f3000000-0000-0000-0000-000000000001','d0000000-0000-0000-0000-000000000031',
  now()-interval '4 hours', now()-interval '4 hours','accepted', NULL, NULL,
  NULL, NULL, now()-interval '2 days', now()-interval '3 days',
  'not_submitted', NULL, NULL, NULL, 1),

 ('e1000002-0000-0000-0000-000000000002','f3000000-0000-0000-0000-000000000002','d0000000-0000-0000-0000-000000000031',
  now()+interval '2 days', now()+interval '2 days','accepted', NULL, NULL,
  NULL, NULL, now()-interval '3 days', now()-interval '4 days',
  'not_submitted', NULL, NULL, NULL, 1),

 ('e1000003-0000-0000-0000-000000000003','f3000000-0000-0000-0000-000000000003','d0000000-0000-0000-0000-000000000031',
  now()+interval '3 days', NULL,'pending', NULL, NULL,
  NULL, NULL, now()+interval '90 minutes', now()-interval '30 minutes',
  'not_submitted', NULL, NULL, NULL, 1),

 ('e1000004-0000-0000-0000-000000000004','f3000000-0000-0000-0000-000000000004','d0000000-0000-0000-0000-000000000031',
  now()+interval '4 days', NULL,'pending', NULL, NULL,
  NULL, NULL, now()+interval '12 minutes', now()-interval '108 minutes',
  'not_submitted', NULL, NULL, NULL, 1),

 ('e1000005-0000-0000-0000-000000000005','f3000000-0000-0000-0000-000000000005','d0000000-0000-0000-0000-000000000031',
  now()-interval '10 days', now()-interval '10 days','completed', 6.4670, 3.5810,
  now()-interval '10 days',
  '{"property_condition":"good","amenities":["Water","Electricity","Road access","Security"],"discrepancies":null,"remarks":"Property matches the listing in every respect.\nEnvironment: Quiet serviced estate, tarred internal roads.\nAccessibility: Easy — 400m off the expressway.","photo_keys":["inspection-report/e1000005/a.jpg","inspection-report/e1000005/b.jpg","inspection-report/e1000005/c.jpg"],"video_key":null}'::jsonb,
  now()-interval '11 days', now()-interval '12 days',
  'approved', now()-interval '9 days','d0000000-0000-0000-0000-000000000001','Thorough report, clear photographs. Approved.', 1),

 ('e1000006-0000-0000-0000-000000000006','f3000000-0000-0000-0000-000000000006','d0000000-0000-0000-0000-000000000031',
  now()-interval '14 days', now()-interval '14 days','completed', 6.4410, 3.5290,
  now()-interval '14 days',
  '{"property_condition":"fair","amenities":["Electricity","Road access"],"discrepancies":"Certificate of Occupancy (C of O): physical document not present.","remarks":"Seller could not produce the C of O on site.\nEnvironment: Busy commercial strip.\nAccessibility: Moderate — parking is tight at peak hours.","photo_keys":["inspection-report/e1000006/a.jpg","inspection-report/e1000006/b.jpg","inspection-report/e1000006/c.jpg"],"video_key":null}'::jsonb,
  now()-interval '15 days', now()-interval '16 days',
  'rejected', now()-interval '13 days','d0000000-0000-0000-0000-000000000001','Photos are too dark to verify the boundary on the north side, and the C of O is missing. Please reshoot in daylight and confirm the document with the seller.', 1);

-- ---------------------------------------------------------------------------
-- 5. Hand the main seed's two realtor1 assignments to realtor2.
--
--    seed_demo_data.sql gives realtor1 an extra pending inspection (Mini Flat)
--    and an extra completed one (Terrace, Ikoyi). Left alone, the Assigned
--    Inspections tiles read 8/3/2/3 and the screen no longer lines up with the
--    artboard's six rows. realtor2 ("Grace Peter") is also approved and covers
--    Lagos, so the demo world stays coherent — the work just belongs to her.
--
--    Only these two fixed ids are touched, so re-running is safe and the main
--    seed can be re-run afterwards to put them back.
-- ---------------------------------------------------------------------------
UPDATE inspections
   SET realtor_id = 'd0000000-0000-0000-0000-000000000032'
 WHERE id IN ('d4000000-0000-0000-0000-000000000002',
              'd4000000-0000-0000-0000-000000000006');

UPDATE transactions
   SET realtor_id = 'd0000000-0000-0000-0000-000000000032'
 WHERE id IN ('d3000000-0000-0000-0000-000000000002',
              'd3000000-0000-0000-0000-000000000006');

COMMIT;

-- ---------------------------------------------------------------------------
-- What you should see, signed in as realtor1@demo.maiplot.ng (Password123!)
--
--   /realtor                6 assignments · "Upcoming Today" counts E1000001
--                           · activity feed shows the approval and the rejection
--   /realtor/inspections    tiles 6 / 2 pending / 2 scheduled / 2 completed
--                           · thumbnails, Distress Sale on plots + office,
--                             per-row references, View Details
--   View Details on         a live 2-hour countdown + Accept
--     Commercial Plot       (Luxury Villa's goes red — under 15 minutes)
--   View Details on         "Submit inspection report" -> the 5-section wizard
--     2 Plots of Land
--   /realtor/reports        2 reports · 1 approved (green) · 1 rejected (red,
--                           with the admin's reason and a working Resubmit)
--   /admin/inspections/reports   empty until you submit — then it is queued
-- ---------------------------------------------------------------------------
