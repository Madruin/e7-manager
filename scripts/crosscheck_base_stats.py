#!/usr/bin/env python3
"""Cross-check datamine/base_stats.json against epic7db hero pages.

base_stats.json is a T3 substitute (see the file's own tier_note), so it can
drift from the live game between upstream patches. This checks a sample of
heroes against an *independent* source and reports disagreements instead of
silently trusting either side. Run it after every `fetch_base_stats.py`.

epic7db serves plain HTML with a "Base Stats" block reading
`Attack: N Health: N Defense: N Speed: N`, which is what this parses.

**Baselines differ.** base_stats.json stores the *awakened* lv60 6-star figure
(upstream's key is `lv60SixStarFullyAwakened`); epic7db's "Base Stats" block is
the *unawakened* figure, and that site lists awakenings separately. Confirmed
in-game 2026-08-12: Belian reads Speed 110 awakened / 106 unawakened, and the
two sources report exactly those two numbers. So a mismatch here means "this
hero's awakening moves that stat", not "base_stats.json is wrong" — it is only
evidence of a real problem if the gap is large or hits many heroes at once.

    python scripts/crosscheck_base_stats.py
    python scripts/crosscheck_base_stats.py --hero c1001=ras --hero c1117=belian
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e7pack import REPO_ROOT  # noqa: E402

UA = 'e7-manager/1.0 (+https://github.com/Madruin/e7-manager) base-stat cross-check'
BASE_STATS = os.path.join(REPO_ROOT, 'datamine', 'base_stats.json')
CACHE = os.path.join(REPO_ROOT, 'datamine', 'raw', 'external', 'epic7db')

# our hero id -> epic7db slug. A spread of old/new, base/moonlight/specialty.
DEFAULT_PROBES = {
    'c1001': 'ras',
    'c1007': 'vildred',
    'c2007': 'arbiter-vildred',
    'c1117': 'belian',
    'c1153': 'harsetti',
}
# epic7db label -> our stat key
LABELS = {'Attack': 'att', 'Health': 'max_hp', 'Defense': 'def', 'Speed': 'speed'}
BLOCK = re.compile(
    r'Base Stats\s*Attack:\s*([\d,]+)\s*Health:\s*([\d,]+)\s*'
    r'Defense:\s*([\d,]+)\s*Speed:\s*([\d,]+)')


def page(slug: str, refresh: bool) -> str:
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, slug + '.html')
    if not refresh and os.path.exists(path):
        return open(path, encoding='utf-8', errors='replace').read()
    url = f'https://epic7db.com/heroes/{slug}'
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode('utf-8', 'replace')
    open(path, 'w', encoding='utf-8').write(body)
    time.sleep(1.5)  # be polite, per CLAUDE.md scraper conventions
    return body


def epic7db_base_stats(slug: str, refresh: bool):
    text = html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', page(slug, refresh))))
    m = BLOCK.search(text)
    if not m:
        return None
    return dict(zip(LABELS.values(), (int(v.replace(',', '')) for v in m.groups())))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--hero', action='append', metavar='ID=SLUG',
                    help='override the default probe set (repeatable)')
    ap.add_argument('--refresh', action='store_true', help='ignore the page cache')
    args = ap.parse_args()

    probes = DEFAULT_PROBES
    if args.hero:
        probes = dict(p.split('=', 1) for p in args.hero)

    with open(BASE_STATS, encoding='utf-8') as f:
        ours = json.load(f)['heroes']

    agree, disagree, skipped = 0, [], []
    for hid, slug in probes.items():
        mine = ours.get(hid, {}).get('lv60_6star_awakened')
        if not mine:
            skipped.append((hid, slug, 'no base stats in base_stats.json'))
            continue
        try:
            theirs = epic7db_base_stats(slug, args.refresh)
        except Exception as exc:
            skipped.append((hid, slug, f'fetch failed: {exc}'))
            continue
        if theirs is None:
            skipped.append((hid, slug, 'no Base Stats block on the page'))
            continue
        diffs = {k: (mine.get(k), theirs[k]) for k in LABELS.values()
                 if mine.get(k) != theirs[k]}
        name = ours[hid].get('name', hid)
        if diffs:
            disagree.append((hid, name, slug, diffs))
            detail = ', '.join(f'{k}: awakened={a} epic7db_unawakened={b}'
                               for k, (a, b) in diffs.items())
            print(f'  DIFFERS   {hid} {name} ({slug}) -> {detail}')
        else:
            agree += 1
            print(f'  ok        {hid} {name} ({slug}) -> att/max_hp/def/speed all match')

    for hid, slug, why in skipped:
        print(f'  skipped   {hid} ({slug}): {why}')

    print(f'\n{agree}/{len(probes)} probes agree on all four stats; '
          f'{len(disagree)} differ, {len(skipped)} skipped')
    if disagree:
        print('Differences are expected where a hero\'s awakening moves a stat '
              '(we store awakened, epic7db shows unawakened). Treat a large gap, '
              'or many heroes differing at once, as a real problem and confirm '
              'in-game before changing anything.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
