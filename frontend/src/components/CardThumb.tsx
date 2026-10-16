'use client';

import { useState } from 'react';

const SIZES = {
  sm: 'h-14 w-10',
  md: 'h-[84px] w-[60px]',
  lg: 'h-[196px] w-[140px]',
} as const;

const ZOOM_W = 260; // enlarged preview width; height follows the photo's own proportions
const ZOOM_MAX_H = 380;
const GAP = 12;

function initials(name: string | null | undefined) {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

/** eBay image URLs carry their size (…/s-l225.jpg); ask for a sharper one for the preview. */
function sharper(src: string) {
  return src.replace(/\/s-l\d+\./, '/s-l800.');
}

/** Card-shaped (5:7) thumbnail; falls back to a drawn slab with the player's initials.
 *  Hovering a photo shows it enlarged (same proportions) beside the pointer's thumbnail. */
export function CardThumb({
  src,
  player,
  size = 'sm',
  alt,
  zoom = size !== 'lg',
}: {
  src: string | null;
  player: string | null;
  size?: keyof typeof SIZES;
  alt?: string;
  zoom?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const box = `${SIZES[size]} shrink-0 overflow-hidden rounded-[4px] border border-edge bg-raised`;

  if (src && !failed) {
    // Fixed positioning so the preview isn't clipped by scrollable tables; flips to the
    // left near the right edge and stays inside the window vertically.
    const show = (el: HTMLElement) => {
      const r = el.getBoundingClientRect();
      const fitsRight = r.right + GAP + ZOOM_W <= window.innerWidth - 8;
      const left = fitsRight ? r.right + GAP : Math.max(8, r.left - GAP - ZOOM_W);
      const top = Math.min(Math.max(8, r.top + r.height / 2 - ZOOM_MAX_H / 2), window.innerHeight - ZOOM_MAX_H - 8);
      setPos({ left, top: Math.max(8, top) });
    };
    return (
      <>
        {/* eslint-disable-next-line @next/next/no-img-element -- owner photos come from our own proxy or arbitrary hosts */}
        <img
          src={src}
          alt={alt ?? `${player ?? 'Card'} photo`}
          loading="lazy"
          onError={() => setFailed(true)}
          onMouseEnter={zoom ? (e) => show(e.currentTarget) : undefined}
          onMouseLeave={zoom ? () => setPos(null) : undefined}
          className={`${box} object-cover ${zoom ? 'cursor-zoom-in' : ''}`}
        />
        {pos && (
          <div
            aria-hidden="true"
            className="pointer-events-none fixed z-50 rounded-md border border-edge bg-base p-1.5 shadow-2xl motion-safe:animate-[fadein_120ms_ease-out]"
            style={{ left: pos.left, top: pos.top, width: ZOOM_W }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- same source as the thumbnail, sharper size */}
            <img
              src={sharper(src)}
              alt=""
              className="block h-auto w-full rounded-[3px] object-contain"
              style={{ maxHeight: ZOOM_MAX_H - 12 }}
              onError={(e) => {
                if (e.currentTarget.src !== src) e.currentTarget.src = src; // sharper size missing: use the thumbnail's
              }}
            />
          </div>
        )}
      </>
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
