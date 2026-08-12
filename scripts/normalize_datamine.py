#!/usr/bin/env python3
"""Normalize the raw datamine tables into datamine/{heroes,skills,items}.json.

Reads datamine/raw/tables/*.json (produced by rip_datamine.py) and emits three
committed, snake_case files. Localisation keys are resolved through
text/en/text.db; where a key has no English string the field is omitted rather
than filled in, and no field is written that the tables did not provide.

    python scripts/normalize_datamine.py
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e7pack import REPO_ROOT  # noqa: E402

RAW_TABLES = os.path.join(REPO_ROOT, 'datamine', 'raw', 'tables')
MANIFEST = os.path.join(REPO_ROOT, 'datamine', 'raw', 'manifest.json')
OUT_DIR = os.path.join(REPO_ROOT, 'datamine')

GEAR_TYPES = ('weapon', 'helm', 'armor', 'neck', 'ring', 'boot')
# item_material types worth carrying into analysis; cosmetics are left in raw.
MATERIAL_TYPES = {
    'catalyst', 'rune', 'stone', 'reforge', 'essence', 'material', 'fragment',
    'change', 'ext_drop', 'skillup', 'xpup', 'promotion', 'devotion',
    'gradejump', 'expendable', 'recipe', 'alchemypoint', 'imprint',
    'skillpoint', 'intimacy', 'petfood', 'multi_eq_select',
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def load(name: str) -> list[dict]:
    with open(os.path.join(RAW_TABLES, name + '.json'), encoding='utf-8') as f:
        d = json.load(f)
    return [dict(zip(d['columns'], row)) for row in d['rows']]


def num(value: str):
    """'0.45' -> 0.45, '4' -> 4, '' -> None. Non-numeric strings pass through."""
    if value is None or value == '':
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def compact(d: dict) -> dict:
    """Drop keys whose value is empty -- the tables use '' for 'not set'."""
    return {k: v for k, v in d.items() if v not in ('', None, [], {})}


def source_block(tables: list[str]) -> dict:
    with open(MANIFEST, encoding='utf-8') as f:
        m = json.load(f)
    return {
        'tier': 'T0',
        'kind': 'datamine',
        'source_url': m['ripper']['repo'],
        'tool': 'EpicSevenAssetRipper',
        'tool_commit': m['ripper']['commit'],
        'pack_path': m['pack']['path'],
        'pack_size_bytes': m['pack']['size_bytes'],
        'pack_mtime_utc': m['pack']['mtime_utc'],
        'partition_versions': m['pack']['partition_versions'],
        'tables': tables,
        'extracted_at': m['extracted_at'],
        'normalized_at': dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }


# --------------------------------------------------------------------------
# heroes
# --------------------------------------------------------------------------

CHAR_TABLES = ['character_player', 'character_player_grade2', 'character_player_grade3']
SKILL_TABLES = ['skill_player', 'skill_player_grade2', 'skill_player_grade3']


def build_heroes(text: dict):
    rows, seen = [], set()
    for t in CHAR_TABLES:
        for r in load(t):
            if r['id'] in seen:
                continue
            seen.add(r['id'])
            r['_table'] = t
            rows.append(r)

    heroes = []
    for r in rows:
        # Playable roster only. 'limited' is the type collab/limited heroes carry
        # (Zeno, Sol, Ram, Riza Hawkeye, Stark, ...) -- they are as playable as
        # 'character' rows. complete == 'y' is the client's own released flag: it
        # drops 173 unreleased rows that the text table names "Unknown Hero",
        # plus boss units like c1352 that are named but never obtainable.
        if r['type'] not in ('character', 'limited'):
            continue
        if r['using'] != 'y' or r['race'] != 'hero' or r['complete'] != 'y':
            continue
        base = r['variation_group'] or r['id']
        skills = [r[f'skill{i}'] for i in range(1, 10) if r[f'skill{i}']]
        heroes.append(compact({
            'id': r['id'],
            'name': text.get(r['name']),
            'name_key': r['name'],
            'base_id': base,
            'is_variant': r['id'] != base,
            'original_id': r['original_id'],
            'rarity': num(r['grade']),
            'element': r['ch_attribute'],
            'class': r['role'],
            'zodiac': r['zodiac_sphere2'],
            'is_moonlight': r['moonlight'] == 'y',
            'is_ordinary': r['ordinary'] == 'y',
            'skills': skills,
            'counter_skill': r['counterskill'],
            'dual_attack_skill': r['coopskill'],
            'devotion_skill': r['devotion_skill'],
            'devotion_skill_self': r['devotion_skill_self'],
            'devotion_skill_slots': [s for s in r['devotion_skill_slot'].split(';') if s],
            # personality seeds; the client derives base stats from these plus
            # class and rarity in pass/public.pass (encrypted, not decoded here)
            'stat_seed': compact({'bravery': num(r['bra']), 'intellect': num(r['int']),
                                  'faith': num(r['fai']), 'destiny': num(r['des'])}),
            'stat_rate': compact({'att_rate': num(r['att_rate']),
                                  'max_hp_rate': num(r['max_hp_rate']),
                                  'def_rate': num(r['def_rate']),
                                  'speed_rate': num(r['speed_rate'])}),
            'sell_price': num(r['price']),
            'source_table': r['_table'],
        }))
    heroes.sort(key=lambda h: h['id'])
    return heroes


# --------------------------------------------------------------------------
# skills
# --------------------------------------------------------------------------

def build_skills(text: dict, heroes: list[dict]):
    by_id, order = {}, []
    for t in SKILL_TABLES:
        for r in load(t):
            if r['id'] in by_id:
                continue
            r['_table'] = t
            by_id[r['id']] = r
            order.append(r['id'])

    owner = {}
    for h in heroes:
        for slot, sid in enumerate(h.get('skills', []), start=1):
            owner.setdefault(sid, (h['id'], slot))
        for key in ('counter_skill', 'dual_attack_skill'):
            if h.get(key):
                owner.setdefault(h[key], (h['id'], None))

    # follow soulburn links so a hero's full skill graph is covered
    wanted = set(owner)
    frontier = list(wanted)
    while frontier:
        sid = frontier.pop()
        row = by_id.get(sid)
        if not row:
            continue
        for key in ('soulburn_skill', 'base_skill', 'parent_skill'):
            nxt = row[key]
            if nxt and nxt not in wanted:
                wanted.add(nxt)
                frontier.append(nxt)

    skills = []
    for sid in order:
        if sid not in wanted:
            continue
        r = by_id[sid]
        hero_id, slot = owner.get(sid, (None, None))
        level_effects = [r[f'sk_lv_eff{i}'] for i in range(1, 11) if r[f'sk_lv_eff{i}']]
        skills.append(compact({
            'id': sid,
            'hero_id': hero_id,
            'slot': slot,
            'name': text.get(r['name']),
            'description': text.get(r['sk_description']),
            'is_passive': r['sk_passive'] == 'y',
            'deals_damage': r['deal_damage'] == 'y',
            'cooldown_turns': num(r['turn_cool']),
            'soul_gain': num(r['soul_gain']),
            'soul_required': num(r['soul_req']),
            'soulburn_skill': r['soulburn_skill'],
            'base_skill': r['base_skill'],
            'attack_multiplier': num(r['att_rate']),
            'pow': num(r['pow']),
            'defense_penetration': num(r['def_pen']),
            'target': r['target'],
            'level_effects': level_effects,
            'max_level': num(r['max_lv']),
            'source_table': r['_table'],
        }))

    sklv = {}
    for r in load('sklv'):
        mods = []
        for i in range(1, 7):
            if r[f'type{i}']:
                mods.append(compact({'type': r[f'type{i}'],
                                     'add': num(r[f'add{i}']),
                                     'mul': num(r[f'mul{i}'])}))
        sklv[r['id']] = compact({
            'description': text.get(r['sklv_text']),
            'power': num(r['power']),
            'modifiers': mods,
        })
    return skills, sklv


# --------------------------------------------------------------------------
# items
# --------------------------------------------------------------------------

def build_items(text: dict):
    set_rates = collections.defaultdict(list)
    for r in load('item_set_rate'):
        set_rates[re.sub(r'_\d+$', '', r['id'])].append(r['set_id'])

    gear_sets = []
    for r in load('item_set'):
        effects = []
        for i in (1, 2, 3, 4):
            if r[f'type{i}']:
                effects.append({'type': r[f'type{i}'], 'value': num(r[f'effect{i}'])})
        gear_sets.append(compact({
            'id': r['id'],
            'name': text.get(r['name']),
            'pieces': num(r['set_number']),
            'effects': effects,
            'description': text.get(r['desc']),
            'sort': num(r['sort']),
        }))

    drop_pools = []
    for group, members in sorted(set_rates.items()):
        counts = collections.Counter(members)
        total = sum(counts.values())
        drop_pools.append({
            'id': group,
            'entries': [{'set_id': k, 'weight': v, 'probability': round(v / total, 6)}
                        for k, v in sorted(counts.items())],
        })

    drops = {r['id']: r for r in load('level_enter_drops')}

    def stage_drops(stage_id):
        r = drops.get(stage_id)
        if not r:
            return None
        gear, items = [], []
        for i in range(1, 41):
            item, typ, sid, rate = r[f'item{i}'], r[f'type{i}'], r[f'set{i}'], r[f'grade_rate{i}']
            if not item:
                continue
            if typ == 'e':
                gear.append(compact({'item_id': item, 'set_pool': sid, 'grade_rate': rate}))
            else:
                items.append(compact({'item_id': item, 'name': text.get(item + '_name'),
                                      'count': num(typ)}))
        return compact({'stage_id': stage_id, 'exp': num(r['exp']),
                        'gear_drops': gear, 'item_drops': items})

    hunts = []
    for r in load('level_battlemenu_hunt'):
        key = r['enter_key']
        stages = sorted(sid for sid in drops if sid.startswith(key))
        hunts.append(compact({
            'id': num(r['id']),
            'enter_key': key,
            'name': text.get(r['name']),
            'boss_monster_id': r['monster_id'],
            'set_pool': r['set_id'],
            'set_pool_entries': next((p['entries'] for p in drop_pools
                                      if p['id'] == r['set_id']), []),
            'reward_material': r['reward1'],
            'stages': [s for s in (stage_drops(sid) for sid in stages) if s],
        }))

    chaos_gate = []
    for r in load('level_battlemenu_chaosgate'):
        chaos_gate.append(compact({
            'id': r['id'],
            'name': text.get(r['name']),
            'set_pool': r['show_set'],
            'set_pool_entries': next((p['entries'] for p in drop_pools
                                      if p['id'] == r['show_set']), []),
            'stages': [r['normal_stage_id'], r['hard_stage_id'], r['hell_stage_id']],
        }))

    equipment, artifacts, exclusive = [], [], []
    for r in load('equip_item'):
        base = compact({
            'id': r['id'],
            'name': text.get(r['name']),
            'type': r['type'],
            'tier': num(r['tier']),
            'item_level': num(r['item_level']),
            'rarity_min': num(r['grade_min']),
            'rarity_max': num(r['grade_max']),
            'main_stat': r['main_stat'],
            'sub_stat': r['sub_stat'],
            'sub_stat_count': num(r['sub_stat_count']),
            'sub_stat_count_min': num(r['sub_stat_count_min']),
            'sell_price': num(r['price']),
            'enhance_xp': num(r['xp']),
            'description': text.get(r['desc']),
        })
        if r['type'] == 'artifact':
            artifacts.append(compact({**base,
                                      'artifact_rarity': num(r['artifact_grade']),
                                      'class_restriction': r['role'],
                                      'skill': r['artifact_skill']}))
        elif r['type'] == 'exclusive':
            exclusive.append(compact({**base,
                                      'hero_id': r['exclusive_unit'],
                                      'hero_rarity': num(r['exclusive_grade']),
                                      'skill': r['exclusive_skill'],
                                      'skill_slot': num(r['exclusive_skill_idx'])}))
        elif r['type'] in GEAR_TYPES:
            equipment.append(base)

    stat_scales = []
    for r in load('equip_stat'):
        stat_scales.append(compact({
            'id': r['id'],
            'stat_type': r['stat_type'],
            'val_min': num(r['val_min']),
            'val_max': num(r['val_max']),
            'val_init': num(r['val_init']),
            'val_range': num(r['val_range']),
            'enhance_val_range': num(r['enchance_val_range']),
            'tier_bonus': num(r['tier_bonus']),
        }))

    materials = []
    for r in load('item_material'):
        if r['ma_type'] not in MATERIAL_TYPES:
            continue
        materials.append(compact({
            'id': r['id'],
            'name': text.get(r['name']),
            'type': r['ma_type'],
            'subtype': r['ma_type2'],
            'element': r['attribute'],
            'rarity': num(r['grade']),
            'sell_price': num(r['price']),
            'description': text.get(r['desc']),
        }))

    return {
        'gear_sets': gear_sets,
        'set_drop_pools': drop_pools,
        'hunts': hunts,
        'chaos_gate': chaos_gate,
        'equipment': equipment,
        'artifacts': artifacts,
        'exclusive_equipment': exclusive,
        'stat_scales': stat_scales,
        'materials': materials,
    }


# --------------------------------------------------------------------------

def write(path: str, payload: dict):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write('\n')
    print(f'  {os.path.relpath(path, REPO_ROOT)}  {os.path.getsize(path)/1024:.0f} KB')


def main() -> int:
    text = {r['id']: r['text'] for r in load('text')}
    print(f'{len(text)} English strings loaded')

    heroes = build_heroes(text)
    skills, sklv = build_skills(text, heroes)
    items = build_items(text)

    named = sum(1 for h in heroes if 'name' in h)
    print(f'heroes: {len(heroes)} ({named} with an English name)')
    print(f'skills: {len(skills)}; skill level effects: {len(sklv)}')
    for k, v in items.items():
        print(f'{k}: {len(v)}')

    write(os.path.join(OUT_DIR, 'heroes.json'), {
        'source': source_block([f'db/{t}.db' for t in CHAR_TABLES] + ['text/en/text.db']),
        'notes': [
            'Roster filter: character_player*.type in ("character", "limited"), '
            'using == "y", race == "hero", complete == "y". The complete flag is what '
            'excludes unreleased rows (the text table names them "Unknown Hero").',
            'base_id is the table\'s variation_group: skins (id suffix _s01/_s02) and story '
            'or tutorial duplicates share a base_id with the canonical unit, and carry '
            'is_variant. Variants reuse the base unit\'s skill ids.',
            'stat_seed holds the datamined personality values the client feeds into its '
            'base-stat formula; that formula lives in pass/public.pass (separately '
            'encrypted) and is NOT decoded here, so no derived lv60 stats are emitted.',
        ],
        'count': len(heroes),
        'heroes': heroes,
    })
    write(os.path.join(OUT_DIR, 'skills.json'), {
        'source': source_block([f'db/{t}.db' for t in SKILL_TABLES]
                               + ['db/sklv.db', 'text/en/text.db']),
        'notes': [
            'Only skills reachable from the heroes in heroes.json (slots, counter, dual '
            'attack, and their soulburn/base/parent links).',
            'hero_id/slot name the first hero referencing the skill; skins share their '
            'base unit\'s skill ids, so one skill maps to one hero_id, not to every '
            'variant that uses it.',
            'level_effects lists the per-skill-level entry applied at that level; most '
            'resolve against skill_level_effects, but a few reference condition-state '
            'ids (cs_*) from db/cs_player.db, which is not part of this file.',
            'Descriptions keep the client\'s #placeholder# and <#RRGGBB> markup verbatim. '
            'Skills in slots 1-3 are localised; many slot 4-9 rows have no English string '
            'in the client\'s own text table, so their description field is absent.',
        ],
        'count': len(skills),
        'skills': skills,
        'skill_level_effects': sklv,
    })
    write(os.path.join(OUT_DIR, 'items.json'), {
        'source': source_block([
            'db/item_set.db', 'db/item_set_rate.db', 'db/equip_item.db',
            'db/equip_stat.db', 'db/item_material.db', 'db/level_enter_drops.db',
            'db/level_battlemenu_hunt.db', 'db/level_battlemenu_chaosgate.db',
            'text/en/text.db']),
        'notes': [
            'set_drop_pools give the sets a content source can roll; weights are the '
            'row counts item_set_rate lists per pool, so probability is uniform over rows.',
            'stat_scales are equip_stat val_min/val_max ranges keyed by the main_stat / '
            'sub_stat ids on equipment rows.',
            'materials exclude cosmetic item_material types; the full table stays in '
            'datamine/raw/tables/item_material.json.',
        ],
        **items,
    })
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
