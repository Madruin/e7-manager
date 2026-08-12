#!/usr/bin/env python3
"""Build the datamine-backed PvE reference into meta/pve/ (session 6).

This is the T0 foundation of the PvE comp library: what each hunt / Chaos
Gate is, which gear sets it drops, its stages, and its boss id. The actual
COMPS (which heroes) and per-slot stat thresholds must come from community
guides (epic7db) and are intentionally left empty here — see meta/pve/README.
Boss stat tables are not in the normalized datamine, so datamine-derived
speed/bulk thresholds are not available either.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ITEMS = json.loads((REPO / "datamine" / "items.json").read_text())
OUT = REPO / "meta" / "pve"


def set_names():
    return {s["id"]: s.get("name") for s in ITEMS["gear_sets"]}


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    names = set_names()

    hunts = []
    for h in ITEMS["hunts"]:
        hunts.append({
            "enter_key": h["enter_key"],
            "name": h["name"],
            "boss_monster_id": h["boss_monster_id"],
            "reward_material": h.get("reward_material"),
            "drop_sets": [
                {"set_id": e["set_id"], "set_name": names.get(e["set_id"]),
                 "probability": e.get("probability")}
                for e in h.get("set_pool_entries", [])
            ],
            "stages": [s["stage_id"] for s in h.get("stages", [])],
            # populated from epic7db guide harvest (deferred) — one entry per
            # known clear comp: {"name","difficulty","auto":bool,"team":[...],
            #                    "per_slot_thresholds":{...},"source_url"}
            "comps": [],
        })

    chaos = []
    for c in ITEMS["chaos_gate"]:
        chaos.append({
            "id": c["id"], "name": c.get("name"),
            "drop_sets": [
                {"set_id": e["set_id"], "set_name": names.get(e["set_id"]),
                 "probability": e.get("probability")}
                for e in c.get("set_pool_entries", [])
            ],
            "stages": c.get("stages", []),
            "comps": [],
        })

    doc = {
        "source": {"tier": "T0", "kind": "datamine",
                   "from": "datamine/items.json (hunts, chaos_gate, gear_sets)",
                   "note": "Structure/drops/stages are T0. comps[] and stat "
                           "thresholds are NOT datamine-derivable (no boss stat "
                           "tables; comps come from community guides) and are "
                           "left empty pending the epic7db harvest — see README."},
        "hunts": hunts,
        "chaos_gate": chaos,
    }
    (OUT / "hunts.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote meta/pve/hunts.json: {len(hunts)} hunts, {len(chaos)} chaos gate seasons")


if __name__ == "__main__":
    build()
