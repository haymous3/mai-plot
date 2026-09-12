import type { Metadata } from 'next';
import { Archivo, Fraunces } from 'next/font/google';
import './globals.css';

// Distinctive pairing: a high-contrast serif for the wordmark + a clean grotesk
// for everything else. Avoids generic system/UI fonts.
const fraunces = Fraunces({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-display',
  display: 'swap',
});

const archivo = Archivo({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-sans',
  display: 'swap',
});

export const metadata: Metadata = {
  // The favicon, touch icon and link-preview image are the file-convention
  // routes next to this layout (`icon.png`, `apple-icon.png`,
  // `opengraph-image.png` — SCRUM-230); Next wires them up by filename.
  // `metadataBase` is what makes the preview URL absolute: without it Next
  // guesses from VERCEL_URL, which is the deployment's own hostname rather
  // than the domain a shared link actually carries.
  metadataBase: new URL('https://www.maihomme.com'),
  title: 'Maihomme',
  description: "Nigeria's distressed real estate marketplace",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${fraunces.variable} ${archivo.variable}`}>
      <body className="min-h-screen bg-white font-sans text-ink-900 antialiased">{children}</body>
    </html>
  );
}
