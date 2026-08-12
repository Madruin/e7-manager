#!/usr/bin/env python3
"""Shared analysis helpers for e7-manager (session 5).

Loads the collection export, datamine base stats, and RTA meta, and
implements CLAUDE.md's GEAR MATH (WSS) so every analysis script scores gear
the same way. Stdlib only.
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COLLECTION = REPO / "collection" / "autosave-latest.json"
BASE_STATS = REPO / "datamine" / "base_stats.json"
META_CUR = REPO / "meta" / "rta"
META_SS20F = REPO / "meta" / "rta_ss20f"

# --- WSS weights (CLAUDE.md GEAR MATH) -------------------------------------
# Substat type (Fribbels export vocabulary) -> weight, for the % / flat-speed
# stats that need no base-stat normalization.
WSS_WEIGHTS = {
    "Speed": 2.0,
    "CriticalHitChancePercent": 1.6,
    "CriticalHitDamagePercent": 8 / 7,
    "AttackPercent": 1.0,
    "DefensePercent": 1.0,
    "HealthPercent": 1.0,
    "EffectivenessPercent": 1.0,
    "EffectResistancePercent": 1.0,
}
# Flat stats are normalized to their % equivalent against a base stat, then
# weighted 1.0. FLAT_BASE keys map the flat substat type to the reference
# base-stat field in base_stats.json.
FLAT_BASE = {"Attack": "att", "Health": "max_hp", "Defense": "def"}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _norm_name(name: str) -> str:
    return name.lower().replace("'", "").replace("’", "").strip()


class Data:
    """Loaded collection + datamine + meta, with the joins resolved."""

    def __init__(self):
        self.collection = json.loads(COLLECTION.read_text())
        self.items = self.collection["items"]
        self.heroes = self.collection["heroes"]

        bs = json.loads(BASE_STATS.read_text())
        self.base_by_id = bs["heroes"]
        # name -> base-stat record (lv60 6* awakened), punctuation-normalized
        self.base_by_name = {}
        for rec in bs["heroes"].values():
            self.base_by_name.setdefault(_norm_name(rec["name"]), rec)

        # Hero-agnostic reference bases = median lv60/6*/awakened across roster.
        atts, hps, defs = [], [], []
        for rec in bs["heroes"].values():
            s = rec.get("lv60_6star_awakened") or {}
            if s.get("att"):
                atts.append(s["att"])
            if s.get("max_hp"):
                hps.append(s["max_hp"])
            if s.get("def"):
                defs.append(s["def"])
        self.ref_base = {
            "att": statistics.median(atts),
            "max_hp": statistics.median(hps),
            "def": statistics.median(defs),
        }

    # -- base-stat lookup ---------------------------------------------------
    def hero_base(self, hero_name: str) -> dict | None:
        rec = self.base_by_name.get(_norm_name(hero_name))
        if rec is None:
            return None
        return rec.get("lv60_6star_awakened")

    # -- WSS ----------------------------------------------------------------
    def _wss_from_pairs(self, pairs, base: dict) -> float:
        """pairs: iterable of (substat_type, value). base: {att,max_hp,def}."""
        total = 0.0
        for typ, val in pairs:
            if val in (None, 0):
                continue
            if typ in WSS_WEIGHTS:
                total += val * WSS_WEIGHTS[typ]
            elif typ in FLAT_BASE:
                ref = base[FLAT_BASE[typ]]
                total += (val / ref * 100.0) * 1.0  # flat -> %-equivalent
        return total

    def wss(self, item: dict, base: dict | None = None) -> float:
        """Current WSS from the item's live substats.

        base defaults to the hero-agnostic reference bases (median roster),
        so scores are comparable across all gear regardless of who wears it.
        Pass a specific hero's lv60 base dict for a hero-relative score.
        """
        base = base or self.ref_base
        return self._wss_from_pairs(
            ((s["type"], s.get("value")) for s in item["substats"]), base
        )

    def reforge_wss(self, item: dict, base: dict | None = None) -> float:
        """Reforge-projected WSS (lv85+): from reforgedStats, the optimizer's
        lv90 projection. For sub-lv85 gear reforgedStats == current substats,
        so this equals wss(). Excludes the main stat.
        """
        base = base or self.ref_base
        rf = item.get("reforgedStats") or {}
        pairs = [(k, v) for k, v in rf.items()
                 if k not in ("mainType", "mainValue")]
        return self._wss_from_pairs(pairs, base)

    # -- meta ---------------------------------------------------------------
    def meta_for(self, hero_name: str) -> dict | None:
        """Best available RTA meta for a hero: current season if the file
        exists and has a real sample, else the ss20f robust snapshot.
        Returns {source, season, record} or None.
        """
        slug = _slug(hero_name)
        cur = META_CUR / f"{slug}.json"
        old = META_SS20F / f"{slug}.json"
        if cur.exists():
            rec = json.loads(cur.read_text())
            return {"source": "current", "season": rec["season_stats"][0].get("season_code"),
                    "record": rec}
        if old.exists():
            rec = json.loads(old.read_text())
            return {"source": "ss20f", "season": "pvp_rta_ss20f", "record": rec}
        return None


def fmt_int(n) -> str:
    try:
        return f"{int(round(n)):,}"
    except (TypeError, ValueError):
        return str(n)
