# Password recovery — written design (SCRUM-191 frontend)

No Figma export covers password recovery. Rather than invent a visual language,
this design is **derived from the two auth screens that already exist** —
`/login` and `/verify-email` — so the three new surfaces read as part of the
same funnel. Every token, class string and layout below is already in the
codebase; nothing here is new visual vocabulary.

If a Figma export for these screens lands later, it supersedes this file.
(It lives in `docs/` rather than alongside the other design material because
`frontend/web/design/` is gitignored — those are large local PNG exports, and
this is a decision record that has to travel with the code.)

---

## The shell (all three screens)

`/login` and `/verify-email` share one shell, and these adopt it unchanged:

```
main.grid.min-h-screen.lg:grid-cols-[1.05fr_1fr]
├── section  ← emerald-deep panel, hidden below lg, .grain texture
│   ├── logo lockup (9×9 rounded-sm bone/10 tile + "Maihomme")
│   ├── eyebrow (text-xs uppercase tracking-[0.2em] text-bone/50)
│   ├── h1 (font-display text-4xl leading-tight)
│   ├── supporting paragraph (text-sm text-bone/70)
│   └── "Secure · encrypted · af-south-1"
└── section  ← form column, centred, max-w-sm, .animate-rise
```

The left panel copy is the only thing that changes per screen. Below `lg` the
panel is hidden and the form column shows a small wordmark, exactly as `/login`
does.

## Screen 1 — the "Forgot password?" link

**Where:** on `/login`, on the Password label row, right-aligned.

```
┌ Password ──────────────── Forgot password? ┐
│ ••••••••                              👁   │
└────────────────────────────────────────────┘
```

The label row becomes `flex items-center justify-between`. The link takes the
same treatment every inline auth link already uses:
`text-sm font-medium text-emerald-deep hover:underline`.

**Why the label row and not under the button:** it is where the control is
conventionally looked for, and it sits next to the field that failed — the user
reaches for it at the moment the password does not work.

**Role is carried through.** `/login` serves buyer/seller/realtor off `?role=`,
so the link forwards it (`/forgot-password?role=seller`) and the recovery screen
keeps the same left-panel copy. Losing the role mid-funnel would drop the user
into a buyer-flavoured screen for no reason.

**Admin sign-in deliberately does NOT get the link.** Admin accounts are
provisioned, not signed up, and the admin surface is IP-allowlisted (CLAUDE.md
§4); advertising an unauthenticated recovery entry point there widens the admin
attack surface for a handful of users an operator can reset directly. The
endpoint itself is not role-gated, so an admin who needs it can still reach
`/forgot-password` — it is simply not signposted.

## Screen 2 — `/forgot-password` (request)

Two states in one client component.

**`form`** — eyebrow "Account recovery", h2 "Forgot your password?", sub
"Enter the email on your account and we'll send you a link to set a new
password." Then one email field and a full-width submit.

**`sent`** — replaces the form entirely (not a toast; the form has no further
purpose). Emerald confirmation panel, the same
`rounded-md bg-emerald-deep/10 px-3.5 py-3 text-sm text-emerald-deep` block the
verify-email resend box uses:

> If that email has an account, we've sent a reset link. Check your inbox — and
> your spam or promotions folder.

⚠️ **That wording is load-bearing, not filler.** The backend answers a
byte-identical 202 for a known and an unknown address so the endpoint cannot be
used to enumerate accounts. Copy that said "We've sent you a link" would leak
through the UI exactly what the API refuses to leak. Do not "improve" it into
something more definite.

The `sent` state also offers "Use a different email" (back to `form`) so a typo
is not a dead end, since the generic copy cannot tell the user they mistyped.

**Errors:** `429` → "Too many requests. Please wait a little and try again.";
`422` → "Please enter a valid email address."; anything else → generic retry.
Same `role="alert"` red panel as `/login`.

## Screen 3 — `/reset-password` (the emailed link lands here)

Mirrors `/verify-email`: a server shell plus a client component with phases, and
a BFF that **POSTs** the token rather than GETting it, so it stays out of server
access logs.

**One deliberate difference from `/verify-email`: this page does not auto-submit
on mount.** Verify-email spends its token immediately because there is nothing
to collect. A reset token must only be spent when the user has actually typed a
new password, so the initial phase is the form. There is no "check this token"
endpoint and there should not be one — validity surfaces on submit.

Phases: `form` → `submitting` → `success`, with `expired`, `invalid`, `missing`
and `error` as the off-ramps.

```
form        ▸ two fields (new password, confirm), live requirement checklist
success     ▸ ✓ "Password reset" → "Go to sign in"
expired     ▸ ⏱ "This link has expired"  → Request a new link
invalid     ▸ ✕ "This link isn't valid"  → Request a new link
missing     ▸ ! "Missing reset link"     → Request a new link
error       ▸ ! "Something went wrong"   → Try again (form retained)
```

Icons, tones and the 14×14 rounded-full badge come straight from
`verify-email-client.tsx`'s `Icon` component.

**The requirement checklist** renders the three rules `is_strong()` actually
enforces — 8+ characters, an uppercase letter, a number — each ticking green as
it is met. It is guidance, not a gate: the button stays enabled once the fields
are non-empty and match, and the server remains the authority. Showing rules the
server does not enforce, or hiding rules it does, is how a "PASSWORD_TOO_WEAK"
error becomes unexplainable.

**Confirm-password mismatch is caught client-side** and never sent — the API has
no concept of a confirm field, so a mismatch is purely a typing check.

⚠️ **A rejected password does not burn the link** (the backend checks strength
only after the token proves out, and does not `mark_used` on that path), so the
`PASSWORD_TOO_WEAK` case keeps the form and the token alive. Do not send the
user back to `/forgot-password` for a weak password.

**No auto-sign-in on success.** `/verify-email` signs the user in because
verifying proves mailbox control for an account they were already creating.
Reset deliberately issues no tokens: whoever holds the link may be an attacker
in the mailbox, and a live session would outlive the real owner's counter-reset.
The success state offers "Go to sign in" and nothing else — no countdown
redirect, because the user must now type a password they just invented and
should not be rushed off the confirmation.

## Settings copy

`app/settings/tabs.tsx` renders `NO_PASSWORD_SET` as *'This account has no
password yet. Use "Forgot password" to set one.'* — copy that has been pointing
at a control that did not exist. It now names the real destination and links to
it.
