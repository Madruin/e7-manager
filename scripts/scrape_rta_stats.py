#!/usr/bin/env python3
"""Scrape per-hero RTA stats from epic7rtastats.com into meta/rta/{slug}.json.

Stdlib only, so it runs on a bare GitHub Actions runner or any local Python 3.9+.

How the site serves data (established empirically via --discover runs on
2026-08-01; the cloud dev environment cannot reach the site, see CLAUDE.md):

- Next.js App Router. There are no public JSON API endpoints — probing
  /api/... returns the 404 page, and the client bundles contain no fetch
  URLs. Data is embedded in each page's RSC "flight" payload
  (self.__next_f.push chunks in the HTML), as plain JSON objects.
- /heroes embeds (a) a hero index [{"code":"c5190","name":"Aube",
  "element":"ice","class":"ranger","id":6730}, ...] and (b) current-season
  per-hero aggregates [{"hero_code":"c5190","season_code":"pvp_rta_ss20f",
  "total_games":12837,"total_wins":5736,"total_losses":6490,
  "total_bans":990,"total_prebans":614,"hero_name":"Aube"}, ...].
- /heroes/{hero_code} (e.g. /heroes/c5190; numeric-id and slug variants
  return an empty shell) embeds the per-hero detail data: setStats
  [{set_code,set_name,total_games,total_wins,total_losses,...}],
  artifact rows [{artifact_code,artifact_name,total_games,...}],
  buildStats [{artifact_code,set_agg_code,total_games,...}], plus
  totalSetStatsGames/totalArtifactStatsGames denominators, a seasons list
  with last_updated, daily site-wide game totals, and trend/matchup rows.

So "prefer JSON endpoints over HTML parsing" lands here on: extract the
embedded JSON objects from the flight payload (never scrape rendered HTML).
Output carries the source's own field names (total_games, total_wins, ...)
plus a "derived" block whose formulas are stated inline — no invented
semantics. A hero file is only written when extraction validates; this
script never emits fabricated data.

Modes:
  (default)    scrape heroes given on the command line (or the default
               sample set) into meta/rta/{slug}.json
  --discover   structural probing: dump link map, flight-payload JSON keys,
               keyword contexts, server-action ids. Use when the site
               changes and scraping stops validating.

Politeness: descriptive User-Agent, >=1s between requests, raw responses
cached in scripts/.cache/ (gitignored). --refresh bypasses cache reads.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import sys
import time
from collections import Counter
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# E7_SCRAPER_BASE override exists for --discover recon against other sites
# (e.g. epic7db.com); scrape mode is epic7rtastats-specific.
BASE_URL = os.environ.get("E7_SCRAPER_BASE", "https://www.epic7rtastats.com")
HEROES_PAGE = BASE_URL + "/heroes"
USER_AGENT = (
    "e7-manager-scraper/0.1 (+https://github.com/madruin/e7-manager; "
    "personal single-account analysis; low volume, >=1s between requests)"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "scripts" / ".cache"
OUT_DIR = REPO_ROOT / "meta" / "rta"

DEFAULT_HEROES = ["Aube", "Notos", "Perfumer Byblis", "Harsetti", "Frieren"]


def log(msg: str) -> None:
    print(msg, flush=True)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Fetcher:
    """Rate-limited, caching HTTP client."""

    def __init__(self, refresh: bool = False, min_interval: float = 1.0):
        self.refresh = refresh
        self.min_interval = min_interval
        self._last_request = 0.0
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path:
        return CACHE_DIR / (hashlib.sha256(key.encode()).hexdigest()[:24] + ".json")

    @staticmethod
    def _decode(raw: bytes) -> str:
        if raw[:2] == b"\x1f\x8b":  # gzip magic; error bodies arrive gzipped too
            try:
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            except OSError:
                pass
        return raw.decode("utf-8", errors="replace")

    def fetch(self, url: str, accept: str = "*/*",
              headers: dict | None = None) -> tuple[int, str]:
        """Return (status_code, body_text). Serves from cache unless --refresh.

        Non-2xx responses are returned (not raised) so callers can probe;
        network-level failures return (0, error_string).
        """
        cache = self._cache_path(url + json.dumps(headers or {}, sort_keys=True))
        if not self.refresh and cache.exists():
            entry = json.loads(cache.read_text())
            return entry["status"], entry["body"]

        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": accept,
                "Accept-Encoding": "gzip",
                **(headers or {}),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status, body = resp.status, self._decode(resp.read())
        except urllib.error.HTTPError as e:
            status, body = e.code, self._decode(e.read())
        except (urllib.error.URLError, OSError, ValueError) as e:
            status, body = 0, f"FETCH ERROR: {e}"
        finally:
            self._last_request = time.monotonic()

        cache.write_text(
            json.dumps(
                {"url": url, "fetched_at": utc_now_iso(), "status": status, "body": body}
            )
        )
        return status, body


# ---------------------------------------------------------------------------
# RSC flight payload extraction
# ---------------------------------------------------------------------------

_FLIGHT_RE = re.compile(r'self\.__next_f\.push\(\[1,\s*"((?:[^"\\]|\\.)*)"\]\)')


def flight_payload(html: str) -> str:
    """Concatenate and unescape the Next.js RSC flight chunks embedded in a page."""
    out = []
    for c in _FLIGHT_RE.findall(html):
        try:
            out.append(json.loads(f'"{c}"'))  # JS string escapes ≈ JSON escapes
        except json.JSONDecodeError:
            out.append(c)
    return "".join(out)


def extract_flat_objects(payload: str, required_key: str) -> list[dict]:
    """Pull every flat (non-nested) JSON object containing required_key."""
    objs = []
    for m in re.finditer(r'\{[^{}]*"%s"[^{}]*\}' % re.escape(required_key), payload):
        try:
            objs.append(json.loads(m.group(0)))
        except json.JSONDecodeError:
            continue
    return objs


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------


def load_heroes_payload(fetcher: Fetcher) -> str:
    status, html = fetcher.fetch(HEROES_PAGE, accept="text/html")
    if status != 200:
        sys.exit(f"{HEROES_PAGE} returned HTTP {status}; body head: {html[:300]!r}")
    payload = flight_payload(html)
    if not payload:
        sys.exit(f"{HEROES_PAGE}: no RSC flight chunks found — site layout "
                 "changed; rerun --discover and update this script")
    return payload


def _win_rate(row: dict) -> float | None:
    wins, losses = row.get("total_wins"), row.get("total_losses")
    if isinstance(wins, int) and isinstance(losses, int) and wins + losses > 0:
        return round(wins / (wins + losses), 4)
    return None


def _stat_rows(objs: list[dict], season: str, keep: tuple[str, ...],
               denominator: int | None, top_n: int = 10) -> list[dict]:
    """Filter to one season, keep source fields + derived rates, cap at top_n."""
    rows = []
    for o in objs:
        if o.get("season_code") != season:
            continue
        row = {k: o[k] for k in keep if k in o}
        wr = _win_rate(o)
        if wr is not None:
            row["derived_win_rate"] = wr
        games = o.get("total_games")
        if denominator and isinstance(games, int):
            row["derived_usage_share"] = round(games / denominator, 4)
        rows.append(row)
    rows.sort(key=lambda r: r.get("total_games") or 0, reverse=True)
    return rows[:top_n]


def build_hero_record(fetcher: Fetcher, index_entry: dict,
                      season_rows: list[dict]) -> dict:
    code = index_entry["code"]
    out: dict = {
        "hero": index_entry["name"],
        "hero_slug": slugify(index_entry["name"]),
        "hero_code": code,
        "element": index_entry.get("element"),
        "class": index_entry.get("class"),
    }
    # Season aggregate counts, verbatim from the source. Normally one row
    # (the currently displayed season); keep all if several appear.
    rows = [
        {k: r[k] for k in (
            "season_code", "total_games", "total_wins", "total_losses",
            "total_bans", "total_prebans",
        ) if k in r}
        for r in season_rows
    ]
    out["season_stats"] = rows
    primary = rows[0]
    season = primary.get("season_code")
    out["sample_size"] = primary.get("total_games")

    # Per-hero detail page: sets, artifacts, builds for the current season.
    detail_url = f"{HEROES_PAGE}/{code}"
    status, html = fetcher.fetch(detail_url, accept="text/html")
    if status == 200:
        payload = flight_payload(html)

        m = re.search(r'"totalSetStatsGames":(\d+)', payload)
        set_denom = int(m.group(1)) if m else None
        m = re.search(r'"totalArtifactStatsGames":(\d+)', payload)
        art_denom = int(m.group(1)) if m else None

        objs = [o for o in extract_flat_objects(payload, "hero_code")
                if o.get("hero_code") == code and "date" not in o]
        sets = [o for o in objs if "set_code" in o]
        builds = [o for o in objs if "set_agg_code" in o]
        arts = [o for o in objs
                if "artifact_code" in o and "set_agg_code" not in o]

        top_sets = _stat_rows(sets, season, (
            "set_code", "set_name", "total_games", "total_wins",
            "total_losses", "total_bans"), set_denom)
        top_arts = _stat_rows(arts, season, (
            "artifact_code", "artifact_name", "total_games", "total_wins",
            "total_losses", "total_bans"), art_denom)
        top_builds = _stat_rows(builds, season, (
            "set_agg_code", "artifact_code", "artifact_name", "total_games",
            "total_wins", "total_losses"), None)

        if top_sets:
            out["top_sets"] = top_sets
        if top_arts:
            out["top_artifacts"] = top_arts
        if top_builds:
            out["top_builds"] = top_builds
        if set_denom:
            out["total_set_stats_games"] = set_denom
        if art_denom:
            out["total_artifact_stats_games"] = art_denom

        season_meta = [o for o in extract_flat_objects(payload, "last_updated")
                       if o.get("code") == season]
        if season_meta:
            # Strip the RSC flight "$D" date sentinel from timestamp strings.
            out["season"] = {
                k: (v[2:] if isinstance(v, str) and v.startswith("$D") else v)
                for k, v in season_meta[0].items()
                if k in ("code", "name", "start_date", "last_updated")
            }
    else:
        log(f"WARN {index_entry['name']}: detail page {detail_url} returned "
            f"HTTP {status}; emitting season aggregates only")

    wr = _win_rate(primary)
    derived: dict = {}
    if wr is not None:
        derived["win_rate"] = wr
    if derived:
        derived["formulas"] = {
            "win_rate": "total_wins / (total_wins + total_losses)",
            "derived_win_rate": "per-row total_wins / (total_wins + total_losses)",
            "derived_usage_share": "row total_games / totalSetStatsGames "
                                   "(sets) or totalArtifactStatsGames (artifacts)",
        }
        out["derived"] = derived

    out["source_url"] = detail_url if status == 200 else HEROES_PAGE
    out["scraped_at"] = utc_now_iso()
    return out


def validate_record(rec: dict) -> list[str]:
    problems = []
    if not rec.get("hero_code"):
        problems.append("missing hero_code from hero index")
    rows = rec.get("season_stats") or []
    if not rows:
        problems.append("no season stat rows")
    elif not isinstance(rows[0].get("total_games"), int):
        problems.append("season row lacks integer total_games")
    if "derived" not in rec:
        problems.append("win rate not derivable (missing/zero wins+losses)")
    if "top_sets" not in rec or "top_artifacts" not in rec:
        problems.append("set/artifact stats missing — detail page layout "
                        "changed or hero has no build data this season; "
                        "rerun --discover if this hits a meta-relevant hero")
    return problems


def scrape(fetcher: Fetcher, heroes: list[str], all_mode: bool = False,
           min_games: int = 500, season: str | None = None) -> int:
    payload = load_heroes_payload(fetcher)

    index = extract_flat_objects(payload, "element")
    index = [o for o in index if "code" in o and "name" in o]
    by_name = {o["name"].lower(): o for o in index}
    by_code = {o["code"]: o for o in index}
    stats = extract_flat_objects(payload, "hero_code")
    log(f"payload: {len(index)} heroes in index, {len(stats)} season stat rows")
    if not index or not stats:
        sys.exit("hero index or season stats missing from /heroes payload — "
                 "site layout changed; rerun --discover")

    # A season rollover leaves stale rows from the previous season in the
    # /heroes payload for some heroes. Pin the whole run to ONE season so
    # files never mix seasons: the caller's choice, else the modal season
    # across all rows (the one the site is currently displaying).
    season_hist = Counter(s.get("season_code") for s in stats if s.get("season_code"))
    if season is None:
        season = season_hist.most_common(1)[0][0]
    log(f"season histogram in payload: {dict(season_hist)}")
    log(f"pinning this run to season: {season}")
    stats = [s for s in stats if s.get("season_code") == season]

    # Resolve targets to (index_entry, season_rows) pairs.
    targets: list[tuple[dict, list[dict]]] = []
    failures = 0
    if all_mode:
        rows_by_code: dict[str, list[dict]] = {}
        for s in stats:
            rows_by_code.setdefault(s["hero_code"], []).append(s)
        skipped = []
        for code, rows in rows_by_code.items():
            games = rows[0].get("total_games") or 0
            if code not in by_code:
                log(f"FAIL {code}: season stats but no hero-index entry")
                failures += 1
            elif games < min_games:
                skipped.append(f"{by_code[code]['name']}({games})")
            else:
                targets.append((by_code[code], rows))
        targets.sort(key=lambda t: -(t[1][0].get("total_games") or 0))
        log(f"--all: scraping {len(targets)} heroes with >= {min_games} games; "
            f"skipping {len(skipped)} below the floor: {', '.join(skipped)}")
    else:
        for hero in heroes:
            entry = by_name.get(hero.lower())
            if entry is None:
                close = [n for n in by_name if hero.lower() in n]
                log(f"FAIL {hero}: not in hero index (near matches: {close[:5]})")
                failures += 1
                continue
            rows = [s for s in stats if s.get("hero_code") == entry["code"]]
            if not rows:
                log(f"FAIL {hero}: no season stats for {entry['code']} (hero "
                    "exists but has no games in the displayed season)")
                failures += 1
                continue
            targets.append((entry, rows))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for entry, rows in targets:
        name = entry["name"]
        rec = build_hero_record(fetcher, entry, rows)
        problems = validate_record(rec)
        only_missing_builds = problems and all(
            "set/artifact stats missing" in p for p in problems)
        if problems and all_mode and only_missing_builds:
            # Source genuinely has no build data for this hero this season —
            # nothing to write is not a scraper defect in bulk mode.
            log(f"SKIP {name}: no set/artifact data on detail page "
                f"(games={rec.get('sample_size')})")
            continue
        if problems:
            log(f"FAIL {name}: extracted record did not validate: {problems}")
            log(f"  rows: {rows!r}")
            failures += 1
            continue
        out_path = OUT_DIR / f"{rec['hero_slug']}.json"
        out_path.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
        log(f"OK   {name} -> {out_path.relative_to(REPO_ROOT)} "
            f"(games={rec['sample_size']}, wr={rec.get('derived', {}).get('win_rate')})")
    return failures


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

# Candidate per-hero routes; per-hero set/artifact stats are not in the
# /heroes payload, so look for a detail route that carries them.
DISCOVERY_PAGES = [
    "/heroes/c5190",           # by hero code (Aube)
    "/heroes/6730",            # by numeric id
    "/heroes/aube",            # by slug
    "/heroes?hero=c5190",
    "/heroes?hero_id=6730",
    "/meta",
    "/sets",
    "/artifacts",
]

_KEYWORDS = [
    "hero_code", "seasons", "last_updated", "usage", "artifact_code",
    "set_name", "winRate", "win_rate", "Aube",
    # rank-target recon (epic7db)
    "Legend", "Champion", "Master", "speed", "targets", "stat-",
]


def dump_keyword_contexts(text: str, keywords: list[str], radius: int = 180) -> None:
    for kw in keywords:
        for i, m in enumerate(re.finditer(re.escape(kw), text)):
            if i >= 2:
                break
            s = max(0, m.start() - radius)
            log(f"  [{kw}] ...{text[s:m.end() + radius]!r}...")


def analyze_page(fetcher: Fetcher, path: str) -> None:
    url = urllib.parse.urljoin(BASE_URL + "/", path)
    log(f"\n== page analysis: {url} ==")
    status, html = fetcher.fetch(url, accept="text/html")
    log(f"HTML: HTTP {status}, {len(html)} bytes, "
        f"{len(_FLIGHT_RE.findall(html))} flight chunks")
    if status != 200:
        return
    payload = flight_payload(html)

    if not payload:
        # Not an RSC page — analyze the raw HTML instead.
        for marker in ("__NEXT_DATA__", "__NUXT__", 'type="application/json"',
                       "application/ld+json", "window.__", "fetch(", "axios"):
            n = html.count(marker)
            if n:
                log(f"  raw-HTML marker {marker!r}: {n} occurrence(s)")
        blobs = re.findall(
            r'<script[^>]*type="application/(?:ld\+)?json"[^>]*>(.*?)</script>',
            html, re.S)
        for b in blobs[:5]:
            log(f"  inline JSON blob ({len(b)} chars): {b[:300]!r}")
        hero_links = sorted(set(re.findall(r'href="(/[^"]*hero[^"]*)"', html)))
        log(f"  hero-ish links ({len(hero_links)}): {hero_links[:30]}")
        dump_keyword_contexts(html, _KEYWORDS)
        return

    keys = re.findall(r'"([A-Za-z_][A-Za-z0-9_]{0,40})":', payload)
    freq: dict[str, int] = {}
    for k in keys:
        freq[k] = freq.get(k, 0) + 1
    top = sorted(freq.items(), key=lambda kv: -kv[1])[:60]
    log(f"flight payload: {len(payload)} chars; top JSON keys: {top}")
    dump_keyword_contexts(payload, _KEYWORDS)


def discover(fetcher: Fetcher, pages: list[str] | None = None) -> None:
    log(f"== discovery against {BASE_URL} ==")
    status, html = fetcher.fetch(BASE_URL + "/", accept="text/html")
    log(f"homepage: HTTP {status}, {len(html)} bytes")

    links = sorted({h for h in re.findall(r'href="([^"#?]+)', html)
                    if h.startswith("/")})
    log(f"internal links ({len(links)}): {links[:80]}")

    # Server-action ids in bundles would explain client-side data loads.
    scripts = re.findall(r"""<script[^>]+src=["']([^"']+)["']""", html)
    action_ids: set[str] = set()
    for src in scripts[:12]:
        _, body = fetcher.fetch(urllib.parse.urljoin(BASE_URL + "/", src))
        action_ids |= set(re.findall(r'"([0-9a-f]{40,64})"', body))
    log(f"server-action-like hex ids in bundles: {sorted(action_ids)[:10]} "
        f"({len(action_ids)} total)")

    for path in pages if pages is not None else DISCOVERY_PAGES:
        analyze_page(fetcher, path)

    log("\nDiscovery done.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("heroes", nargs="*", default=None,
                    help=f"hero names (default: {', '.join(DEFAULT_HEROES)})")
    ap.add_argument("--discover", action="store_true",
                    help="probe the live site's structure instead of scraping")
    ap.add_argument("--page", action="append", dest="pages", metavar="PATH",
                    help="with --discover: analyze this page path (repeatable)")
    ap.add_argument("--refresh", action="store_true",
                    help="bypass the response cache (still writes to it)")
    ap.add_argument("--all", action="store_true", dest="all_mode",
                    help="scrape every hero in the current season's stats "
                         "instead of a named list")
    ap.add_argument("--min-games", type=int, default=500,
                    help="with --all: skip heroes below this many season games "
                         "(default 500; their build stats are too noisy)")
    ap.add_argument("--season", metavar="CODE",
                    help="pin to a specific season_code (e.g. pvp_rta_ss20f); "
                         "default is the season the site currently displays")
    args = ap.parse_args()

    fetcher = Fetcher(refresh=args.refresh)
    if args.discover:
        discover(fetcher, pages=args.pages)
        return

    failures = scrape(fetcher, args.heroes or DEFAULT_HEROES,
                      all_mode=args.all_mode, min_games=args.min_games,
                      season=args.season)
    if failures:
        sys.exit(f"{failures} hero(es) failed — nothing fabricated, see log above")


if __name__ == "__main__":
    main()
