"""Import an insert checklist and its pack odds from public web pages with Playwright.

Pages are rendered in headless Chromium and read as plain text, then parsed:
  checklist rows  "FAN-1 Victor Wembanyama – San Antonio Spurs"  (optionally "RC")
  odds            "1:290 blaster packs", "1:144 Mega", "Odds - 1:295 Hobby; 1:147 Jumbo"
Sites that answer with a bot check (Cloudflare "Just a moment…", captcha) are reported
as blocked; they are never worked around.
"""

from __future__ import annotations

import io
import os
import re

import httpx

from app.services.set_guide import ascii_fold

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"


class Blocked(RuntimeError):
    pass


class FetchFailed(RuntimeError):
    pass


_BLOCK_SIGNS = ("just a moment", "verify you are human", "attention required", "captcha", "access denied", "cf-chl")


def _check_blocked(status: int, title: str, text: str) -> None:
    head = f"{title}\n{text[:2000]}".lower()
    if status in (403, 429, 503) or (len(text) < 3000 and any(s in head for s in _BLOCK_SIGNS)):
        raise Blocked(f"The site answered with a bot check (HTTP {status}). Paste the checklist instead.")


def fetch_text(url: str) -> str:
    """Rendered page text (Playwright). PDFs are downloaded and read as text."""
    if url.lower().split("?")[0].endswith(".pdf"):
        return _pdf_text(url)
    try:
        from playwright.sync_api import Error as PwError
        from playwright.sync_api import sync_playwright
    except ImportError:  # Playwright not installed (e.g. tests): plain HTTP
        return _http_text(url)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_PATH") or None)
            try:
                page = browser.new_page(user_agent=UA, locale="en-US")
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8_000)
                except PwError:
                    pass  # pages with endless ad requests: what's loaded is enough
                title = page.title()
                text = page.inner_text("body")
                status = resp.status if resp else 0
            finally:
                browser.close()
    except PwError as exc:
        raise FetchFailed(f"Could not open {url}: {str(exc).splitlines()[0]}") from exc
    _check_blocked(status, title, text)
    if status >= 400:
        raise FetchFailed(f"{url} answered HTTP {status}")
    return text


def _http_text(url: str) -> str:
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise FetchFailed(f"Could not open {url}: {exc}") from exc
    html = r.text
    title = (re.search(r"<title>(.*?)</title>", html, re.S | re.I) or [None, ""])[1]
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr|table|ul|ol|section|article)>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&#160;", " ", text).replace("&amp;", "&").replace("&#8211;", "–").replace("&#8217;", "'")
    text = "\n".join(" ".join(line.split()) for line in text.splitlines())
    _check_blocked(r.status_code, title, text)
    if r.status_code >= 400:
        raise FetchFailed(f"{url} answered HTTP {r.status_code}")
    return text


def _pdf_text(url: str) -> str:
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=60, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise FetchFailed(f"Could not download {url}: {exc}") from exc
    from pypdf import PdfReader

    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(r.content)).pages)


# --------------------------------------------------------------------------- parsing

_ROW = re.compile(r"^\s*([A-Z]{1,5}-[A-Z0-9]{1,6})\s+(.+?)\s+[–—-]\s+(.+?)\s*(?:\b(RC|Rookie)\b)?\s*$")
_PARALLEL = re.compile(r"([A-Za-z][A-Za-z ]*?)\s*(?:Refractor)?\s*(?:#\s*)?(?:1)?/\s*(\d{1,4})\b")


def _key(name: str) -> str:
    n = re.sub(r"(?i)\b(set|checklist|insert|inserts|cards?)\b", " ", ascii_fold(name))
    return re.sub(r"[^a-z0-9]", "", n.lower())


def _heading_name(line: str) -> str:
    """'2025-26 Topps Chrome – Fanatical Set' -> 'Fanatical'."""
    s = re.split(r"\s[–—-]\s", line)[-1]
    s = re.sub(r"(?i)\b(set|checklist|insert)\b", "", s)
    return " ".join(s.split()).strip(" :")


def parse_checklist(text: str) -> list[dict]:
    """Groups of checklist rows, each named after the heading above it."""
    groups: list[dict] = []
    heading = ""
    pending_parallels: list[dict] = []
    cur: dict | None = None
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            continue
        m = _ROW.match(line)
        if m:
            code, player, team, rc = m.groups()
            prefix = code.split("-")[0]
            if cur is None or cur["code"] != prefix:
                cur = next((g for g in groups if g["code"] == prefix), None)  # rows split by a photo/ad
                if cur is None:
                    cur = {"name": _heading_name(heading) or prefix, "code": prefix, "cards": [], "parallels": pending_parallels}
                    groups.append(cur)
                elif pending_parallels and not cur["parallels"]:
                    cur["parallels"] = pending_parallels
                pending_parallels = []
            team = re.sub(r"\s+(RC|Rookie)$", "", team).strip()
            cur["cards"].append({"number": code, "player": player.strip(), "team": team or None, "rookie": bool(rc) or bool(re.search(r"\bRC\b", raw))})
            continue
        if re.match(r"(?i)^parallels?\b", line):
            pending_parallels = parse_parallels(line)
            continue
        if re.match(r"(?i)^(\d+\s+cards?\b|odds\b|image\b|advertisement|shop\b|buy\b|view\b|see\b)", line):
            continue  # counts, odds lines, photo captions and ads aren't headings
        if len(line) <= 90 and not re.search(r"1:\s?\d", line):
            heading = line
            cur = None
    return groups


def parse_parallels(line: str) -> list[dict]:
    out = []
    body = line.split(":", 1)[-1]
    for part in re.split(r"[;,•|]", body):
        part = part.strip()
        if not part:
            continue
        if re.search(r"(?i)super\s*fractor", part):
            out.append({"name": "SuperFractor", "print_run": 1})
            continue
        m = _PARALLEL.search(part)
        if m:
            out.append({"name": " ".join(m.group(1).replace("Refractor", "").split()), "print_run": int(m.group(2))})
    return out


_BOX_WORDS = r"fanatics\s+mega|breaker'?s?\s+delight|breaker|first\s+day\s+issue|hobby|jumbo|blaster|value|mega|hanger"
_ODDS = re.compile(rf"1\s*:\s*([\d,]+)\s+({_BOX_WORDS})", re.I)


def _box_name(word: str, boxes: list[str]) -> str | None:
    w = " ".join(word.lower().split())
    if w.startswith("fanatics"):
        w = "fanatics mega"
    elif w in ("blaster", "value"):
        w = "value"
    elif w.startswith("breaker"):
        w = "breaker's delight"
    by_lower = {b.lower(): b for b in boxes}
    if w in by_lower:
        return by_lower[w]
    if w == "value" and "value blaster" in by_lower:
        return by_lower["value blaster"]
    return None


def _name_pattern(name: str) -> list[re.Pattern]:
    toks = re.findall(r"[a-z0-9]+", ascii_fold(name).lower())
    variants = [toks]
    if toks and toks[0] == "the":
        variants.append(toks[1:])
    if len(toks) >= 3:
        variants.append(toks[:2])
    return [re.compile(r"\b" + r"[\W_]*".join(map(re.escape, v)) + r"\b", re.I) for v in variants if v]


def parse_odds(text: str, inserts: dict[str, list[str]], boxes: list[str]) -> dict[str, dict[str, dict[str, int]]]:
    """{insert: {parallel: {box: packs}}} — each '1:N box' belongs to the insert named most
    recently before it; a parallel named in the same phrase just before the odds gets them instead."""
    marks: list[tuple[int, int, str]] = []
    for name in inserts:
        for pat in _name_pattern(name):
            marks += [(m.start(), m.end(), name) for m in pat.finditer(ascii_fold(text))]
    marks.sort()
    folded = ascii_fold(text)
    out: dict[str, dict[str, dict[str, int]]] = {}
    for m in _ODDS.finditer(folded):
        before = [mk for mk in marks if mk[0] < m.start()]
        if not before:
            continue
        _, end, name = before[-1]
        if m.start() - end > 600:
            continue  # too far from any insert name to trust
        box = _box_name(m.group(2), boxes)
        if not box:
            continue
        near = folded[max(end, m.start() - 60) : m.start()].lower()  # same phrase, just before the odds
        near = re.split(r"[.;\n]", near)[-1]
        parallel = "Base"
        for p in inserts[name]:
            if p.lower() != "base" and re.search(rf"\b{re.escape(p.lower())}\b", near):
                parallel = p
        out.setdefault(name, {}).setdefault(parallel, {}).setdefault(box, int(m.group(1).replace(",", "")))
    return out


# --------------------------------------------------------------------------- import


def _match_group(group_name: str, names: list[str]) -> str | None:
    g = _key(group_name)
    if len(g) < 3:
        return None
    for n in names:
        k = _key(n)
        if g == k:
            return n
    # Loose match ("Finals" for "The Finals", "Ultra Violet" for "Ultra Violet All-Stars"),
    # but never a different kind of card that shares the name ("Paradox Autographs").
    kinds = re.compile(r"auto|signature|relic|patch|memorabilia|jersey|variation|rookie")
    for n in names:
        k = _key(n)
        k2 = _key(re.sub(r"(?i)^the\s+|all[\s-]*stars?", "", n))
        if len(k2) >= 4 and (k2 in g or g in k) and not (kinds.search(g) and not kinds.search(k)):
            return n
    return None


def guess_product(name: str) -> dict:
    """'2025-26 Topps Chrome Basketball' -> year 2025, brand Topps, set Topps Chrome, sport Basketball."""
    m = re.match(r"\s*(\d{4})(?:-\d{2})?\s+(.*)", name)
    year = int(m.group(1)) if m else 0
    rest = (m.group(2) if m else name).split()
    sports = {"basketball": "Basketball", "baseball": "Baseball", "football": "Football", "hockey": "Hockey", "soccer": "Soccer", "f1": "F1", "formula": "F1"}
    sport = next((sports[w.lower()] for w in rest if w.lower() in sports), "Other")
    set_words = [w for w in rest if w.lower() not in sports and w.lower() not in {"1", "one"}]
    return {"year": year, "brand": set_words[0] if set_words else "", "set_name": " ".join(set_words), "sport": sport}


def run_import(db, name: str, checklist_url: str | None, odds_url: str | None, fetch=fetch_text) -> dict:
    from sqlalchemy import text as sql

    from app.services.set_guide import save_product

    name = " ".join(name.split())
    prod = db.execute(sql("SELECT id, checklist_url, odds_url FROM set_product WHERE name = :n"), {"n": name}).mappings().first()
    checklist_url = checklist_url or (prod and prod["checklist_url"])
    odds_url = odds_url or (prod and prod["odds_url"])
    if not checklist_url and not odds_url:
        raise ValueError("Give a checklist page and/or an odds page to read.")
    existing: dict[str, list[str]] = {}
    boxes = ["Hobby", "Jumbo", "Value", "Mega"]
    if prod:
        for r in db.execute(
            sql("SELECT i.name, p.name AS par FROM set_insert i LEFT JOIN set_insert_parallel p ON p.insert_id = i.id WHERE i.product_id = :p"),
            {"p": prod["id"]},
        ):
            existing.setdefault(r[0], [])
            if r[1]:
                existing[r[0]].append(r[1])
        boxes = [r[0] for r in db.execute(sql("SELECT name FROM set_box_type WHERE product_id = :p ORDER BY sort"), {"p": prod["id"]})] or boxes

    warnings: list[str] = []
    groups: list[dict] = []
    if checklist_url:
        try:
            groups = parse_checklist(fetch(checklist_url))
            if not groups:
                warnings.append("No checklist rows were found on the checklist page.")
        except (Blocked, FetchFailed) as exc:
            warnings.append(f"Checklist: {exc}")

    # Insert names we know: existing ones, else every checklist group (narrowed by the odds page below).
    names = dict(existing) or {g["name"]: ["Base"] + [p["name"] for p in g["parallels"]] for g in groups}
    odds: dict = {}
    if odds_url:
        try:
            odds = parse_odds(fetch(odds_url), names, boxes)
            if not odds:
                warnings.append("No pack odds were found on the odds page.")
        except (Blocked, FetchFailed) as exc:
            warnings.append(f"Odds: {exc}")
    if not existing and odds:
        names = {n: v for n, v in names.items() if n in odds}  # a new product: keep the inserts that have odds (the SSPs)

    inserts: dict[str, dict] = {n: {"name": n, "parallels": [], "cards": []} for n in names}
    unmatched = []
    for g in groups:
        target = _match_group(g["name"], list(names))
        if not target:
            unmatched.append(g["name"])
            continue
        ins = inserts[target]
        ins["code"] = g["code"]
        ins["cards"] = g["cards"]
        ins["parallels"] += [p for p in g["parallels"] if p["name"] not in {q["name"] for q in ins["parallels"]}]
    for n, by_par in odds.items():
        if n not in inserts:
            continue
        for par, o in by_par.items():
            hit = next((p for p in inserts[n]["parallels"] if p["name"].lower() == par.lower()), None)
            if hit:
                hit["odds"] = {**hit.get("odds", {}), **o}
            else:
                inserts[n]["parallels"].append({"name": par, "print_run": None, "odds": o})
    for ins in inserts.values():
        if not any(p["name"].lower() == "base" for p in ins["parallels"]):
            ins["parallels"].insert(0, {"name": "Base", "print_run": None, "odds": {}})

    if not any(i["cards"] or any(p.get("odds") for p in i["parallels"]) for i in inserts.values()):
        return {"product_id": prod["id"] if prod else None, "updated": [], "unmatched": unmatched, "warnings": warnings or ["Nothing usable was found."]}

    data = {"name": name, "checklist_url": checklist_url, "odds_url": odds_url, "inserts": list(inserts.values())}
    if not prod:
        data.update(guess_product(name))
        data["box_types"] = [{"name": b} for b in boxes]
        data["source_note"] = "Imported with Playwright."
    pid = save_product(db, data, replace=True)
    updated = [
        {"name": i["name"], "cards": len(i["cards"]), "odds": sum(len(p.get("odds") or {}) for p in i["parallels"])}
        for i in inserts.values()
        if i["cards"] or any(p.get("odds") for p in i["parallels"])
    ]
    return {"product_id": pid, "updated": updated, "unmatched": unmatched[:30], "warnings": warnings}
