#!/usr/bin/env python3
"""Build datamine/base_stats.json — per-hero base stats keyed by our cXXXX ids.

**Tier downgrade, deliberate.** Base stats are not in any `.db` table: the
client derives them at runtime from the datamined personality seeds via
`formula.lua` inside `pass/public.pass`, which session 2 could not decrypt (see
CLAUDE.md KNOWN UNKNOWNS). This script substitutes a T3 community source until
that formula is recovered, and records the substitution in the output.

Source: the Fribbels E7 Optimizer's bundled hero data
(`data/cache/herodata.json`), which the optimizer needs in order to optimize
and which its maintainers refresh per game patch. Discovered by inspecting the
live repo, not from memory.

Its `calculatedStatus` gives two fully-awakened breakpoints per hero. Stat keys
are renamed to the vocabulary our own T0 tables use (`db/equip_stat.db`,
`db/item_set.db`) so this file joins cleanly with datamine/items.json; the
mapping is written into the output so it stays auditable.

    python scripts/fetch_base_stats.py
    python scripts/fetch_base_stats.py --offline   # reuse the cached download
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e7pack import REPO_ROOT  # noqa: E402

REPO = 'https://github.com/fribbels/Fribbels-Epic-7-Optimizer'
HERODATA_URL = ('https://raw.githubusercontent.com/fribbels/'
                'Fribbels-Epic-7-Optimizer/main/data/cache/herodata.json')
COMMITS_API = ('https://api.github.com/repos/fribbels/Fribbels-Epic-7-Optimizer'
               '/commits?path=data/cache/herodata.json&per_page=1')
UA = 'e7-manager/1.0 (+https://github.com/Madruin/e7-manager)'

CACHE = os.path.join(REPO_ROOT, 'datamine', 'raw', 'external', 'fribbels_herodata.json')
HEROES = os.path.join(REPO_ROOT, 'datamine', 'heroes.json')
OUT = os.path.join(REPO_ROOT, 'datamine', 'base_stats.json')

# Fribbels key -> the stat name our T0 tables use.
KEY_MAP = {
    'atk': 'att',        # equip_stat stat_type 'att'
    'hp': 'max_hp',      # 'max_hp'
    'def': 'def',
    'spd': 'speed',
    'chc': 'cri',        # crit hit chance, 0.15 base
    'chd': 'cri_dmg',    # crit hit damage, 1.5 base
    'dac': 'coop',       # dual attack chance, 0.03 base
    'eff': 'acc',        # effectiveness
    'efr': 'res',        # effect resistance
    'cp': 'cp',          # combat power, Fribbels-only aggregate
}
LEVELS = {
    'lv50FiveStarFullyAwakened': 'lv50_5star_awakened',
    'lv60SixStarFullyAwakened': 'lv60_6star_awakened',
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def upstream_commit() -> dict:
    try:
        c = json.loads(fetch(COMMITS_API))[0]
        return {'sha': c['sha'],
                'date': c['commit']['committer']['date'],
                'subject': c['commit']['message'].splitlines()[0]}
    except Exception as exc:
        print(f'  (could not read upstream commit: {exc})')
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--offline', action='store_true', help='reuse the cached download')
    args = ap.parse_args()

    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    if args.offline and os.path.exists(CACHE):
        print(f'using cached {CACHE}')
        commit = {}
    else:
        print(f'GET {HERODATA_URL}')
        blob = fetch(HERODATA_URL)
        with open(CACHE, 'wb') as f:
            f.write(blob)
        print(f'  {len(blob)} bytes -> {CACHE}')
        commit = upstream_commit()
        if commit:
            print(f'  upstream commit {commit["sha"][:8]} {commit["date"]} '
                  f'({commit["subject"]})')

    with open(CACHE, encoding='utf-8') as f:
        upstream = json.load(f)
    by_code = {h['code']: h for h in upstream.values()}
    print(f'{len(by_code)} upstream hero entries')

    with open(HEROES, encoding='utf-8') as f:
        roster = json.load(f)['heroes']

    out, unmatched = {}, []
    for h in roster:
        # Match rules, in order. A _sNN suffix is a skin, and a skin never
        # changes base stats, so falling back to the un-suffixed code is safe;
        # base_id (variation_group) groups story forms of one hero.
        stripped = h['id'].rsplit('_s', 1)[0] if re.search(r'_s\d+$', h['id']) else None
        for rule, code in (('id', h['id']), ('skin_suffix', stripped),
                           ('variation_group', h['base_id'])):
            if code and code in by_code:
                src, match_rule = by_code[code], rule
                break
        else:
            unmatched.append({'id': h['id'], 'name': h.get('name'),
                              'rarity': h.get('rarity')})
            continue
        entry = {'name': h.get('name'), 'source_code': src['code'],
                 'source_name': src['name'], 'match_rule': match_rule}
        for up_key, our_key in LEVELS.items():
            block = src.get('calculatedStatus', {}).get(up_key)
            if block:
                entry[our_key] = {KEY_MAP[k]: v for k, v in block.items() if k in KEY_MAP}
        out[h['id']] = entry

    payload = {
        'source': {
            'tier': 'T3',
            'tier_note': (
                'T3 SUBSTITUTE for a T0 value. Base stats are not stored in any '
                'data.pack table; the client computes them from the personality '
                'seeds in datamine/heroes.json via formula.lua inside '
                'pass/public.pass, which is not decrypted. Replace this file with '
                'a T0 derivation if that formula is ever recovered.'),
            'source_url': HERODATA_URL,
            'upstream_repo': REPO,
            'upstream_commit': commit.get('sha'),
            'upstream_commit_date': commit.get('date'),
            'upstream_commit_subject': commit.get('subject'),
            'roster': 'datamine/heroes.json',
            'key_mapping': KEY_MAP,
            'scraped_at': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'coverage': {
                'roster_heroes': len(roster),
                'with_base_stats': len(out),
                'unmatched': len(unmatched),
                'upstream_entries': len(by_code),
            },
        },
        'levels': {
            'lv50_5star_awakened': 'upstream calculatedStatus.lv50FiveStarFullyAwakened',
            'lv60_6star_awakened': 'upstream calculatedStatus.lv60SixStarFullyAwakened',
        },
        'notes': [
            'Stats are for a fully awakened hero with no gear and no imprint.',
            'cri / cri_dmg / coop / acc / res are fractions (0.15 = 15%).',
            'cp is the upstream combat-power aggregate, not a game-table value.',
            'Variants (skins, story duplicates) inherit their base unit\'s row; '
            'source_code and match_rule say which upstream entry supplied it and '
            'why ("id" = exact, "skin_suffix" = _sNN skin of that code, '
            '"variation_group" = same variation_group).',
            'unmatched_heroes are roster units the upstream source does not carry '
            'at all; nothing is guessed for them.',
        ],
        'heroes': dict(sorted(out.items())),
        'unmatched_heroes': unmatched,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write('\n')

    print(f'\n{len(out)}/{len(roster)} roster heroes have base stats '
          f'({len(unmatched)} unmatched)')
    for u in unmatched:
        print(f"   unmatched: {u['id']:<12} {u['name']}")
    print(f'{os.path.relpath(OUT, REPO_ROOT)}  {os.path.getsize(OUT)/1024:.0f} KB')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
