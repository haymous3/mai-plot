'use client';

import { useState } from 'react';

import { HouseIcon, UserCircleIcon } from './icons';
import { FieldError, FieldLabel, TextField, UploadDropzone } from './fields';
import {
  NinAlreadyVerified,
  NinVerifyField,
  ninIsSettled,
  useNinVerification,
} from './nin-verify-field';
import { OnboardingHeading, PrimaryButton, SelectCard } from './ui';

/**
 * Seller and realtor onboarding steps — the `sellers-flow-*` and
 * `realtor-flow-*` exports.
 *
 * Both artboards draw their content column wider than the rest of the flow
 * (seller ~895px, buyers-flow-2 878px, everything else 768/672). Normalised
 * onto the 672px form column, same as PR 2, so a user does not see the page
 * width change between steps.
 *
 * Measured: dropzone 180px tall at a 16px radius; authority tiles ~104px;
 * controls and CTAs all 68px.
 */

/**
 * There is ONE upload left on these screens: the seller's Power of Attorney.
 * auth-service `poa.detect_document_type()` sniffs the bytes and takes PDF or
 * JPEG only — no PNG, which is why this is its own narrow accept list rather
 * than a shared one (SCRUM-199: a shared constant was letting a seller pick a
 * PNG the server always rejected).
 *
 * ⚠️ The realtor "Professional Credentials" upload that used to sit alongside it
 * was removed by SCRUM-219 — realtor onboarding collects no document now — so
 * `CREDENTIAL_ACCEPT` and realtor-service's ID-document validation went with it.
 */
const POA_ACCEPT = 'application/pdf,image/jpeg';
/**
 * 10MB, matching auth-service `poa_max_upload_bytes`.
 *
 * ⚠️ Was 5MB until SCRUM-201. SCRUM-199 corrected the visible subtitles to
 * "max 10MB" but missed this check, so the screens promised 10 and the button
 * refused at 5 — a file between the two was rejected for a reason the user had
 * just been told was allowed.
 */
const MAX_MB = 10;
const MAX_BYTES = MAX_MB * 1024 * 1024;

/**
 * Seller Verification — NIN, selling authority, and a PoA document when the
 * seller is not the owner.
 *
 * ⚠️ COPY: the same tile is labelled "Power of Attorney" on export 1 and
 * "Authorized Agent" on exports 2 and 3. "Power of Attorney" is used here — it
 * matches `authority_type = owner | power_of_attorney` and CLAUDE.md §8.1, and
 * the upload beneath it is titled "Upload Power of Attorney" on the export
 * itself, so the other label was the outlier.
 *
 * This step is NOT skippable: a PoA seller cannot publish any listing until the
 * document is verified (§8.1), so leaving without declaring an authority would
 * strand the account in a state the listing flow does not expect.
 */
export function SellerVerificationStep({
  onDone,
  fullName,
  ninVerified = false,
}: {
  onDone: () => void | Promise<void>;
  /** Already verified on this account or its linked root — skip the field (SCRUM-228). */
  ninVerified?: boolean;
  /** From the page's GET /auth/me — POST /auth/profile requires full_name. */
  fullName?: string | null;
}) {
  const [nin, setNin] = useState('');
  const [address, setAddress] = useState('');
  const [authority, setAuthority] = useState<'owner' | 'power_of_attorney' | ''>('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needsDocument = authority === 'power_of_attorney';
  // SCRUM-221: checked when entered, not inside submit().
  const ninCheck = useNinVerification('/api/auth/seller/nin');
  // Settled up front when the account — or the one it is linked to — already
  // holds a verified NIN (SCRUM-228); otherwise a linked seller was stuck here.
  const ninSettled = ninVerified || ninIsSettled(ninCheck.status);
  const canSubmit =
    ninSettled && address.trim().length > 0 && authority !== '' && (!needsDocument || file !== null);

  async function submit() {
    if (file && file.size > MAX_BYTES) {
      setError(`That document is larger than ${MAX_MB}MB. Please upload a smaller file.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Authority first: it is what gates listing publication.
      //
      // ⚠️ This comment used to claim the ordering ALSO stopped a verified NIN
      // sitting against an undeclared authority. That was already shaky — the
      // owner-only gate it leaned on went with SCRUM-189 — and SCRUM-221 ends
      // it outright: the NIN is verified on blur, long before this runs. The
      // state it warned about is now reachable by abandoning the form, and is
      // harmless: a verified NIN sets `id_verified`, publication is gated on
      // `authority_type` separately, and a seller with neither can do nothing.
      const authResp = await fetch('/api/auth/seller/authority', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ authority_type: authority }),
      });
      if (!authResp.ok) {
        setError('We could not save your selling authority. Please retry.');
        return;
      }

      // The NIN POST that used to sit here has moved to the field's own blur
      // handler (SCRUM-221), so a bad number is caught beside the field rather
      // than after the authority, address and PoA document are all filled in.
      // Every seller's NIN is verified (SCRUM-201), PoA sellers included —
      // SCRUM-189 removed the owner-only gate that used to skip them.
      if (!ninSettled) {
        setError('Please enter a NIN we can verify before continuing.');
        return;
      }

      // Address goes to the shared profile endpoint — user_pii, every role.
      const addrResp = await fetch('/api/auth/profile', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ full_name: fullName ?? '', address: address.trim() }),
      });
      if (!addrResp.ok) {
        setError('We could not save your address. Please retry.');
        return;
      }

      if (needsDocument && file) {
        const form = new FormData();
        form.append('file', file);
        const poaResp = await fetch('/api/auth/seller/poa', { method: 'POST', body: form });
        if (!poaResp.ok) {
          setError('We could not upload that document. Please retry.');
          return;
        }
      }

      await onDone();
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full">
      <OnboardingHeading
        title="Seller Verification"
        subtitle="Required for property listing authorization"
      />

      <div className="mx-auto mt-14 max-w-[672px]">
        {ninVerified ? (
          <NinAlreadyVerified />
        ) : (
          <NinVerifyField
            value={nin}
            onChange={(v) => {
              setNin(v);
              if (ninCheck.status !== 'idle') ninCheck.reset();
            }}
            status={ninCheck.status}
            message={ninCheck.message}
            onBlurVerify={() => void ninCheck.verify(nin)}
            onRetry={() => void ninCheck.verify(nin)}
            disabled={busy}
          />
        )}

        <div className="mt-9">
          <FieldLabel htmlFor="address" required>
            Address
          </FieldLabel>
          <TextField
            id="address"
            value={address}
            onChange={setAddress}
            placeholder="e.g., 12 Admiralty Way, Lekki Phase 1, Lagos"
            disabled={busy}
          />
        </div>

        <div className="mt-9">
          <FieldLabel htmlFor="authority-owner" required>
            Selling Authority
          </FieldLabel>
          <div className="mt-3 grid gap-6 sm:grid-cols-2">
            <SelectCard
              compact
              Icon={HouseIcon}
              label="Property Owner"
              description="I own the property"
              selected={authority === 'owner'}
              onSelect={() => setAuthority('owner')}
            />
            <SelectCard
              compact
              Icon={UserCircleIcon}
              label="Power of Attorney"
              description="Authorized to sell"
              selected={authority === 'power_of_attorney'}
              onSelect={() => setAuthority('power_of_attorney')}
            />
          </div>
        </div>

        {needsDocument && (
          <div className="mt-9">
            <FieldLabel htmlFor="poa-file" required>
              Upload Power of Attorney
            </FieldLabel>
            <UploadDropzone
              id="poa-file"
              file={file}
              onFile={setFile}
              title="Upload document"
              subtitle="PDF or JPG (max 10MB)"
              accept={POA_ACCEPT}
              disabled={busy}
            />
          </div>
        )}

        {error && <FieldError>{error}</FieldError>}

        <div className="mt-12">
          <PrimaryButton disabled={!canSubmit || busy} onClick={() => void submit()}>
            {busy ? 'Submitting…' : 'Complete Verification'}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
}

/**
 * Realtor Profile — identity and coverage area.
 *
 * ⚠️ NO ESVARBON FIELD (SCRUM-207). It used to be here — added back against the
 * export because `POST /realtors` required it — and the product has now removed
 * the licence number entirely: an admin verifies the application and the
 * platform issues a Maihomme registration number, emailed to the realtor, which
 * they sign in with. The screen finally matches the export it was drawn from.
 *
 * ⚠️ NO PROFESSIONAL CREDENTIALS UPLOAD (SCRUM-219). The document this step used
 * to require is no longer collected anywhere: `POST /realtors` takes no file, and
 * the admin queue's "View ID" modal was removed in the same change. The step is
 * now NIN + address + coverage.
 *
 * Coverage is a comma-separated free-text field, matching the export's
 * "e.g., Lagos, Lekki, Victoria Island", and is split into the repeated
 * `coverage_states` parts the service expects.
 */
export function RealtorProfileStep({
  onDone,
  fullName,
  ninVerified = false,
}: {
  onDone: () => void | Promise<void>;
  /** Already verified on this account or its linked root — skip the field (SCRUM-228). */
  ninVerified?: boolean;
  /** From the page's GET /auth/me — POST /auth/profile requires full_name. */
  fullName?: string | null;
}) {
  // ⚠️ NIN was collected nowhere in the realtor flow before SCRUM-201: this
  // step asked for an ESVARBON licence, coverage and credentials, and the
  // platform-wide identity check was simply absent for the role. Since
  // SCRUM-219 dropped the credentials document, the NIN is the only identity
  // evidence this step gathers.
  const [nin, setNin] = useState('');
  const [address, setAddress] = useState('');
  const [coverage, setCoverage] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ninCheck = useNinVerification('/api/auth/nin');
  const ninSettled = ninVerified || ninIsSettled(ninCheck.status);
  const canSubmit = ninSettled && address.trim().length > 0 && coverage.trim() !== '';

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      // Identity first, then the profile: a realtor row that exists without a
      // verified NIN is the state SCRUM-201 set out to remove.
      // Verified on blur since SCRUM-221; this is the guard behind `canSubmit`.
      if (!ninSettled) {
        setError('Please enter a NIN we can verify before continuing.');
        return;
      }

      const addrResp = await fetch('/api/auth/profile', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ full_name: fullName ?? '', address: address.trim() }),
      });
      if (!addrResp.ok) {
        setError('We could not save your address. Please retry.');
        return;
      }

      // Still multipart: `coverage_states` is a REPEATED field, which is what
      // FastAPI's `list[str] = Form()` reads. It carried the credentials file
      // until SCRUM-219; the shape is unchanged without it.
      const form = new FormData();
      coverage
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .forEach((state) => form.append('coverage_states', state));

      const resp = await fetch('/api/realtor/onboarding', { method: 'POST', body: form });
      if (!resp.ok) {
        const b = (await resp.json().catch(() => ({}))) as { error_code?: string };
        setError(
          b.error_code === 'COVERAGE_REQUIRED'
            ? 'Name at least one area you cover.'
            : 'Could not submit your profile. Please retry.',
        );
        return;
      }
      await onDone();
    } catch {
      setError('Could not reach the server. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full">
      <OnboardingHeading title="Realtor Profile" subtitle="Complete your professional profile" />

      <div className="mx-auto mt-14 max-w-[672px]">
        {/* NIN and Address are not on the export either (SCRUM-201): the
            realtor flow collected no identity document at all, and no role
            collected an address. */}
        {ninVerified ? (
          <NinAlreadyVerified />
        ) : (
          <NinVerifyField
            id="realtor-nin"
            value={nin}
            onChange={(v) => {
              setNin(v);
              if (ninCheck.status !== 'idle') ninCheck.reset();
            }}
            status={ninCheck.status}
            message={ninCheck.message}
            onBlurVerify={() => void ninCheck.verify(nin)}
            onRetry={() => void ninCheck.verify(nin)}
            disabled={busy}
          />
        )}

        <div className="mt-9">
          <FieldLabel htmlFor="realtor-address" required>
            Address
          </FieldLabel>
          <TextField
            id="realtor-address"
            value={address}
            onChange={setAddress}
            placeholder="e.g., 12 Admiralty Way, Lekki Phase 1, Lagos"
            disabled={busy}
          />
        </div>

        <div className="mt-9">
          <FieldLabel htmlFor="coverage" required>
            Coverage Area
          </FieldLabel>
          <TextField
            id="coverage"
            value={coverage}
            onChange={setCoverage}
            placeholder="e.g., Lagos, Lekki, Victoria Island"
            disabled={busy}
          />
          <p className="mt-3 text-[15px] leading-5 text-ink-500">
            Areas where you provide services
          </p>
        </div>

        {error && <FieldError>{error}</FieldError>}

        <div className="mt-12">
          <PrimaryButton disabled={!canSubmit || busy} onClick={() => void submit()}>
            {busy ? 'Submitting…' : 'Complete Profile'}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
}
