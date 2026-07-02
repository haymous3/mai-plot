import type { Metadata } from 'next';

import { RegisterFlow } from './register-flow';

export const metadata: Metadata = {
  title: 'Get started · Maiplot',
};

export default function RegisterPage() {
  return <RegisterFlow />;
}
