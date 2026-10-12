// Where a card's picture comes from, in priority order:
// 1. the owner's uploaded photo of this holding  2. an image URL the owner pasted
// 3. the catalog card's default image             4. a drawn placeholder (CardThumb)

export function photoUrl(itemId: number, version: string): string {
  return `/api/backend/collection/items/${itemId}/photo?v=${version}`;
}

export function holdingImage(h: { id: number; photo_version: string | null; image_url: string | null; card_image_url: string | null }): string | null {
  if (h.photo_version) return photoUrl(h.id, h.photo_version);
  return h.image_url || h.card_image_url || null;
}

export function cardImage(c: { photo_item_id: number | null; photo_version: string | null; default_image_url: string | null }): string | null {
  if (c.photo_item_id && c.photo_version) return photoUrl(c.photo_item_id, c.photo_version);
  return c.default_image_url || null;
}

/** Downscale a picked/captured photo in the browser so uploads stay small (phone photos are 3–8 MB). */
export async function resizeForUpload(file: File, maxSide = 900): Promise<{ content_type: string; data_base64: string; preview: string }> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
  return { content_type: 'image/jpeg', data_base64: dataUrl.split(',')[1], preview: dataUrl };
}
