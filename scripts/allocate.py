#!/usr/bin/env python3
"""Single-hero gear allocator (session 5, deliverable d — starter).

Given a hero, finds a better 6-piece build from that hero's CURRENT gear plus
all SPARE (unequipped) gear, requiring a real set bonus and maximizing total
reforge-projected WSS. Only spare gear is considered movable, so a suggestion
never silently steals gear off another built hero (the hard part of a global
solver — left as a hook).

Usage: python scripts/allocate.py "Sage Baal & Sezan" [--sets set_speed,set_immune]
"""

from __future__ import annotations

import argparse
import sys
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e7lib import Data  # noqa: E402
from analyze import FRIBBELS_TO_CODE, CODE_TO_NAME, active_sets  # noqa: E402

SLOTS = ["Weapon", "Helmet", "Armor", "Necklace", "Ring", "Boots"]


def equipped_ids(d: Data) -> set:
    ids = set()
    for h in d.heroes:
        for it in (h.get("equipment") or {}).values():
            if it.get("ingameId"):
                ids.add(it["ingameId"])
    return ids


def candidate_pool(d: Data, hero_name: str, exclude_ids: set | None = None):
    """Per slot: the hero's current piece + all spare pieces of that slot.

    exclude_ids: spare pieces already claimed by another hero's plan, so a
    batch of allocations never hands the same physical piece to two heroes.
    The hero's own current gear is never excluded.
    """
    exclude_ids = exclude_ids or set()
    hero = next((h for h in d.heroes if h["name"] == hero_name), None)
    if hero is None or not hero.get("equipment"):
        sys.exit(f"{hero_name}: not found or not geared")
    eq_ids = equipped_ids(d)
    current = {it["gear"]: it for it in hero["equipment"].values()}
    cur_ids = {it.get("ingameId") for it in current.values()}
    # spare = items not equipped by anyone and not already claimed elsewhere
    spare = [x for x in d.items
             if x.get("ingameId") not in eq_ids
             and (x.get("ingameId") not in exclude_ids or x.get("ingameId") in cur_ids)]
    pool = {}
    for slot in SLOTS:
        opts = [it for it in spare if it["gear"] == slot]
        if slot in current:
            opts = [current[slot]] + opts
        pool[slot] = opts
    return hero, current, pool


def build_wss(d: Data, combo) -> float:
    return sum(d.reforge_wss(it) for it in combo)


_PIECES = {c: p for _, (c, p) in FRIBBELS_TO_CODE.items()}


def _set_slots(sets: list[str]) -> int:
    """How many of the 6 slots are accounted for by the active set bonuses."""
    return sum(_PIECES.get(c, 0) for c in sets)


def best_build(d: Data, hero_name: str, want_sets=None, top_k_per_slot=8,
               min_set_slots=4, exclude_ids=None):
    """Search current + spare gear for the highest-WSS build that forms a
    *coherent* set (>= min_set_slots slots in sets — i.e. a 4-piece, or two
    2-piece sets, not a lone 2-piece). Optionally force want_sets. Per-slot
    cap bounds the brute force. exclude_ids blocks spare pieces already claimed
    by another hero's plan (see candidate_pool)."""
    hero, current, pool = candidate_pool(d, hero_name, exclude_ids)
    capped = {s: sorted(v, key=lambda it: -d.reforge_wss(it))[:top_k_per_slot]
              for s, v in pool.items()}
    total = 1
    for s in SLOTS:
        total *= max(len(capped[s]), 1)

    best = None
    for combo in product(*[capped[s] or [None] for s in SLOTS]):
        if any(c is None for c in combo):
            continue
        sets = active_sets(list(combo))
        if not sets or _set_slots(sets) < min_set_slots:
            continue
        if want_sets and set(sets) != set(want_sets):
            continue
        w = build_wss(d, combo)
        if best is None or w > best[0]:
            best = (w, combo, sets)
    return hero, current, best, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hero")
    ap.add_argument("--sets", help="comma-separated set_codes to require, "
                    "e.g. set_speed,set_immune")
    args = ap.parse_args()
    want = args.sets.split(",") if args.sets else None

    d = Data()
    hero, current, best, searched = best_build(d, args.hero, want)
    cur_w = sum(d.reforge_wss(it) for it in current.values())
    cur_sets = active_sets(list(current.values()))

    print(f"# Allocation: {hero['name']}\n")
    print(f"Searched {searched:,} combos from current + spare gear.\n")
    print(f"CURRENT: {cur_w:.0f} WSS · sets "
          f"{'+'.join(CODE_TO_NAME.get(c,c) for c in cur_sets) or 'NONE'}")
    if not best:
        print("No set-forming build found from spare gear.")
        return
    w, combo, sets = best
    print(f"BEST   : {w:.0f} WSS · sets "
          f"{'+'.join(CODE_TO_NAME.get(c,c) for c in sets)}  "
          f"({'+' if w>=cur_w else ''}{w-cur_w:.0f} WSS)\n")
    print("Proposed pieces (◆ = change from current):")
    for slot, it in zip(SLOTS, combo):
        cur = current.get(slot)
        changed = "◆" if (cur is None or cur.get("ingameId") != it.get("ingameId")) else " "
        print(f"  {changed} {slot:9s} {it['set'].replace('Set',''):12s} "
              f"+{it['enhance']:<2} lv{it['level']} main={it['main']['type']:22s} "
              f"WSS {d.reforge_wss(it):.1f}")


if __name__ == "__main__":
    main()
