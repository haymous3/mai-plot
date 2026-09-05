'use client';

import { useState } from 'react';

import { HouseIcon, UserCircleIcon } from './icons';
import { FieldError, FieldLabel, SecureNote, TextField, UploadDropzone } from './fields';
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
 * The two uploads on these screens have DIFFERENT server rules, so they get
 * different accept lists (SCRUM-199). One shared constant was letting a seller
 * pick a PNG that auth-service always rejected.
 *
 *   PoA         auth-service `poa.detect_document_type()` — PDF or JPEG only
 *   credentials realtor-service `credentials.py`          — PDF, JPEG or PNG
 *
 * Both cap at 10MB (`poa_max_upload_bytes`, `gov_id_max_upload_bytes`).
 */
const POA_ACCEPT = 'application/pdf,image/jpeg';
const CREDENTIAL_ACCEPT = 'application/pdf,image/png,image/jpeg';
/**
 * 10MB, matching BOTH servers: auth-service `poa_max_upload_bytes` and
 * realtor-service `gov_id_max_upload_bytes`.
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
}: {
  onDone: () => void | Promise<void>;
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
  const ninOk = /^\d{11}$/.test(nin.trim());
  const canSubmit =
    ninOk && address.trim().length > 0 && authority !== '' && (!needsDocument || file !== null);

  async function submit() {
    if (file && file.size > MAX_BYTES) {
      setError(`That document is larger than ${MAX_MB}MB. Please upload a smaller file.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Authority first: it is what gates listing publication, and the NIN
      // check is only meaningful for an owner. Ordering them the other way
      // would let a 202-accepted NIN sit against an undeclared authority.
      const authResp = await fetch('/api/auth/seller/authority', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ authority_type: authority }),
      });
      if (!authResp.ok) {
        setError('We could not save your selling authority. Please retry.');
        return;
      }

      // ⚠️ This used to run only for `authority === 'owner'` — a leftover from
      // when /auth/verify/nin was hard-gated to owner-sellers and 403'd anyone
      // else. SCRUM-189 removed that gate, but this condition stayed, so a PoA
      // seller typed a NIN the form REQUIRED and it was silently discarded.
      // Every seller's NIN is verified now (SCRUM-201).
      {
        const ninResp = await fetch('/api/auth/seller/nin', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ nin: nin.trim() }),
        });
        if (!ninResp.ok) {
          const b = (await ninResp.json().catch(() => ({}))) as { error_code?: string };
          setError(
            b.error_code === 'NIN_FORMAT_INVALID'
              ? 'NIN must be exactly 11 digits.'
              : b.error_code === 'NIN_ALREADY_VERIFIED'
                ? 'This NIN has already been verified.'
                : 'We could not verify that NIN. Please retry.',
          );
          return;
        }
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
        <FieldLabel htmlFor="nin" required>
          NIN
        </FieldLabel>
        <TextField
          id="nin"
          value={nin}
          onChange={(v) => setNin(v.replace(/[^\d]/g, ''))}
          placeholder="NIN should not be more than 11 digits"
          inputMode="numeric"
          maxLength={11}
          disabled={busy}
        />
        <SecureNote>Your data is encrypted and used only for verification</SecureNote>

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
 * Realtor Profile — credentials document and coverage area.
 *
 * ⚠️ NO ESVARBON FIELD (SCRUM-207). It used to be here — added back against the
 * export because `POST /realtors` required it — and the product has now removed
 * the licence number entirely: an admin verifies the application and the
 * platform issues a Maihomme registration number, emailed to the realtor, which
 * they sign in with. The screen finally matches the export it was drawn from.
 *
 * Coverage is a comma-separated free-text field, matching the export's
 * "e.g., Lagos, Lekki, Victoria Island", and is split into the repeated
 * `coverage_states` parts the service expects.
 */
export function RealtorProfileStep({
  onDone,
  fullName,
}: {
  onDone: () => void | Promise<void>;
  /** From the page's GET /auth/me — POST /auth/profile requires full_name. */
  fullName?: string | null;
}) {
  // ⚠️ NIN was collected nowhere in the realtor flow before SCRUM-201: this
  // step asked for an ESVARBON licence, coverage and credentials, and the
  // platform-wide identity check was simply absent for the role.
  const [nin, setNin] = useState('');
  const [address, setAddress] = useState('');
  const [coverage, setCoverage] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ninOk = /^\d{11}$/.test(nin.trim());
  const canSubmit =
    ninOk && address.trim().length > 0 && coverage.trim() !== '' && file !== null;

  async function submit() {
    if (file && file.size > MAX_BYTES) {
      setError(`That document is larger than ${MAX_MB}MB. Please upload a smaller file.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Identity first, then the professional credentials: a realtor row that
      // exists without a verified NIN is the state SCRUM-201 set out to remove.
      const ninResp = await fetch('/api/auth/nin', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ nin: nin.trim() }),
      });
      if (!ninResp.ok) {
        const b = (await ninResp.json().catch(() => ({}))) as { error_code?: string };
        setError(
          b.error_code === 'NIN_FORMAT_INVALID'
            ? 'NIN must be exactly 11 digits.'
            : b.error_code === 'NIN_ALREADY_VERIFIED'
              ? 'This NIN has already been verified.'
              : 'We could not verify that NIN. Please retry.',
        );
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

      const form = new FormData();
      coverage
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
        .forEach((state) => form.append('coverage_states', state));
      if (file) form.append('file', file);

      const resp = await fetch('/api/realtor/onboarding', { method: 'POST', body: form });
      if (!resp.ok) {
        const b = (await resp.json().catch(() => ({}))) as { error_code?: string };
        setError(
          (b.error_code ?? '').startsWith('CREDENTIAL')
            ? `That document was not accepted. Use a PDF, PNG or JPG under ${MAX_MB}MB.`
            : 'Could not submit your credentials. Please retry.',
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
        <FieldLabel htmlFor="realtor-nin" required>
          NIN
        </FieldLabel>
        <TextField
          id="realtor-nin"
          value={nin}
          onChange={(v) => setNin(v.replace(/[^\d]/g, ''))}
          placeholder="NIN should not be more than 11 digits"
          inputMode="numeric"
          maxLength={11}
          disabled={busy}
        />
        <SecureNote>Your data is encrypted and used only for verification</SecureNote>

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
          <FieldLabel htmlFor="credentials" required>
            Professional Credentials
          </FieldLabel>
          <UploadDropzone
            id="credentials"
            file={file}
            onFile={setFile}
            title="Upload credentials"
            subtitle="PDF, PNG, or JPG (max 10MB)"
            accept={CREDENTIAL_ACCEPT}
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
