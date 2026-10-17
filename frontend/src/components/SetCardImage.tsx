'use client';

import { useState } from 'react';

/** A card photo in a 5:7 frame. With a crop box (fractions of the photo where the card is),
 *  only the card is shown, edge to edge; otherwise the whole photo is fitted inside. */
export function CardPhoto({
  src,
  crop,
  fallback,
  className = '',
}: {
  src: string | null;
  crop?: number[] | null;
  fallback: React.ReactNode;
  className?: string;
}) {
  const [failed, setFailed] = useState<string | null>(null);
  if (!src || failed === src) return <>{fallback}</>;
  const box = `relative aspect-[5/7] w-full overflow-hidden ${className}`;
  if (crop && crop.length === 4 && crop[2] > crop[0] && crop[3] > crop[1]) {
    const [x0, y0, x1, y1] = crop;
    const w = x1 - x0;
    const h = y1 - y0;
    return (
      <div className={box}>
        {/* eslint-disable-next-line @next/next/no-img-element -- remote eBay images */}
        <img
          src={src}
          alt=""
          loading="lazy"
          onError={() => setFailed(src)}
          className="absolute max-w-none"
          style={{ width: `${100 / w}%`, height: `${100 / h}%`, left: `${(-x0 / w) * 100}%`, top: `${(-y0 / h) * 100}%` }}
        />
      </div>
    );
  }
  return (
    <div className={box}>
      {/* eslint-disable-next-line @next/next/no-img-element -- remote eBay images */}
      <img src={src} alt="" loading="lazy" onError={() => setFailed(src)} className="h-full w-full object-contain" />
    </div>
  );
}
