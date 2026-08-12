#!/usr/bin/env python3
"""Copy the Fribbels optimizer's autosave.json into collection/ and summarise it.

    python scripts/sync_collection.py                       # copy + summarise
    python scripts/sync_collection.py --describe            # schema probe only
    python scripts/sync_collection.py --expect-gear 1420 --expect-heroes 312 --commit

The optimizer writes its save under Documents/FribbelsOptimizerSaves (the
Documents folder may be redirected to OneDrive, so several roots are probed).
This copies the newest autosave.json to collection/autosave-YYYY-MM-DD.json,
dated by the *source file's* mtime rather than today, and refreshes
collection/autosave-latest.json (a copy, not a symlink -- symlinks need
developer mode or admin on Windows).

Counts are discovered from the file's actual structure, never assumed: any
top-level list of objects, or dict-of-objects, is reported. Pass --expect-gear
and --expect-heroes with the numbers you read in-game; a mismatch is refused
rather than committed, per CLAUDE.md's "never commit data you haven't checked".
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e7pack import REPO_ROOT  # noqa: E402

COLLECTION = os.path.join(REPO_ROOT, 'collection')
LATEST = os.path.join(COLLECTION, 'autosave-latest.json')
SAVE_DIRNAME = 'FribbelsOptimizerSaves'

# Substrings that identify which discovered collection is gear vs heroes.
GEAR_HINTS = ('gear', 'item', 'equip')
HERO_HINTS = ('hero', 'unit', 'character')


def candidate_dirs() -> list[str]:
    home = os.path.expanduser('~')
    roots = [os.path.join(home, 'Documents'),
             os.path.join(home, 'OneDrive', 'Documents'),
             os.path.join(home, 'OneDrive - Personal', 'Documents'),
             home]
    env = os.environ.get('E7_FRIBBELS_SAVES')
    out = [env] if env else []
    out += [os.path.join(r, SAVE_DIRNAME) for r in roots]
    return [d for d in out if d and os.path.isdir(d)]


def find_autosave(explicit: str | None) -> str:
    if explicit:
        if not os.path.isfile(explicit):
            raise FileNotFoundError(explicit)
        return explicit
    found = []
    for d in candidate_dirs():
        for dirpath, _, files in os.walk(d):
            for fn in files:
                if fn.lower().endswith('.json') and 'autosave' in fn.lower():
                    found.append(os.path.join(dirpath, fn))
    if not found:
        raise FileNotFoundError(
            'No autosave*.json found. Looked in:\n  '
            + '\n  '.join(candidate_dirs() or ['(no candidate dirs exist)'])
            + '\nRun the optimizer\'s import first, or pass --source PATH '
              '/ set E7_FRIBBELS_SAVES.')
    return max(found, key=os.path.getmtime)


def describe(data):
    """Report the file's real structure: top-level keys and collection sizes."""
    rows = []
    if isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, list):
                kind = 'list'
                n = len(val)
                sample = val[0] if val and isinstance(val[0], dict) else None
            elif isinstance(val, dict):
                kind = 'dict'
                n = len(val)
                first = next(iter(val.values()), None)
                sample = first if isinstance(first, dict) else None
            else:
                rows.append((key, type(val).__name__, '', ''))
                continue
            fields = ', '.join(list(sample.keys())[:12]) if sample else ''
            rows.append((key, kind, str(n), fields))
    return rows


def pick_count(rows, hints):
    """Largest discovered collection whose key matches one of the hints."""
    best = None
    for key, kind, n, _ in rows:
        if kind in ('list', 'dict') and n and any(h in key.lower() for h in hints):
            if best is None or int(n) > best[1]:
                best = (key, int(n))
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--source', help='path to autosave.json (default: auto-discover)')
    ap.add_argument('--describe', action='store_true',
                    help='print the observed schema and exit, copying nothing')
    ap.add_argument('--expect-gear', type=int, help='gear count you see in-game')
    ap.add_argument('--expect-heroes', type=int, help='hero count you see in-game')
    ap.add_argument('--commit', action='store_true',
                    help='git commit the copy with the [collection] prefix')
    args = ap.parse_args()

    try:
        src = find_autosave(args.source)
    except FileNotFoundError as exc:
        print(exc)
        return 1
    mtime = dt.datetime.fromtimestamp(os.path.getmtime(src))
    print(f'source: {src}')
    print(f'        {os.path.getsize(src)/1024/1024:.1f} MB, modified {mtime:%Y-%m-%d %H:%M}')

    with open(src, encoding='utf-8') as f:
        data = json.load(f)

    rows = describe(data)
    print(f'\nobserved top-level structure ({type(data).__name__}):')
    print(f'  {"key":<24} {"kind":<6} {"n":>7}  first item fields')
    for key, kind, n, fields in rows:
        print(f'  {key:<24} {kind:<6} {n:>7}  {fields[:90]}')

    gear = pick_count(rows, GEAR_HINTS)
    heroes = pick_count(rows, HERO_HINTS)
    print(f'\ngear collection  : {gear[0]} = {gear[1]}' if gear else '\ngear collection  : NOT IDENTIFIED')
    print(f'hero collection  : {heroes[0]} = {heroes[1]}' if heroes else 'hero collection  : NOT IDENTIFIED')

    if args.describe:
        return 0

    problems = []
    if args.expect_gear is not None:
        if not gear:
            problems.append('--expect-gear given but no gear collection was identified')
        elif gear[1] != args.expect_gear:
            problems.append(f'gear count {gear[1]} != expected {args.expect_gear}')
    if args.expect_heroes is not None:
        if not heroes:
            problems.append('--expect-heroes given but no hero collection was identified')
        elif heroes[1] != args.expect_heroes:
            problems.append(f'hero count {heroes[1]} != expected {args.expect_heroes}')
    if problems:
        print('\nMISMATCH — refusing to write:')
        for p in problems:
            print(f'  - {p}')
        print('Re-run the optimizer import, or re-check the in-game numbers.')
        return 1
    if args.commit and (args.expect_gear is None or args.expect_heroes is None):
        print('\n--commit requires both --expect-gear and --expect-heroes '
              '(CLAUDE.md: sanity-check before committing).')
        return 1

    os.makedirs(COLLECTION, exist_ok=True)
    dest = os.path.join(COLLECTION, f'autosave-{mtime:%Y-%m-%d}.json')
    shutil.copy2(src, dest)
    shutil.copy2(src, LATEST)
    print(f'\nwrote {os.path.relpath(dest, REPO_ROOT)}')
    print(f'wrote {os.path.relpath(LATEST, REPO_ROOT)}')

    if args.commit:
        subprocess.run(['git', '-C', REPO_ROOT, 'add', dest, LATEST], check=True)
        msg = (f'[collection] Sync Fribbels export {mtime:%Y-%m-%d}\n\n'
               f'{gear[1]} gear, {heroes[1]} heroes; both confirmed against the '
               f'in-game counts.\nSource: {os.path.basename(src)}\n')
        subprocess.run(['git', '-C', REPO_ROOT, 'commit', '-m', msg], check=True)
        print('committed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
