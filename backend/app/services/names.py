"""Player-name matching for sold-listing titles, shared by the collection sync and the
set guide: the card's own player, not a namesake ('Dylan Harper' is not 'Bryce Harper')."""

from __future__ import annotations

import re
import unicodedata


def ascii_fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _compact(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", ascii_fold(s).lower())


_SUFFIX = {"jr", "sr", "ii", "iii", "iv"}


_NOT_NAMES = set(
    "topps chrome panini prizm select optic bowman donruss rc rookie rookies ssp sp case hit hits insert inserts refractor "
    "parallel card cards nba basketball baseball football f1 sp ssp short print variation var gem mint psa bgs sgc cgc raw "
    "new hot lot the and of a w with auto autograph serial numbered".split()
)
# Other words sellers put right next to a surname that are never a first name. Only used when
# the first name is missing, so a longer list just means fewer good sales left out.
_NOT_NAMES |= set(
    "base silver gold holo refractor refractors prizm prism logo mint nm nrmt mt graded signed patch jersey relic rpa "
    "rated ex vg pop invest investment sharp clean centered rare fire hof mvp all star allstar stars die cut edition "
    "exclusive mega hobby retail blaster jumbo hanger fanatics box pack exclusive black white red blue green orange "
    "purple pink yellow teal aqua bronze neon wave raywave mojo pulsar geometric superfractor xfractor 1st first "
    "bowman topps panini upper deck donruss chrome finest update series sapphire flagship image photo look read "
    "vintage modern lot lots set sets team usa draft pick picks".split()
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
    # Surname = the last word of the name (a hyphenated one stays whole: Gilgeous-Alexander);
    # middle names are optional ('Kimi Antonelli' / 'Antonelli' for Andrea Kimi Antonelli).
    tokens = [tok for tok in ascii_fold(player).lower().split() if _words(tok) and _words(tok)[0] not in _SUFFIX]
    parts = [w for tok in tokens for w in _words(tok)]
    if not parts:
        return False
    words = t.split()
    first = parts[0]
    last = _words(tokens[-1]) if len(tokens) > 1 else parts
    nonname = _NOT_NAMES | TEAM_WORDS | context | set(parts)

    surname = "".join(last)

    def is_nonname(w: str) -> bool:
        # also a nickname cut from the surname: 'Wemby Wembanyama'
        return w in nonname or any(ch.isdigit() for ch in w) or len(w) <= 1 or (len(w) >= 4 and w[:4] == surname[:4])

    initials = "".join(p[0] for p in _words(" ".join(parts).replace("-", " ")))

    def first_ok(w: str) -> bool:
        # A shortened first name counts ('Shaq', 'Steph'); a short one ('Ray', 'Ja') must be exact,
        # or 'RayWave' / 'James' would pass for it.
        if w == first or (len(initials) >= 3 and w == initials):
            return True
        return len(first) >= 4 and len(w) >= 3 and (first.startswith(w) or w.startswith(first[:4]))

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


TEAM_WORDS = set(
    (
        "cardinals falcons ravens bills panthers bears bengals browns cowboys broncos lions packers texans colts jaguars "
        "chiefs raiders chargers rams dolphins vikings patriots saints giants jets eagles steelers 49ers niners seahawks "
        "buccaneers bucs titans commanders hawks celtics nets hornets bulls cavaliers cavs mavericks mavs nuggets pistons "
        "warriors rockets pacers clippers lakers grizzlies heat bucks timberwolves wolves pelicans knicks thunder magic "
        "76ers sixers suns blazers kings spurs raptors jazz wizards diamondbacks dbacks braves orioles cubs reds guardians "
        "rockies tigers astros royals angels dodgers marlins brewers twins mets yankees athletics phillies pirates padres "
        "mariners rays rangers jays nationals ducks bruins sabres flames hurricanes blackhawks avalanche oilers predators "
        "devils islanders senators flyers penguins sharks kraken blues lightning leafs canucks capitals "
        "ferrari mercedes mclaren williams alpine haas sauber"
    ).split()
)
