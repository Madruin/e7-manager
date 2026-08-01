#!/usr/bin/env python3
"""Scrape per-hero RTA stats from epic7rtastats.com into meta/rta/{slug}.json.

Stdlib only, so it runs on a bare GitHub Actions runner or any local Python 3.9+.

The cloud dev environment cannot reach the site (see CLAUDE.md, OPERATIONAL
NOTES), so endpoint knowledge must come from the live site, not from memory:

  --discover   fetch the homepage + JS bundles, extract candidate API
               endpoints, probe them, and dump what they return. Run this
               first (locally or via the meta-sync workflow) whenever the
               site changes and the scrape mode stops validating.
  (default)    scrape the heroes given on the command line (or the default
               sample set) and write meta/rta/{slug}.json. A hero file is
               only written if the response passes validation — this script
               never emits fabricated or half-parsed data.

Politeness: descriptive User-Agent, >=1s between requests, raw responses
cached in scripts/.cache/ (gitignored). --refresh bypasses cache reads.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://www.epic7rtastats.com"
USER_AGENT = (
    "e7-manager-scraper/0.1 (+https://github.com/madruin/e7-manager; "
    "personal single-account analysis; low volume, >=1s between requests)"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "scripts" / ".cache"
OUT_DIR = REPO_ROOT / "meta" / "rta"

DEFAULT_HEROES = ["Aube", "Notos", "Perfumer Byblis", "Harsetti", "Frieren"]

# Endpoint templates to try per hero, in order. {slug} / {name} / {qname} are
# substituted. This list is (re)populated from --discover output against the
# live site; entries here are only ever *attempted* — every response must pass
# validate_hero_payload() before anything is written, so a wrong guess costs a
# probe request, never bad data.
HERO_ENDPOINT_TEMPLATES: list[str] = [
    "{base}/api/hero/{slug}",
    "{base}/api/heroes/{slug}",
    "{base}/api/hero?name={qname}",
    "{base}/api/stats/hero/{slug}",
    "{base}/api/herostats/{slug}",
]

# Parameterless endpoints worth probing during discovery (hero indexes etc.).
DISCOVERY_PROBE_CANDIDATES = [
    "{base}/api/heroes",
    "{base}/api/hero-list",
    "{base}/api/stats",
]


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

    def _cache_path(self, url: str) -> Path:
        h = hashlib.sha256(url.encode()).hexdigest()[:24]
        return CACHE_DIR / f"{h}.json"

    def fetch(self, url: str, accept: str = "*/*") -> tuple[int, str]:
        """Return (status_code, body_text). Serves from cache unless --refresh.

        Non-2xx responses are returned (not raised) so callers can probe
        candidate endpoints; network-level failures raise.
        """
        cache = self._cache_path(url)
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
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                status, body = resp.status, raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read().decode("utf-8", errors="replace")
        finally:
            self._last_request = time.monotonic()

        cache.write_text(
            json.dumps(
                {"url": url, "fetched_at": utc_now_iso(), "status": status, "body": body}
            )
        )
        return status, body


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

_ENDPOINT_RE = re.compile(
    r"""["'`](
          /(?:api|data|stats|json)/[A-Za-z0-9_./?=&{}$:-]+   # absolute paths
        | https?://[A-Za-z0-9_.-]*epic7rtastats[^"'`\s]+     # own-domain URLs
        | [A-Za-z0-9_./-]+\.json(?:\?[^"'`\s]*)?             # .json assets
    )["'`]""",
    re.VERBOSE,
)


def discover(fetcher: Fetcher) -> None:
    log(f"== discovery against {BASE_URL} ==")
    status, html = fetcher.fetch(BASE_URL + "/", accept="text/html")
    log(f"homepage: HTTP {status}, {len(html)} bytes")
    if status != 200:
        log(f"homepage body (first 1000 chars):\n{html[:1000]}")
        sys.exit(f"discovery aborted: homepage returned {status}")

    candidates: set[str] = set(m.group(1) for m in _ENDPOINT_RE.finditer(html))

    # Embedded app-state blobs (Next/Nuxt) carry both data and route hints.
    for marker in ("__NEXT_DATA__", "__NUXT__", "window.__INITIAL_STATE__"):
        if marker in html:
            log(f"NOTE: homepage embeds {marker} app-state blob")

    scripts = re.findall(r"""<script[^>]+src=["']([^"']+)["']""", html)
    log(f"script tags: {scripts}")
    for src in scripts[:12]:
        url = urllib.parse.urljoin(BASE_URL + "/", src)
        s, body = fetcher.fetch(url)
        found = set(m.group(1) for m in _ENDPOINT_RE.finditer(body))
        log(f"bundle {url}: HTTP {s}, {len(body)} bytes, {len(found)} endpoint hits")
        candidates |= found

    log("\n== candidate endpoints ==")
    for c in sorted(candidates):
        log(f"  {c}")

    log("\n== probing parameterless candidates ==")
    probes = [t.format(base=BASE_URL) for t in DISCOVERY_PROBE_CANDIDATES]
    probes += [
        urllib.parse.urljoin(BASE_URL + "/", c)
        for c in sorted(candidates)
        if "{" not in c and "$" not in c and not c.endswith((".js", ".css"))
    ][:15]
    for url in dict.fromkeys(probes):
        s, body = fetcher.fetch(url, accept="application/json")
        log(f"  {url} -> HTTP {s}; first 400 chars: {body[:400]!r}")

    log("\nDiscovery done. Update HERO_ENDPOINT_TEMPLATES / the parser from the above.")


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------


def try_hero_endpoints(fetcher: Fetcher, hero: str) -> tuple[str, dict] | None:
    """Try each endpoint template; return (url, parsed_json) for the first hit."""
    subs = {
        "base": BASE_URL,
        "slug": slugify(hero),
        "name": hero,
        "qname": urllib.parse.quote(hero),
    }
    for template in HERO_ENDPOINT_TEMPLATES:
        url = template.format(**subs)
        status, body = fetcher.fetch(url, accept="application/json")
        if status != 200:
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        if data:
            return url, data
    return None


def _as_rate(value) -> float | None:
    """Normalize a rate that may arrive as 0-1 float, 0-100 number, or '12.3%'."""
    if isinstance(value, str):
        value = value.strip().rstrip("%")
        try:
            value = float(value)
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    return round(value / 100.0, 6) if value > 1 else round(float(value), 6)


def parse_hero_payload(hero: str, url: str, data: dict) -> dict:
    """Map the site's payload to our schema. Only emit fields actually present.

    NOTE: written against candidate key aliases; validate_hero_payload() gates
    the output, so if the live schema differs this fails loudly instead of
    writing junk. Update the alias table from --discover output.
    """

    def pick(src: dict, *aliases):
        for a in aliases:
            if a in src and src[a] is not None:
                return src[a]
        return None

    out: dict = {"hero": hero, "hero_slug": slugify(hero)}

    n = pick(data, "sample_size", "battles", "total_battles", "games", "count", "picks")
    if isinstance(n, (int, float)):
        out["sample_size"] = int(n)

    for field, aliases in {
        "pick_rate": ("pick_rate", "pickRate", "pick"),
        "ban_rate": ("ban_rate", "banRate", "ban"),
        "win_rate": ("win_rate", "winRate", "win"),
    }.items():
        rate = _as_rate(pick(data, *aliases))
        if rate is not None:
            out[field] = rate

    sets = pick(data, "top_sets", "sets", "set_stats", "setStats", "builds")
    if isinstance(sets, list) and sets:
        parsed = []
        for s in sets:
            if not isinstance(s, dict):
                continue
            entry = {}
            name = pick(s, "sets", "set", "name", "label")
            if name is not None:
                entry["sets"] = name if isinstance(name, list) else [name]
            usage = _as_rate(pick(s, "usage_rate", "usage", "usageRate", "rate", "pick_rate"))
            if usage is not None:
                entry["usage_rate"] = usage
            wr = _as_rate(pick(s, "win_rate", "winRate", "win"))
            if wr is not None:
                entry["win_rate"] = wr
            if entry:
                parsed.append(entry)
        if parsed:
            out["top_sets"] = parsed[:10]

    arts = pick(data, "top_artifacts", "artifacts", "artifact_stats", "artifactStats")
    if isinstance(arts, list) and arts:
        parsed = []
        for a in arts:
            if not isinstance(a, dict):
                continue
            entry = {}
            name = pick(a, "name", "artifact", "label")
            if name is not None:
                entry["name"] = name
            usage = _as_rate(pick(a, "usage_rate", "usage", "usageRate", "rate", "pick_rate"))
            if usage is not None:
                entry["usage_rate"] = usage
            wr = _as_rate(pick(a, "win_rate", "winRate", "win"))
            if wr is not None:
                entry["win_rate"] = wr
            if entry:
                parsed.append(entry)
        if parsed:
            out["top_artifacts"] = parsed[:10]

    stats = pick(data, "stat_medians", "medians", "stats", "stat_distributions", "statAverages")
    if isinstance(stats, dict) and stats:
        out["stats"] = stats

    out["source_url"] = url
    out["scraped_at"] = utc_now_iso()
    return out


def validate_hero_payload(parsed: dict) -> list[str]:
    """Return a list of problems; empty means the file is worth writing."""
    problems = []
    core = {"sample_size", "pick_rate", "ban_rate", "win_rate"}
    if not core & parsed.keys():
        problems.append(
            "no core stat field (sample_size / pick_rate / ban_rate / win_rate) "
            "could be extracted — endpoint schema has diverged; rerun --discover "
            "and update parse_hero_payload()"
        )
    if "top_sets" not in parsed and "top_artifacts" not in parsed:
        problems.append("neither set nor artifact stats extracted")
    return problems


def scrape(fetcher: Fetcher, heroes: list[str]) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0
    for hero in heroes:
        hit = try_hero_endpoints(fetcher, hero)
        if hit is None:
            log(f"FAIL {hero}: no endpoint template returned valid JSON "
                f"(tried {len(HERO_ENDPOINT_TEMPLATES)}). Run with --discover.")
            failures += 1
            continue
        url, data = hit
        parsed = parse_hero_payload(hero, url, data)
        problems = validate_hero_payload(parsed)
        if problems:
            log(f"FAIL {hero}: response from {url} did not validate:")
            for p in problems:
                log(f"  - {p}")
            log(f"  raw payload (first 500 chars): {json.dumps(data)[:500]!r}")
            failures += 1
            continue
        out_path = OUT_DIR / f"{parsed['hero_slug']}.json"
        out_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False) + "\n")
        log(f"OK   {hero} -> {out_path.relative_to(REPO_ROOT)}")
    return failures


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("heroes", nargs="*", default=None,
                    help=f"hero names (default: {', '.join(DEFAULT_HEROES)})")
    ap.add_argument("--discover", action="store_true",
                    help="probe the live site for API endpoints instead of scraping")
    ap.add_argument("--refresh", action="store_true",
                    help="bypass the response cache (still writes to it)")
    args = ap.parse_args()

    fetcher = Fetcher(refresh=args.refresh)
    if args.discover:
        discover(fetcher)
        return

    failures = scrape(fetcher, args.heroes or DEFAULT_HEROES)
    if failures:
        sys.exit(f"{failures} hero(es) failed — nothing fabricated, see log above")


if __name__ == "__main__":
    main()
