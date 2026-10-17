"""Insert / SSP set guide: products, box types, insert checklists with pack odds, and
sold-price lookups for a checklist card (CompsAPI, cached 7 days per card+parallel)."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT
from app.services import card_photo, compsapi
from app.services.ebay import serials_in

logger = logging.getLogger(__name__)

SEED_DIR = PROJECT_ROOT / "seed" / "sets"
PRICE_CACHE_DAYS = 7
MATCH_VERSION = 2  # bump when title matching changes, so saved 'no sales' results are redone


# --------------------------------------------------------------------------- saving


def save_product(db: Session, data: dict, *, replace: bool = False) -> int:
    """Insert or update a product and everything under it. Values that are missing in
    `data` are left alone, so a partial re-import never wipes what was there."""
    pid = db.execute(text("SELECT id FROM set_product WHERE name = :n"), {"n": data["name"]}).scalar()
    fields = {k: data.get(k) for k in ("sport", "year", "brand", "set_name", "checklist_url", "odds_url", "source_note")}
    if pid is None:
        pid = db.execute(
            text(
                "INSERT INTO set_product (name, sport, year, brand, set_name, checklist_url, odds_url, source_note) "
                "VALUES (:name, :sport, :year, :brand, :set_name, :checklist_url, :odds_url, :source_note) RETURNING id"
            ),
            {"name": data["name"], **fields},
        ).scalar()
    else:
        sets = ", ".join(f"{k} = COALESCE(:{k}, {k})" for k in fields)
        db.execute(text(f"UPDATE set_product SET {sets}, imported_at = NOW() WHERE id = :id"), {**fields, "id": pid})

    for i, b in enumerate(data.get("box_types") or []):
        db.execute(
            text(
                "INSERT INTO set_box_type (product_id, name, packs_per_box, cards_per_pack, boxes_per_case, sort) "
                "VALUES (:p, :n, :ppb, :cpp, :bpc, :s) ON CONFLICT (product_id, name) DO UPDATE SET "
                "packs_per_box = COALESCE(EXCLUDED.packs_per_box, set_box_type.packs_per_box), "
                "cards_per_pack = COALESCE(EXCLUDED.cards_per_pack, set_box_type.cards_per_pack), "
                "boxes_per_case = COALESCE(EXCLUDED.boxes_per_case, set_box_type.boxes_per_case)"
            ),
            {"p": pid, "n": b["name"], "ppb": b.get("packs_per_box"), "cpp": b.get("cards_per_pack"), "bpc": b.get("boxes_per_case"), "s": i},
        )

    for i, ins in enumerate(data.get("inserts") or []):
        iid = db.execute(
            text(
                "INSERT INTO set_insert (product_id, name, code, kind, note, sort) VALUES (:p, :n, :c, :k, :note, :s) "
                "ON CONFLICT (product_id, name) DO UPDATE SET code = COALESCE(EXCLUDED.code, set_insert.code), "
                "note = COALESCE(EXCLUDED.note, set_insert.note) RETURNING id"
            ),
            {"p": pid, "n": ins["name"], "c": ins.get("code"), "k": ins.get("kind") or "ssp", "note": ins.get("note"), "s": i},
        ).scalar()
        for j, par in enumerate(ins.get("parallels") or []):
            odds = {k: int(v) for k, v in (par.get("odds") or {}).items() if v}
            db.execute(
                text(
                    "INSERT INTO set_insert_parallel (insert_id, name, print_run, odds, sort) "
                    "VALUES (:i, :n, :pr, CAST(:o AS JSONB), :s) ON CONFLICT (insert_id, name) DO UPDATE SET "
                    "print_run = COALESCE(EXCLUDED.print_run, set_insert_parallel.print_run), "
                    "odds = set_insert_parallel.odds || EXCLUDED.odds"
                ),
                {"i": iid, "n": par["name"], "pr": par.get("print_run"), "o": json.dumps(odds), "s": j},
            )
        cards = ins.get("cards") or []
        if cards and replace:
            keep = [c["number"] for c in cards]
            db.execute(text("DELETE FROM set_insert_card WHERE insert_id = :i AND NOT (number = ANY(:k))"), {"i": iid, "k": keep})
        for j, c in enumerate(cards):
            db.execute(
                text(
                    "INSERT INTO set_insert_card (insert_id, number, player, team, rookie, sort) VALUES (:i, :num, :pl, :t, :r, :s) "
                    "ON CONFLICT (insert_id, number) DO UPDATE SET player = EXCLUDED.player, "
                    "team = COALESCE(EXCLUDED.team, set_insert_card.team), rookie = EXCLUDED.rookie OR set_insert_card.rookie, sort = EXCLUDED.sort"
                ),
                {"i": iid, "num": c["number"], "pl": c["player"], "t": c.get("team"), "r": bool(c.get("rookie")), "s": j},
            )
    db.commit()
    return pid


def load_seeds(db: Session) -> None:
    """Built-in products (seed/sets/*.json) are added once; later edits/imports are kept."""
    if not SEED_DIR.exists():
        return
    for path in sorted(SEED_DIR.glob("*.json")):
        try:
            data = json.loads(Path(path).read_text())
            exists = db.execute(text("SELECT 1 FROM set_product WHERE name = :n"), {"n": data["name"]}).scalar()
            if not exists:
                save_product(db, data)
                logger.info("Loaded set guide %s", data["name"])
        except Exception:  # a bad seed file must not stop the app
            db.rollback()
            logger.exception("Could not load set guide seed %s", path)


# --------------------------------------------------------------------------- reading


def list_products(db: Session) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT p.id, p.name, p.sport, p.year, p.imported_at, "
            "(SELECT COUNT(*) FROM set_insert i WHERE i.product_id = p.id) AS inserts, "
            "(SELECT COUNT(*) FROM set_insert_card c JOIN set_insert i ON i.id = c.insert_id WHERE i.product_id = p.id) AS cards "
            "FROM set_product p ORDER BY p.year DESC, p.name"
        )
    ).mappings()
    return [dict(r) for r in rows]


def product_detail(db: Session, pid: int) -> dict | None:
    p = db.execute(text("SELECT * FROM set_product WHERE id = :id"), {"id": pid}).mappings().first()
    if not p:
        return None
    boxes = [dict(r) for r in db.execute(text("SELECT id, name, packs_per_box, cards_per_pack, boxes_per_case FROM set_box_type WHERE product_id = :p ORDER BY sort, id"), {"p": pid}).mappings()]
    inserts = [dict(r) for r in db.execute(text("SELECT id, name, code, kind, note, photos_checked_at FROM set_insert WHERE product_id = :p ORDER BY sort, id"), {"p": pid}).mappings()]
    ids = [i["id"] for i in inserts] or [0]
    pars = db.execute(
        text("SELECT id, insert_id, name, print_run, odds FROM set_insert_parallel WHERE insert_id = ANY(:ids) ORDER BY sort, id"), {"ids": ids}
    ).mappings()
    cards = db.execute(
        text("SELECT id, insert_id, number, player, team, rookie, image_url, image_crop, image_locked FROM set_insert_card WHERE insert_id = ANY(:ids) ORDER BY sort, id"),
        {"ids": ids},
    ).mappings()
    prices = db.execute(
        text(
            "SELECT pc.card_id, pc.parallel_id, pc.result, pc.fetched_at FROM set_price_cache pc "
            "JOIN set_insert_card c ON c.id = pc.card_id WHERE c.insert_id = ANY(:ids)"
        ),
        {"ids": ids},
    ).mappings()
    owned = _owned(db, p["year"], ids)

    by_insert: dict[int, dict] = {i["id"]: {**i, "parallels": [], "cards": []} for i in inserts}
    for r in pars:
        by_insert[r["insert_id"]]["parallels"].append({"id": r["id"], "name": r["name"], "print_run": r["print_run"], "odds": r["odds"] or {}})
    card_map: dict[int, dict] = {}
    for r in cards:
        c = {k: r[k] for k in ("id", "number", "player", "team", "rookie", "image_url", "image_crop", "image_locked")}
        c["owned"] = owned.get(r["number"].upper(), 0)
        c["prices"] = {}
        card_map[r["id"]] = c
        by_insert[r["insert_id"]]["cards"].append(c)
    for r in prices:
        res = r["result"] or {}
        stats = res.get("stats") or {}
        last = res.get("last_sale") or {}
        card_map[r["card_id"]]["prices"][str(r["parallel_id"])] = {
            "count": res.get("count", 0),
            "median": stats.get("median"),
            "last": last.get("total"),
            "last_date": last.get("date"),
            "fetched_at": r["fetched_at"].isoformat() if r["fetched_at"] else None,
        }
    return {**dict(p), "box_types": boxes, "inserts": list(by_insert.values())}


def _owned(db: Session, year: int, insert_ids: list[int]) -> dict[str, int]:
    """How many of each checklist number are in the collection (same year, same card #)."""
    rows = db.execute(
        text(
            "SELECT UPPER(c.card_number) AS num, SUM(ci.quantity) AS n FROM collection_item ci JOIN card c ON c.id = ci.card_id "
            "WHERE c.year = :y AND UPPER(c.card_number) IN (SELECT UPPER(number) FROM set_insert_card WHERE insert_id = ANY(:ids)) "
            "GROUP BY UPPER(c.card_number)"
        ),
        {"y": year, "ids": insert_ids},
    ).mappings()
    return {r["num"]: int(r["n"]) for r in rows}


# --------------------------------------------------------------------------- price check


def ascii_fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _compact(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", ascii_fold(s).lower())


def insert_keyword(name: str) -> str:
    """'Ultra Violet All-Stars' -> 'Ultra Violet'; 'The Finals' -> 'Finals'; "Let's Go" -> 'Lets Go'."""
    n = re.sub(r"(?i)\ball[\s-]*stars?\b", "", name)
    n = re.sub(r"(?i)^the\s+", "", n)
    return " ".join(ascii_fold(n).replace("'", "").replace("’", "").split())


def price_query(year: int, set_name: str, insert: str, player: str, parallel: str) -> str:
    parts = [str(year), set_name, insert_keyword(insert), ascii_fold(player)]
    if parallel.lower() != "base":
        parts.append(parallel)
    return " ".join(" ".join(parts).split())


_SET_JUNK = re.compile(r"\b(lot|lots|reprint|custom|digital|break|breaks|you pick|u pick|pick your|choose|random)\b")


_SPORT_WORDS = {
    "basketball": {"basketball", "nba", "wnba"},
    "baseball": {"baseball", "mlb", "bowman"},
    "football": {"football", "nfl"},
    "hockey": {"hockey", "nhl"},
    "soccer": {"soccer", "mls", "uefa", "epl"},
    "f1": {"f1", "formula"},
}
_SUFFIX = {"jr", "sr", "ii", "iii", "iv"}


def _other_sport(t: str, sport: str | None) -> bool:
    """A Fanatical from Topps Chrome Football is not the basketball one."""
    if not sport or sport.lower() not in _SPORT_WORDS:
        return False
    mine = _SPORT_WORDS[sport.lower()]
    words = set(t.split())
    return any(words & ws for k, ws in _SPORT_WORDS.items() if k != sport.lower() and not (ws & mine)) and not (words & mine - {"wnba"})


_NOT_NAMES = set(
    "topps chrome panini prizm select optic bowman donruss rc rookie rookies ssp sp case hit hits insert inserts refractor "
    "parallel card cards nba basketball baseball football f1 sp ssp short print variation var gem mint psa bgs sgc cgc raw "
    "new hot lot the and of a w with auto autograph serial numbered".split()
)


def _words(s: str) -> list[str]:
    return re.sub(r"[^a-z0-9/]+", " ", ascii_fold(s).lower()).split()


def _seq_at(words: list[str], seq: list[str]) -> int:
    for i in range(len(words) - len(seq) + 1):
        if words[i : i + len(seq)] == seq:
            return i
    return -1


def _name_in(t: str, compact: str, player: str, context: set[str] = frozenset()) -> bool:
    """The card's player, not a namesake: 'Dylan Harper' is not 'Bryce Harper', and a
    Robinson from another sport is not David Robinson. Sellers often drop famous first names
    ('Topps Chrome Wembanyama') or last names ('Giannis'), so either alone counts as long as
    no other first name is written next to it."""
    parts = [w for w in _words(player) if w not in _SUFFIX]
    if not parts:
        return False
    words = t.split()
    first, last = parts[0], parts[1:] or parts
    nonname = _NOT_NAMES | context

    def is_nonname(w: str) -> bool:
        return w in nonname or any(ch.isdigit() for ch in w) or len(w) <= 1

    initials = "".join(p[0] for p in _words(" ".join(parts).replace("-", " ")))

    def first_ok(w: str) -> bool:
        return w == first or (len(initials) >= 3 and w == initials) or (len(w) >= 3 and (first.startswith(w) or w.startswith(first[:4])))

    i = _seq_at(words, last)
    if i < 0 and _compact("".join(last)) in compact:  # 'Gilgeous-Alexander' written 'GilgeousAlexander', "O'Neal" as 'ONeal'
        i = next((k for k, w in enumerate(words) if _compact("".join(last)).startswith(w) and _compact("".join(words[k : k + len(last) + 1])).startswith(_compact("".join(last)))), -1)
    if i >= 0:
        if len(parts) == 1 or any(first_ok(w) for w in words):
            return True
        # No first name: the words around the surname must not be another player's name
        # ('Topps Chrome Wembanyama Fanatical' yes; 'Allen Iverson' is not Ray Allen).
        after = i + len(last)
        return (i == 0 or is_nonname(words[i - 1])) and (after >= len(words) or is_nonname(words[after]))
    # Last name missing: a distinctive first name on its own ('Giannis', 'Wemby' is not handled).
    j = next((k for k, w in enumerate(words) if w == first), -1)
    return len(first) >= 6 and j >= 0 and (j + 1 >= len(words) or is_nonname(words[j + 1]))


def match_reason(
    title: str,
    *,
    insert: str,
    player: str,
    parallel: str,
    print_run: int | None,
    other_parallels: list[str],
    sport: str | None = None,
    team: str | None = None,
) -> str | None:
    """None when this sold listing is the checklist card in the asked-for parallel;
    otherwise a short reason it was left out (shown to the owner)."""
    t = " " + re.sub(r"[^a-z0-9/]+", " ", ascii_fold(title).lower()) + " "
    compact = _compact(title)
    if _SET_JUNK.search(t):
        return "lot / break / reprint"
    if _other_sport(t, sport):
        return "another sport"
    context = set(_words(insert)) | {w for p in other_parallels for w in _words(p)} | set(_words(team or ""))
    if not _name_in(t, compact, player, context):
        return "different player"
    if _compact(insert_keyword(insert)) not in compact:
        return f"not {insert_keyword(insert)}"
    serials = serials_in(t)
    is_super = "superfractor" in compact or bool(re.search(r"(?<![\d/])1\s*/\s*1(?![\d/])", t))
    p = parallel.lower()
    if p == "base":
        if is_super:
            return "SuperFractor 1/1"
        if serials:
            return f"numbered /{min(serials)} (a parallel)"
        # A colour word alone can describe the design (a gold trophy); with 'refractor' it's the parallel.
        colours = [w for w in other_parallels if w.lower() not in {"base", "superfractor"} and f" {w.lower()} " in t]
        if colours and re.search(r"\b(refractor|parallel|numbered|ssp /)\b", t):
            return f"{colours[0]} parallel"
        return None
    if p == "superfractor":
        return None if is_super else "not the SuperFractor"
    if f" {p} " not in t and _compact(p) not in compact:
        return f"not {parallel}"
    if print_run and serials and print_run not in serials:
        return f"numbered /{min(serials)}, not /{print_run}"
    return None


def title_matches(title: str, **kw) -> bool:
    return match_reason(title, **kw) is None


def price_check(db: Session, card_id: int, parallel_id: int, force: bool = False) -> dict:
    row = db.execute(
        text(
            "SELECT c.id, c.number, c.player, c.team, c.rookie, c.image_url, i.id AS insert_id, i.name AS insert, "
            "c.image_locked, p.year, p.set_name, p.sport, p.brand, par.name AS parallel, par.print_run "
            "FROM set_insert_card c JOIN set_insert i ON i.id = c.insert_id JOIN set_product p ON p.id = i.product_id "
            "JOIN set_insert_parallel par ON par.id = :par AND par.insert_id = i.id WHERE c.id = :c"
        ),
        {"c": card_id, "par": parallel_id},
    ).mappings().first()
    if not row:
        raise LookupError("card or parallel not found")
    cached = db.execute(
        text("SELECT result, fetched_at FROM set_price_cache WHERE card_id = :c AND parallel_id = :p"), {"c": card_id, "p": parallel_id}
    ).mappings().first()
    fresh = cached and cached["fetched_at"] > datetime.now(timezone.utc) - timedelta(days=PRICE_CACHE_DAYS)
    # Results saved by an older matching rule are looked up again.
    if fresh and not force and (cached["result"] or {}).get("v", 1) >= MATCH_VERSION:
        return {**cached["result"], "cached": True, "fetched_at": cached["fetched_at"].isoformat()}
    if not compsapi.enabled():
        raise compsapi.CompsApiError("compsapi_off: price checks need COMPSAPI_KEY in .env", 503)

    others = [r[0] for r in db.execute(text("SELECT name FROM set_insert_parallel WHERE insert_id = :i"), {"i": row["insert_id"]})]
    q = price_query(row["year"], row["set_name"], row["insert"], row["player"], row["parallel"])
    data = compsapi.fetch_sold(q, {}, None, size=200)
    kw = dict(insert=row["insert"], player=row["player"], parallel=row["parallel"], print_run=row["print_run"], other_parallels=others, sport=row["sport"], team=row["team"])
    items, left_out = [], []
    for r in data["items"]:
        why = match_reason(r["title"], **kw) if r["date"] else "no sale date"
        if why is None:
            items.append({k: r[k] for k in ("item_id", "title", "price", "shipping", "total", "date", "url", "image", "best_offer", "grade")})
        elif len(left_out) < 15:
            left_out.append({"title": r["title"], "total": r["total"], "date": r["date"], "url": r["url"], "why": why})
    items.sort(key=lambda r: r["date"], reverse=True)
    result = {
        "query": q,
        "days": data.get("days"),
        "count": len(items),
        "searched": len(data["items"]),
        "items": items,
        "stats": compsapi._stats([r["total"] for r in items]),
        "last_sale": items[0] if items else None,
        "left_out": left_out,  # what the search found that isn't this card, and why
        "v": MATCH_VERSION,
    }
    db.execute(
        text(
            "INSERT INTO set_price_cache (card_id, parallel_id, query, result, fetched_at) VALUES (:c, :p, :q, CAST(:r AS JSONB), NOW()) "
            "ON CONFLICT (card_id, parallel_id) DO UPDATE SET query = EXCLUDED.query, result = EXCLUDED.result, fetched_at = NOW()"
        ),
        {"c": card_id, "p": parallel_id, "q": q, "r": json.dumps(result)},
    )
    # No photo yet: the best-looking one from these sales (prefer the base insert's).
    if not row["image_url"] and not row["image_locked"] and any(r.get("image") for r in items):
        pick = card_photo.best_photo(items)
        if pick:
            _set_photo(db, card_id, pick)
    db.commit()
    return {**result, "cached": False, "fetched_at": datetime.now(timezone.utc).isoformat()}


# --------------------------------------------------------------------------- photos


def load_photos(db: Session, insert_id: int, force: bool = False) -> dict:
    """One search for the whole insert ('2025 Topps Chrome Fanatical') and a photo for every
    card whose player shows up in the results. Uses eBay live listings when an eBay key is
    set (free), otherwise one CompsAPI sold search. Done once per insert unless `force`."""
    from app.services import ebay

    ins = db.execute(
        text(
            "SELECT i.id, i.name, i.photos_checked_at, p.year, p.set_name, p.sport FROM set_insert i "
            "JOIN set_product p ON p.id = i.product_id WHERE i.id = :i"
        ),
        {"i": insert_id},
    ).mappings().first()
    if not ins:
        raise LookupError("insert not found")
    cards = list(
        db.execute(text("SELECT id, player, team, image_url, image_locked FROM set_insert_card WHERE insert_id = :i ORDER BY sort"), {"i": insert_id}).mappings()
    )
    # force (Re-pick): every card that the owner didn't pick by hand; otherwise only cards with no photo.
    todo = [c for c in cards if not c["image_locked"] and (force or not c["image_url"])]
    if not todo or (ins["photos_checked_at"] and not force):
        return {"source": None, "searched": 0, "added": 0, "missing": sum(1 for c in cards if not c["image_url"]), "skipped": True}

    q = f"{ins['year']} {ins['set_name']} {insert_keyword(ins['name'])}"
    source, items = None, []
    if ebay.ebay_enabled():
        try:
            items = [{"title": a["title"], "image": a.get("image")} for a in ebay.search_listings(q, None, limit=200).get("active", [])]
            source = "ebay"
        except Exception:  # eBay key not working: fall back to CompsAPI
            logger.warning("eBay photo search failed for %s", q, exc_info=True)
    if not any(it.get("image") for it in items):
        if not compsapi.enabled():
            if source is None:
                raise compsapi.CompsApiError("compsapi_off: photos need COMPSAPI_KEY (or an eBay key) in .env", 503)
        else:
            items = [{"title": r["title"], "image": r.get("image")} for r in compsapi.fetch_sold(q, {}, None, size=240)["items"]]
            source = "compsapi"

    others = [r[0] for r in db.execute(text("SELECT name FROM set_insert_parallel WHERE insert_id = :i"), {"i": insert_id})]
    with_photo = [it for it in items if it.get("image")]

    def candidates(player: str, team: str | None) -> list[dict]:
        kw = dict(insert=ins["name"], player=player, print_run=None, other_parallels=others, sport=ins["sport"], team=team)
        base = [it for it in with_photo if title_matches(it["title"], parallel="Base", **kw)]
        # A numbered parallel shows the same design in another colour: only when there's no base photo.
        par = [it for it in with_photo if it not in base and any(title_matches(it["title"], parallel=p, **kw) for p in others if p.lower() != "base")]
        return base + par

    work = [(c, candidates(c["player"], c["team"])[:3]) for c in todo]
    # All photos for the whole insert are fetched and scored together, in parallel.
    analyses = card_photo.analyze_urls([it["image"] for _, cs in work for it in cs])
    picks = [card_photo.best_photo(cs, analyses=analyses) if cs else None for _, cs in work]
    added = 0
    for (c, _), pick in zip(work, picks):
        if pick:
            _set_photo(db, c["id"], pick)
            added += 1
    db.execute(text("UPDATE set_insert SET photos_checked_at = NOW() WHERE id = :i"), {"i": insert_id})
    db.commit()
    missing = db.execute(text("SELECT COUNT(*) FROM set_insert_card WHERE insert_id = :i AND image_url IS NULL"), {"i": insert_id}).scalar()
    return {"source": source, "searched": len(items), "added": added, "missing": missing, "skipped": False}


def _set_photo(db: Session, card_id: int, pick: dict, locked: bool = False) -> None:
    db.execute(
        text("UPDATE set_insert_card SET image_url = :u, image_crop = CAST(:c AS JSONB), image_locked = :l, photo_rev = 2 WHERE id = :id"),
        {"u": pick["url"], "c": json.dumps(pick.get("crop")), "l": locked, "id": card_id},
    )


def choose_photo(db: Session, card_id: int, url: str | None) -> dict:
    """The owner picks a photo (from the card's sales) — or clears it with url=None."""
    if not db.execute(text("SELECT 1 FROM set_insert_card WHERE id = :c"), {"c": card_id}).scalar():
        raise LookupError("card not found")
    if url is None:
        db.execute(text("UPDATE set_insert_card SET image_url = NULL, image_crop = NULL, image_locked = TRUE WHERE id = :c"), {"c": card_id})
        db.commit()
        return {"url": None, "crop": None}
    pick = card_photo.best_photo([{"image": url, "title": ""}]) or {"url": card_photo.display_url(url), "crop": None}
    _set_photo(db, card_id, pick, locked=True)
    db.commit()
    return {"url": pick["url"], "crop": pick.get("crop")}
