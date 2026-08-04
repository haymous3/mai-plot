# Design Export Index

Maps every PNG in `frontend/web/design/` to the screen it depicts and the app route that implements it.

**The exports are not in the repository.** `frontend/web/design/` is gitignored (`.gitignore:68`) — 39MB of PNGs would live in git history permanently. This index and [`design-spec.md`](./design-spec.md) exist so the design is reviewable without them.

Produced for SCRUM-163. Tooling: [`scripts/design/`](../scripts/design/).

---

## Why this file exists

The filenames carry no information. `Maiplot Web design (7).png` could be anything, and the names actively mislead:

- Every file named **"Mobile App Onboarding Flow"** is a desktop-width screen (1562–1577px). None are mobile, none are onboarding.
- Every file named **"Agent Referral Information Page"** is the Notifications screen — except one, which really is the agent-referral step.
- **"App.png"** and **"App (1).png"** are Notifications tab states.
- **"Preview Design.png"** is the buyer wallet.

---

## Export scale — read before measuring

The 69 files are **not** a uniform export of one viewport. Grouped by width:

| Width | Files | What it covers |
|---|---|---|
| **1562px** | 41 | Primary artboard — dashboards, listings, offers, transactions, documents, loans |
| 1577px | 11 | Settings and notification screens |
| 1180–1195px | 9 | Seller create-listing wizard only |
| 1663–1679px | 3 | Buyer listing detail |
| 2343px | 1 | Buyer wallet (`Preview Design.png`) |
| 1244–1280px | 2 | Seller referral form, realtor gradient swatch |
| 1567px | 1 | Buyer deal progress |
| 545px | 1 | Employment-status dropdown crop |

**Measure from the 1562px group and treat it as the reference.** Values taken from the 1180px seller wizard captures are at a different scale and must not be mixed into the same spacing scale without normalising. `design-spec.md` records which group each measurement came from.

Whether 1562px is exactly 1x is still open — see the scale question in `design-spec.md`.

---

## Buyer — `frontend/web/design/buyer-dashboard/` (26 files)

| File | Screen | Route | State captured |
|---|---|---|---|
| `Maiplot Web design.png` | Buyer dashboard | `app/(buyer)/dashboard` | Baseline |
| `Maiplot Web design (1).png` | Buyer dashboard | `app/(buyer)/dashboard` | **Notifications panel open** |
| `Maiplot Web design (3).png` | Buyer dashboard | `app/(buyer)/dashboard` | Duplicate of (1) — identical bytes |
| `Maiplot Web design (2).png` | Buyer dashboard | `app/(buyer)/dashboard` | **Filter panel expanded** (Location, Property Type, Min/Max Price) |
| `Maiplot Web design (4).png` | Buyer dashboard | `app/(buyer)/dashboard` | **User menu open** (Settings, My Documents, Sign Out) |
| `Maiplot Web design (5).png` | Buyer dashboard | `app/(buyer)/dashboard` | Baseline — brand reads "Maiplot" |
| `Maiplot Web design (6).png` | Buyer dashboard | `app/(buyer)/dashboard` | Baseline — brand reads "Maiplot" |
| `Maiplot Web design (8).png` | Listing detail | `app/(buyer)/listings/[id]` | Baseline — hero carousel, trust score |
| `Maiplot Web design (9).png` | Listing detail | `app/(buyer)/listings/[id]` | **Modal backdrop** — page dimmed |
| `Maiplot Web design (10).png` | Listing detail | `app/(buyer)/listings/[id]` | Scrolled variant |
| `Maiplot Web design (7).png` | Deal progress | `app/(buyer)/deals/[id]` | Milestones, 2 of 6 complete |
| `Mobile App Onboarding Flow.png` | Property financing calculator | `app/(buyer)/financing/[transactionId]` | Repayment period **12 months selected** |
| `Mobile App Onboarding Flow (1).png` | Loan application — step 1 | `app/(buyer)/loans/apply/[transactionId]` | Empty |
| `Mobile App Onboarding Flow (2).png` | Loan application — step 1 | `app/(buyer)/loans/apply/[transactionId]` | **Validation errors** — red borders + messages |
| `Mobile App Onboarding Flow (3).png` | Loan application — step 2 | `app/(buyer)/loans/apply/[transactionId]` | Upload documents, empty |
| `Mobile App Onboarding Flow (4).png` | Loan application — step 2 | `app/(buyer)/loans/apply/[transactionId]` | **Validation errors** — red dashed dropzones |
| `Mobile App Onboarding Flow (5).png` | Loan application — step 3 | `app/(buyer)/loans/apply/[transactionId]` | Review before submit |
| `Mobile App Onboarding Flow (6).png` | Loan status — under review | `app/(buyer)/loans/[loanId]` | Review progress: completed / in progress / pending |
| `Mobile App Onboarding Flow (7).png` | Loan status — approved | `app/(buyer)/loans/[loanId]` | Loan details + next steps |
| `Employment status dropdown.png` | Employment select, open | `app/(buyer)/loans/apply/[transactionId]` | **Dropdown open** — the only isolated open-menu crop |
| `Preview Design.png` | My wallet | `app/(buyer)/wallet` | ⚠️ See scope conflict below |
| `Mobile App Onboarding Flow (12).png` | My documents | **no route yet** | 5 docs, verified / pending / rejected counts |
| `Mobile App Onboarding Flow (8).png` | Settings — Profile | **no route yet** | |
| `Mobile App Onboarding Flow (9).png` | Settings — Financial | **no route yet** | BVN + bank account |
| `Mobile App Onboarding Flow (10).png` | Settings — Notifications | **no route yet** | **Toggles on and off** |
| `Mobile App Onboarding Flow (11).png` | Settings — Security | **no route yet** | Change password + danger zone |

---

## Seller — `frontend/web/design/seller-dashboard/` (28 files)

| File | Screen | Route | State captured |
|---|---|---|---|
| `Maiplot Web design.png` | Seller dashboard overview | `app/seller` | 4 stat cards, recent activity, insights rail |
| `Maiplot Web design (10).png` | My listings | `app/seller/listings` | Cards with Edit / View / Pause / Delete |
| `Maiplot Web design (11).png` | Offers | `app/seller/offers` | Tab **All Offers** active |
| `Maiplot Web design (12).png` | Offers | `app/seller/offers` | Tab **Pending** active |
| `Maiplot Web design (13).png` | Offers | `app/seller/offers` | **Row expanded** — Accept / Reject / Counter actions |
| `Maiplot Web design (14).png` | Offers | `app/seller/offers` | **Counter offer sent** state |
| `Maiplot Web design (15).png` | Offers | `app/seller/offers` | All offers, scrolled |
| `Maiplot Web design (16).png` | Transactions | `app/seller/transactions` | Progress timeline + escrow rail |
| `Maiplot Web design (17).png` | Transaction detail | `app/seller/transactions/[id]` | Progress checklist |
| `Maiplot Web design (18).png` | Documents | `app/seller/documents` | Tabs + verified / pending / rejected |
| `Maiplot Web design (1).png` | Create listing — 1 Property details | `app/seller/listings/new` | 1180px artboard |
| `Maiplot Web design (2).png` | Create listing — 2 Location | `app/seller/listings/new` | Map pin placeholder |
| `Maiplot Web design (3).png` | Create listing — 3 Pricing | `app/seller/listings/new` | **Normal Sale selected** vs Distress Sale |
| `Maiplot Web design (4).png` | Create listing — 4 Media upload | `app/seller/listings/new` | |
| `Maiplot Web design (5).png` | Create listing — 5 Documents | `app/seller/listings/new` | |
| `Maiplot Web design (6).png` | Create listing — 6 Authority | `app/seller/listings/new` | **Direct Owner selected** vs Power of Attorney |
| `Maiplot Web design (7).png` | Create listing — 7 Review & submit | `app/seller/listings/new` | |
| `Agent Referral Information Page.png` | Create listing — agent referral | `app/seller/listings/new` | ⚠️ 8-step variant — see below |
| `Maiplot Web design (8).png` | Dashboard role chooser | **no route yet** | "Welcome back, ken!" — buyer / seller / realtor cards |
| `Maiplot Web design (9).png` | Sign in to seller dashboard | `app/login` | Includes demo-credentials panel |
| `Agent Referral Information Page (1).png` | Notifications | **no route yet** | Tab **All** active |
| `App.png` | Notifications | **no route yet** | Tab **Bids** active |
| `Agent Referral Information Page (2).png` | Notifications | **no route yet** | Tab **Deposits** active |
| `Agent Referral Information Page (3).png` | Notifications | **no route yet** | Tab **Documents** active |
| `App (1).png` | Notifications | **no route yet** | Tab **Messages** active |
| `Agent Referral Information Page (4).png` | Notifications | **no route yet** | Tab **System** active |
| `Mobile App Onboarding Flow.png` | Settings — Profile | **no route yet** | |
| `Mobile App Onboarding Flow (1).png` | Settings — Notifications | **no route yet** | **Toggles on and off** |
| `Mobile App Onboarding Flow (2).png` | Settings — Security | **no route yet** | Change password + danger zone |

---

## Realtor — `frontend/web/design/realtor-dashboard/` (14 files)

| File | Screen | Route | State captured |
|---|---|---|---|
| `Maiplot Web Design.png` | Realtor dashboard overview | `app/realtor` | Sidebar, 4 stats, upcoming inspections |
| `Maiplot Web Design (11).png` | Earnings | `app/realtor/earnings` | Totals + transaction history table |
| `Report submitted.png` | Report history | `app/realtor/reports` | Counts + admin feedback cards |
| `Maiplot Web Design (1).png` | Inspection report — 1 Property verification | `app/realtor/inspections/[id]/report` | Unanswered |
| `Maiplot Web Design (2).png` | Inspection report — 1 Property verification | `app/realtor/inspections/[id]/report` | **Yes selected** — green option state |
| `Maiplot Web Design (3).png` | Inspection report — 2 Condition assessment | `app/realtor/inspections/[id]/report` | **Fair selected** — amber option state |
| `Maiplot Web Design (4).png` | Inspection report — 3 Document cross-check | `app/realtor/inspections/[id]/report` | Unanswered |
| `Maiplot Web Design (5).png` | Inspection report — 3 Document cross-check | `app/realtor/inspections/[id]/report` | **Verified + Not Present selected** — green and red |
| `Maiplot Web Design (6).png` | Inspection report — 3 Document cross-check | `app/realtor/inspections/[id]/report` | Duplicate of (5) — identical bytes |
| `Maiplot Web Design (7).png` | Inspection report — 4 Media upload | `app/realtor/inspections/[id]/report` | Photo + video dropzones |
| `Maiplot Web Design (8).png` | Inspection report — 5 Final remarks | `app/realtor/inspections/[id]/report` | Report summary panel |
| `Maiplot Web Design (9).png` | Report submitted confirmation | `app/realtor/inspections/[id]/report` | Success state |
| `Maiplot Web Design (10).png` | Report submitted confirmation | `app/realtor/inspections/[id]/report` | Duplicate of (9) — identical bytes |
| `Maiplot Web Design (12).png` | — not a screen | — | Cream gradient swatch, 57 colours, `#f6f4ee`–`#f8f7f5` |

---

## Findings that need a decision

These came out of indexing and are not mine to resolve. Listed here so they are not silently absorbed into implementation work.

### 1. The brand name is inconsistent in the design itself

The buyer header reads **"MaiHome"** in `Maiplot Web design.png`, `(1)`, `(2)`, `(3)` and `(4)`, and **"Maiplot"** in `(5)` and `(6)`. Same screen, same position, two names. Someone needs to say which is correct before the buyer header is touched.

### 2. Buyer uses top nav; seller and realtor use a left sidebar

Not a defect — but it means there is no single app shell. The buyer dashboard has a 72px top bar with centred greeting. Seller and realtor have a persistent left sidebar (logo, nav items, Settings, Logout pinned to the bottom). Any "shared shell" component has to account for both.

### 3. The wallet design contains funded-wallet UI that was deliberately not built

`Preview Design.png` shows **Add Funds** and **Make Payment** controls over an available balance. Per the buyer dashboard epic the wallet shipped read-only (Option A), with the funded-balance path deferred pending CBN sign-off under CLAUDE.md §11.

**Matching this screen exactly would build a deferred money path.** SCRUM-167 must implement the read-only wallet's presentation only and leave the funding controls out. Flagging rather than deciding.

### 4. The create-listing wizard has two different step counts

Most captures show **7 steps** (Property Details → Location → Pricing → Media Upload → Documents → Authority → Review). `Agent Referral Information Page.png` shows **8**, with Agent Referral inserted before Review. Either it is conditional on a referral being present, or the design changed mid-flow. Needs confirming before the wizard's step indicator is touched.

### 5. Four screen families exist in the design with no route

Notifications (6 tab states), Settings (Profile / Financial / Notifications / Security), buyer My Documents, and the dashboard role chooser. None have a route under `app/`.

These are **new feature work, not fidelity work.** They should not be absorbed into the SCRUM-162 epic. They need their own tickets if they are wanted.

---

## Interaction-state coverage — better than expected

The initial read was that PNGs could not supply interaction states and SCRUM-165 was hard-blocked on Figma. Indexing shows that is wrong. Already captured:

| State | Evidence |
|---|---|
| Selected / active option | Realtor report options (green, amber, red); seller sale-type and authority toggles; financing repayment period |
| Active tab | Notifications ×6, seller offers ×2, seller documents |
| Form validation errors | Loan application steps 1 and 2 — red borders, red dashed dropzones, message styling |
| Open dropdown | Buyer notifications panel, user menu, employment-status select |
| Toggle on / off | Settings notification preferences (buyer and seller) |
| Modal backdrop | Listing detail dimmed |
| Row expanded | Seller offers with action buttons |
| Empty dropzone | Media upload, document upload |

Still missing, and still needing Figma: **hover**, **focus-visible**, **disabled**, and any **transition or motion**. Focus-visible matters most — it is a WCAG AA requirement, not polish.

SCRUM-165 is therefore only partly blocked. Most of it can proceed.
