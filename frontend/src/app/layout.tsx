import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';
import '@fontsource/jetbrains-mono/700.css';
import '@fontsource/space-grotesk/400.css';
import '@fontsource/space-grotesk/500.css';
import '@fontsource/space-grotesk/700.css';
import './globals.css';

import type { Metadata, Viewport } from 'next';
import { headers } from 'next/headers';

import { Header } from '@/components/Header';
import { authEnabled } from '@/lib/auth';
import { apiTry } from '@/lib/server-api';
import type { SourceHealth } from '@/lib/types';

export const metadata: Metadata = {
  title: 'Slab Terminal · Sports Card Portfolio',
  description: 'Personal sports card portfolio: holdings, comps, deterministic valuation and ingestion review.',
};

export const viewport: Viewport = { themeColor: '#0B0F14' };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const path = (await headers()).get('x-pathname') ?? '';
  const bare = path.startsWith('/login');
  const health = bare ? null : await apiTry<SourceHealth>('/internal/ingestion/source-health');
  const reviewCount = health ? Object.values(health.open_issues).reduce((a, b) => a + b, 0) : 0;

  return (
    <html lang="en">
      <body>
        {!bare && <Header reviewCount={reviewCount} showLogout={authEnabled()} />}
        {children}
      </body>
    </html>
  );
}
