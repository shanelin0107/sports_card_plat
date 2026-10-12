'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useState } from 'react';

import { Logo } from './Logo';

const NAV = [
  { href: '/', label: 'Dashboard' },
  { href: '/collection', label: 'Collection' },
  { href: '/search', label: 'Search eBay' },
  { href: '/review', label: 'Ingestion' },
];

export function Header({ reviewCount = 0, showLogout = false }: { reviewCount?: number; showLogout?: boolean }) {
  const pathname = usePathname();
  const router = useRouter();
  const [q, setQ] = useState('');

  return (
    <header className="border-b border-line bg-chrome">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-7 gap-y-3 px-4 py-3 sm:px-7">
        <Link href="/" className="hover:text-ink">
          <Logo />
        </Link>
        <nav aria-label="Main" className="flex flex-wrap gap-1">
          {NAV.map((n) => {
            const active = n.href === '/' ? pathname === '/' : pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active ? 'page' : undefined}
                className={`flex min-h-11 items-center gap-2 rounded-md px-3 ${active ? 'bg-[#17212C] text-ink' : ''}`}
              >
                {n.label}
                {n.href === '/review' && reviewCount > 0 && (
                  <span className="badge bg-warn/15 font-mono text-warn" aria-label={`${reviewCount} to review`}>
                    {reviewCount}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
        <form
          role="search"
          className="flex min-w-[240px] flex-1 gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            router.push(`/search?q=${encodeURIComponent(q)}`);
          }}
        >
          <label htmlFor="global-search" className="sr-only">
            Search eBay for a card
          </label>
          <input
            id="global-search"
            className="field"
            placeholder="Search eBay: 2024 prizm black lillard orange wave"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <button className="btn-primary">Search</button>
        </form>
        {showLogout && (
          <form action="/api/logout" method="post">
            <button className="btn-ghost px-3 text-[13px]">Sign out</button>
          </form>
        )}
      </div>
    </header>
  );
}
