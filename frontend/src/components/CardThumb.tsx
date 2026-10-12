'use client';

import { useState } from 'react';

const SIZES = {
  sm: 'h-14 w-10',
  md: 'h-[84px] w-[60px]',
  lg: 'h-[196px] w-[140px]',
} as const;

function initials(name: string | null | undefined) {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

/** Card-shaped (5:7) thumbnail; falls back to a drawn slab with the player's initials. */
export function CardThumb({ src, player, size = 'sm', alt }: { src: string | null; player: string | null; size?: keyof typeof SIZES; alt?: string }) {
  const [failed, setFailed] = useState(false);
  const box = `${SIZES[size]} shrink-0 overflow-hidden rounded-[4px] border border-edge bg-raised`;

  if (src && !failed) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- owner photos come from our own proxy or arbitrary hosts
      <img src={src} alt={alt ?? `${player ?? 'Card'} photo`} loading="lazy" onError={() => setFailed(true)} className={`${box} object-cover`} />
    );
  }
  return (
    <div className={`${box} flex flex-col p-[3px]`} aria-hidden="true">
      <div className="mb-[3px] h-[18%] rounded-[2px] bg-line" />
      <div className={`flex flex-1 items-center justify-center rounded-[2px] bg-base font-mono font-bold text-muted ${size === 'lg' ? 'text-[28px]' : 'text-[11px]'}`}>
        {initials(player)}
      </div>
    </div>
  );
}
