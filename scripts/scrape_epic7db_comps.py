#!/usr/bin/env python3
"""Harvest PvE team comps from epic7db's guide library into meta/pve/comps.json.

Structure located 2026-08-12 (session 6, see CLAUDE.md): epic7db.com/guides is
an HTML index; each guide page carries team comps as
`<div class="hero-list hero-team">` blocks whose heroes are `/heroes/{slug}`
links. Per-slot stat thresholds are NOT in structured markup (prose only), so
this harvests **team lists** only and leaves thresholds empty.

Cloud dev sessions can't reach epic7db (egress); run via GitHub Actions or
locally. Stdlib only. Politeness: descriptive UA, >=1s between requests,
responses cached in scripts/.cache/ (gitignored). Emits only comps whose
heroes resolve to our datamine roster, so meta/pve never holds fabricated data.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://epic7db.com"
GUIDES = BASE + "/guides"
UA = ("e7-manager-scraper/0.1 (+https://github.com/madruin/e7-manager; "
      "personal single-account analysis; >=1s between requests)")

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "scripts" / ".cache"
OUT = REPO / "meta" / "pve" / "comps.json"

CONTENT_TAGS = [
    ("wyvern", "wyvern"), ("banshee", "banshee"), ("golem", "golem"),
    ("azimanak", "azimanak"), ("caides", "caides"), ("abyss", "abyss"),
    ("tower", "tower"), ("guild", "guild_war"), ("expedition", "expedition"),
    ("automaton", "automaton_tower"), ("hunt", "hunt"),
]


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class Fetch:
    def __init__(self, refresh=False):
        self.refresh = refresh
        self.last = 0.0
        CACHE.mkdir(parents=True, exist_ok=True)

    def get(self, url: str) -> tuple[int, str]:
        cp = CACHE / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".e7db.json")
        if not self.refresh and cp.exists():
            e = json.loads(cp.read_text())
            return e["status"], e["body"]
        wait = 1.1 - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept": "text/html", "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                status, body = r.status, raw.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            status, body = e.code, ""
        except (urllib.error.URLError, OSError) as e:
            status, body = 0, f"ERR {e}"
        finally:
            self.last = time.monotonic()
        cp.write_text(json.dumps({"status": status, "body": body}))
        return status, body


def hero_slug_map() -> dict:
    """slug(name) -> {name, code} from datamine, non-variant preferred."""
    heroes = json.loads((REPO / "datamine" / "heroes.json").read_text())["heroes"]
    m = {}
    for h in heroes:
        s = slugify(h["name"])
        if s not in m or not h.get("is_variant", False):
            m[s] = {"name": h["name"], "code": h["id"]}
    return m


# team block: <div class="hero-list hero-team"> ... </div> (heroes via /heroes/{slug})
_TEAM_RE = re.compile(r'class="hero-list hero-team".*?(?=class="hero-list|</section|</article|$)',
                      re.S)
_HERO_RE = re.compile(r'/heroes/([a-z0-9-]+)')
_GUIDE_LINK_RE = re.compile(r'href="(https://epic7db\.com/guides/[a-z0-9-]+)"')
_TITLE_RE = re.compile(r"<title>([^<]+)</title>", re.I)


def classify(text: str) -> list[str]:
    t = text.lower()
    return sorted({tag for kw, tag in CONTENT_TAGS if kw in t})


def parse_guide(html: str, url: str, smap: dict) -> dict | None:
    title = (_TITLE_RE.search(html) or [None, ""])[1].strip()
    teams = []
    for m in _TEAM_RE.finditer(html):
        slugs = list(dict.fromkeys(_HERO_RE.findall(m.group(0))))
        team = []
        for s in slugs:
            hit = smap.get(s)
            team.append({"slug": s, "name": hit["name"] if hit else None,
                         "code": hit["code"] if hit else None,
                         "resolved": hit is not None})
        if team:
            teams.append(team)
    if not teams:
        return None
    return {
        "title": title, "source_url": url, "content_tags": classify(title + " " + url),
        "teams": teams, "scraped_at": utc(),
    }


def main():
    refresh = "--refresh" in sys.argv
    f = Fetch(refresh=refresh)
    smap = hero_slug_map()

    s, idx = f.get(GUIDES)
    if s != 200:
        sys.exit(f"/guides returned HTTP {s}; site changed — re-recon.")
    guide_urls = sorted(set(_GUIDE_LINK_RE.findall(idx)))
    print(f"/guides: {len(guide_urls)} guide links")

    comps, skipped = [], 0
    for url in guide_urls:
        gs, gh = f.get(url)
        if gs != 200:
            skipped += 1
            continue
        rec = parse_guide(gh, url, smap)
        if rec is None:
            skipped += 1
            continue
        # resolution rate for validation
        allh = [h for t in rec["teams"] for h in t]
        res = sum(h["resolved"] for h in allh)
        rec["resolved_heroes"] = res
        rec["total_hero_slots"] = len(allh)
        comps.append(rec)
        print(f"OK  {url.split('/')[-1]:40s} teams={len(rec['teams'])} "
              f"heroes {res}/{len(allh)} tags={rec['content_tags']}")

    OUT.write_text(json.dumps({
        "source": {"tier": "T3", "kind": "guide_scrape", "site": "epic7db.com/guides",
                   "note": "Team comps only; per-slot stat thresholds are prose on "
                           "epic7db and are NOT captured. Hero names resolved to "
                           "datamine roster; unresolved slugs kept with resolved=false."},
        "scraped_at": utc(), "guide_count": len(comps),
        "comps": comps,
    }, indent=2, ensure_ascii=False) + "\n")
    print(f"\nwrote meta/pve/comps.json: {len(comps)} guides, {skipped} skipped")


if __name__ == "__main__":
    main()
