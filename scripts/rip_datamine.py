#!/usr/bin/env python3
"""Extract Epic Seven game tables from the local `data.pack` into datamine/raw/.

Requires the official Epic Seven PC client (STOVE launcher) installed and run
once, so `data.pack` is present. Everything this writes is gitignored; the
committed output is produced by `normalize_datamine.py`.

    python scripts/rip_datamine.py                 # extract the configured tables
    python scripts/rip_datamine.py --all-db        # every db/ table (slow, ~950 files)
    python scripts/rip_datamine.py --list wyvern   # search the pack's file tree
    python scripts/rip_datamine.py --extract-raw 'text/en/text\\.db'

Outputs under datamine/raw/:
    tree.json            every record in data.pack (name/size/offset/extra)
    manifest.json        provenance: pack identity, partition versions, results
    tables/<name>.json   {"table", "columns", "rows"} per parsed table
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e7pack import PackReader, REPO_ROOT, decrypt_db, parse_table, ripper_commit  # noqa: E402

RAW = os.path.join(REPO_ROOT, 'datamine', 'raw')
TREE_PATH = os.path.join(RAW, 'tree.json')
TABLES_DIR = os.path.join(RAW, 'tables')
MANIFEST_PATH = os.path.join(RAW, 'manifest.json')

# Tables the normalizer consumes, plus a few kept for future analysis sessions.
TABLES = [
    # heroes
    'db/character_player.db',
    'db/character_player_grade2.db',
    'db/character_player_grade3.db',
    'db/class_stat_preset.db',
    # skills
    'db/skill_player.db',
    'db/skill_player_grade2.db',
    'db/skill_player_grade3.db',
    'db/sklv.db',
    # gear + items
    'db/equip_item.db',
    'db/equip_stat.db',
    'db/item_set.db',
    'db/item_set_rate.db',
    'db/item_material.db',
    'db/item_special.db',
    'db/recommend_equip.db',
    # content / drops
    'db/level_enter_drops.db',
    'db/level_battlemenu.db',
    'db/level_battlemenu_hunt.db',
    'db/level_battlemenu_chaosgate.db',
    # localisation
    'text/en/text.db',
]


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def build_tree(reader: PackReader) -> list:
    print('scanning data.pack ...', flush=True)
    tree = list(reader.scan())
    os.makedirs(RAW, exist_ok=True)
    with open(TREE_PATH, 'w', encoding='utf-8') as f:
        json.dump(tree, f)
    print(f'  {len(tree)} records -> {TREE_PATH}')
    return tree


def load_tree(reader: PackReader, refresh: bool) -> list:
    if not refresh and os.path.exists(TREE_PATH):
        with open(TREE_PATH, encoding='utf-8') as f:
            return json.load(f)
    return build_tree(reader)


def partition_versions(reader: PackReader, index: dict) -> dict:
    out = {}
    for name, rec in index.items():
        m = re.fullmatch(r'#partion\.(.+)\.ver', name)
        if m and rec['size'] == 4:
            out[m.group(1)] = int.from_bytes(reader.read(rec), 'little')
    return dict(sorted(out.items()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--pack', help='path to data.pack (default: STOVE install, or $E7_PACK)')
    ap.add_argument('--refresh-tree', action='store_true', help='rescan the pack file tree')
    ap.add_argument('--all-db', action='store_true', help='parse every db/ table, not just TABLES')
    ap.add_argument('--list', metavar='REGEX', help='list matching pack records and exit')
    ap.add_argument('--extract-raw', metavar='REGEX',
                    help='dump matching records verbatim to datamine/raw/pack/ (no decrypt)')
    args = ap.parse_args()

    with PackReader(args.pack) as reader:
        tree = load_tree(reader, args.refresh_tree)
        index = {r['name']: r for r in tree}

        if args.list:
            pat = re.compile(args.list, re.I)
            hits = sorted((r for r in tree if pat.search(r['name'])),
                          key=lambda r: -r['size'])
            for r in hits[:400]:
                print(f"{r['size']:>10}  {r['name']}")
            print(f'{len(hits)} match')
            return 0

        if args.extract_raw:
            pat = re.compile(args.extract_raw, re.I)
            dest = os.path.join(RAW, 'pack')
            n = 0
            for r in tree:
                if not pat.search(r['name']):
                    continue
                out = os.path.join(dest, r['name'].replace('/', os.sep))
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, 'wb') as f:
                    f.write(reader.read(r))
                n += 1
            print(f'{n} records -> {dest}')
            return 0

        wanted = TABLES
        if args.all_db:
            wanted = sorted({*TABLES, *(r['name'] for r in tree
                                        if r['name'].startswith('db/')
                                        and not r['name'].startswith('db/story_'))})

        os.makedirs(TABLES_DIR, exist_ok=True)
        ok, failed, missing = {}, {}, []
        for name in wanted:
            rec = index.get(name)
            if rec is None:
                missing.append(name)
                print(f'  MISSING  {name}')
                continue
            try:
                cols, rows = parse_table(decrypt_db(reader.read(rec)))
            except Exception as exc:
                failed[name] = str(exc)
                print(f'  FAILED   {name}: {exc}')
                continue
            out = os.path.join(TABLES_DIR, os.path.basename(name).replace('.db', '') + '.json')
            with open(out, 'w', encoding='utf-8') as f:
                json.dump({'table': name, 'columns': cols, 'rows': rows}, f,
                          ensure_ascii=False)
            ok[name] = {'columns': len(cols), 'rows': len(rows),
                        'output': os.path.relpath(out, REPO_ROOT).replace('\\', '/')}
            print(f'  ok       {name}: {len(rows)} rows x {len(cols)} cols')

        stat = os.stat(reader.pack_path)
        manifest = {
            'extracted_at': utcnow(),
            'pack': {
                'path': reader.pack_path,
                'size_bytes': stat.st_size,
                'mtime_utc': dt.datetime.fromtimestamp(
                    stat.st_mtime, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'records': len(tree),
                'partition_versions': partition_versions(reader, index),
            },
            'ripper': {
                'repo': 'https://github.com/CeciliaBot/EpicSevenAssetRipper',
                'path': reader.ripper_path,
                'commit': ripper_commit(reader.ripper_path),
            },
            'tables': ok,
            'failed': failed,
            'missing': missing,
        }
        with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f'\n{len(ok)} tables parsed, {len(failed)} failed, {len(missing)} missing')
    print(f'manifest -> {MANIFEST_PATH}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
