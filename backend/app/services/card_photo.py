"""Pick the best listing photo for a checklist card.

Sellers' photos range from flat scans that fill the frame to a slab on a desk or a card
lying sideways. Each candidate is downloaded small and scored:
  - how much of the frame the card fills (pixels that differ from the background colour,
    taken from the four corners), and
  - whether that area is card-shaped and upright (about 5:7).
When the card sits on a plain background, the crop box is kept too, so the page can show
just the card, edge to edge.
"""

from __future__ import annotations

import io
import re
from concurrent.futures import ThreadPoolExecutor

import httpx

CARD_RATIO = 5 / 7
_GRADED = re.compile(r"\b(psa|bgs|sgc|cgc|beckett|graded|slab)\b", re.I)


def display_url(url: str) -> str:
    """eBay image URLs carry a size (s-l225): ask for one that's sharp on a tile."""
    return re.sub(r"/s-l\d+\.", "/s-l500.", url)


def _download(url: str) -> bytes | None:
    try:
        r = httpx.get(display_url(url), timeout=8, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
            return r.content
    except httpx.HTTPError:
        pass
    return None


def analyze(data: bytes) -> dict | None:
    """{'fill', 'ratio', 'uniform_bg', 'crop': [x0, y0, x1, y1] fractions, 'score'}."""
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        return None
    try:
        im = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None
    im.thumbnail((240, 240))
    im = im.filter(ImageFilter.MedianFilter(3))
    w, h = im.size
    if w < 20 or h < 20:
        return None
    px = im.load()
    # The frame's outer ring: a plain (even if shaded) background changes slowly along it.
    ring = [px[x, 0] for x in range(w)] + [px[w - 1, y] for y in range(h)] + [px[x, h - 1] for x in range(w - 1, -1, -1)] + [px[0, y] for y in range(h - 1, -1, -1)]
    jumps = [sum(abs(a[i] - b[i]) for i in range(3)) for a, b in zip(ring, ring[1:])]
    uniform = sum(jumps) / len(jumps) < 10 and sorted(jumps)[int(len(jumps) * 0.97)] < 60

    def dist(a, b) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])

    def mix(a, b, t):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)

    if uniform:
        # Background at (x, y): blend of the ring colours on its row and its column (handles shading).
        fgmask = [[min(dist(px[x, y], mix(px[0, y], px[w - 1, y], x / (w - 1))), dist(px[x, y], mix(px[x, 0], px[x, h - 1], y / (h - 1)))) > 60 for x in range(w)] for y in range(h)]
        rows = [sum(r) / w for r in fgmask]
        cols = [sum(fgmask[y][x] for y in range(h)) / h for x in range(w)]
        ys = [y for y, v in enumerate(rows) if v > 0.12]
        xs = [x for x, v in enumerate(cols) if v > 0.12]
        if not xs or not ys:
            return None
        x0, x1, y0, y1 = xs[0], xs[-1] + 1, ys[0], ys[-1] + 1
    else:
        x0, y0, x1, y1 = 0, 0, w, h  # busy edges: the card (or the scene) runs to the frame
    bw, bh = x1 - x0, y1 - y0
    fill = (bw * bh) / (w * h)
    ratio = bw / bh if bh else 0
    shape = max(0.0, 1 - abs(ratio - CARD_RATIO) / 0.25)  # 1 for 5:7, 0 for square or wider
    if uniform:
        score = (0.35 + 0.65 * shape) * (0.55 + 0.45 * fill)  # plain background: we can crop to the card
    else:
        frame = max(0.0, 1 - abs(w / h - CARD_RATIO) / 0.25)
        score = 0.85 * frame  # full-frame photo: good when the frame itself is card-shaped
    crop = None
    if uniform and fill < 0.92 and 0.6 <= ratio <= 0.85:
        pad = 0.005
        crop = [round(max(0, x0 / w - pad), 4), round(max(0, y0 / h - pad), 4), round(min(1, x1 / w + pad), 4), round(min(1, y1 / h + pad), 4)]
    return {"fill": round(fill, 3), "ratio": round(ratio, 3), "uniform_bg": uniform, "crop": crop, "score": round(score, 4)}


def best_photo(candidates: list[dict], download=None, limit: int = 6) -> dict | None:
    """candidates: [{'image', 'title'}] in preference order -> {'url', 'crop', 'score'}."""
    cands = [c for c in candidates if c.get("image")][:limit]
    if not cands:
        return None
    download = download or _download
    with ThreadPoolExecutor(max_workers=6) as pool:
        datas = list(pool.map(lambda c: download(c["image"]), cands))
    best = None
    for i, (c, data) in enumerate(zip(cands, datas)):
        a = analyze(data) if data else None
        score = a["score"] if a else 0.3  # couldn't look at it: keep the listing order
        if _GRADED.search(c.get("title") or ""):
            score *= 0.75  # slabs: label and plastic around the card
        score -= i * 0.01  # tie-break: earlier = better title match / newer
        if best is None or score > best["score"]:
            best = {"url": display_url(c["image"]), "crop": a["crop"] if a else None, "score": round(score, 4)}
    return best
