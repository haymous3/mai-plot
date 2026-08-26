'use client';

import { BuildingIcon, HouseIcon, UserCircleIcon } from './icons';
import { OnboardingHeading, PrimaryButton, SelectCard } from './ui';

/**
 * Role picker — `design/onboarding/selected-options.png` (unselected) and the
 * three `*-selected-state.png` exports.
 *
 * ⚠️ THE EXPORTS CONTAIN TWO DIFFERENT DESIGNS, two files each:
 *   "Welcome to Maiplot" / "Tell us what brings you here today" with long
 *      benefit-led descriptions        — onboarding + buyer exports
 *   "Who are you?" / "Select your role to personalize your experience" with
 *      short factual descriptions      — seller + realtor exports
 * Product owner chose the first, which is also the copy already shipped, so
 * this is zero copy churn. The other variant is not built.
 *
 * Measured: cards 768×144 at a 24px gap, 16px radius, 1px SOLID #e5e7eb;
 * 80×80 `surface-warm` chip inverting to `emerald-deep` when selected; CTA
 * 768×68, disabled until a role is chosen.
 *
 * NOTE ON THE BRAND STRING: the export says "Maiplot", and every other auth
 * screen (login, verify-email, register) says Maiplot too, so this is
 * internally consistent. But SCRUM-182 has just rebranded the verification
 * EMAIL and SMS to "Maihomme" from maihomme.com — so a user now signs up under
 * one name and is emailed under another. That is a live inconsistency this
 * ticket did not introduce and is not fixing; flagged for a rebrand ticket.
 */

export const ROLES = [
  {
    value: 'buyer',
    Icon: UserCircleIcon,
    label: 'Buyer / Investor',
    description: 'Find verified properties and get financing to close deals fast',
  },
  {
    value: 'seller',
    Icon: HouseIcon,
    label: 'Property Seller',
    description: 'List your property and connect with serious, pre-qualified buyers',
  },
  {
    value: 'realtor',
    Icon: BuildingIcon,
    label: 'Realtor / Agent',
    description: 'Grow your business with verified listings and commission tracking',
  },
] as const;

export function RolePicker({
  role,
  setRole,
  onContinue,
}: {
  role: string;
  setRole: (r: string) => void;
  onContinue: () => void;
}) {
  return (
    <div className="w-full">
      <OnboardingHeading title="Welcome to Maiplot" subtitle="Tell us what brings you here today" />

      <div className="mt-14 flex flex-col gap-6">
        {ROLES.map((r) => (
          <SelectCard
            key={r.value}
            Icon={r.Icon}
            label={r.label}
            description={r.description}
            selected={r.value === role}
            onSelect={() => setRole(r.value)}
          />
        ))}
      </div>

      <div className="mt-12">
        <PrimaryButton disabled={!role} onClick={onContinue}>
          Continue
        </PrimaryButton>
      </div>
    </div>
  );
}
