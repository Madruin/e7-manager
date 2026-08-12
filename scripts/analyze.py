#!/usr/bin/env python3
"""Session-5 analysis core for e7-manager. Stdlib only.

Produces committed reports under analysis/ from the collection export,
datamine, and RTA meta:

  gear_scores.json   every gear piece scored (WSS + reforge projection)
  gear_report.md     gear-quality distribution, best pieces, reforge & enhance EV
  hero_builds.md     per built hero: 6-piece WSS, active sets, meta set-alignment
  priority.md        cross-mode + per-mode hero investment priority

Run: python scripts/analyze.py
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e7lib import Data, fmt_int, _slug  # noqa: E402

ANALYSIS = Path(__file__).resolve().parent.parent / "analysis"

# Fribbels PascalCase set -> (meta set_code, pieces-per-set) from datamine.
FRIBBELS_TO_CODE = {
    "AttackSet": ("set_att", 4), "HealthSet": ("set_max_hp", 2),
    "DefenseSet": ("set_def", 2), "CriticalSet": ("set_cri", 2),
    "HitSet": ("set_acc", 2), "ResistSet": ("set_res", 2),
    "SpeedSet": ("set_speed", 4), "DestructionSet": ("set_cri_dmg", 4),
    "LifestealSet": ("set_vampire", 4), "CounterSet": ("set_counter", 4),
    "UnitySet": ("set_coop", 2), "ImmunitySet": ("set_immune", 2),
    "RageSet": ("set_rage", 4), "RevengeSet": ("set_revenge", 4),
    "InjurySet": ("set_scar", 4), "PenetrationSet": ("set_penetrate", 2),
    "ProtectionSet": ("set_shield", 4), "TorrentSet": ("set_torrent", 2),
    "ReversalSet": ("set_revenant", 4), "RiposteSet": ("set_riposte", 4),
    "WarfareSet": ("set_opener", 4), "PursuitSet": ("set_chase", 2),
    "WeakeningSet": ("set_weak", 4), "FervorSet": ("set_might", 2),
}
CODE_TO_NAME = {c: f.replace("Set", "") for f, (c, _) in FRIBBELS_TO_CODE.items()}


def active_sets(equip_items) -> list[str]:
    """Given 6 equipped items, return the active set bonuses as set_codes,
    greedily (4-piece sets first). E.g. ['set_speed', 'set_immune']."""
    counts = Counter(it["set"] for it in equip_items)
    active = []
    # resolve 4-piece first, then 2-piece
    for need in (4, 2):
        for fset, (code, pieces) in FRIBBELS_TO_CODE.items():
            if pieces != need:
                continue
            while counts.get(fset, 0) >= pieces:
                active.append(code)
                counts[fset] -= pieces
    return sorted(active)


def load() -> Data:
    ANALYSIS.mkdir(exist_ok=True)
    return Data()


# ---------------------------------------------------------------------------
# (a) gear scoring
# ---------------------------------------------------------------------------

def score_all(d: Data) -> list[dict]:
    # map item ingameId -> hero name (via heroes[].equipment)
    id_to_hero = {}
    for h in d.heroes:
        for it in (h.get("equipment") or {}).values():
            if it.get("ingameId"):
                id_to_hero[it["ingameId"]] = h["name"]
    rows = []
    for x in d.items:
        w = d.wss(x)
        rw = d.reforge_wss(x)
        rows.append({
            "ingameId": x.get("ingameId"),
            "gear": x["gear"], "set": x["set"], "rank": x["rank"],
            "level": x["level"], "enhance": x["enhance"],
            "main": x["main"]["type"],
            "wss": round(w, 2), "reforge_wss": round(rw, 2),
            "reforge_gain": round(rw - w, 2),
            "reforge_pending": x["level"] < 90 and (rw - w) > 0.05,
            "equipped_by": id_to_hero.get(x.get("ingameId")),
            "locked": x.get("locked", False),
        })
    return rows


def gear_report(d: Data, rows: list[dict]) -> None:
    (ANALYSIS / "gear_scores.json").write_text(
        json.dumps({"note": "WSS per CLAUDE.md GEAR MATH; reforge_wss = lv90 "
                    "projection from reforgedStats; hero-agnostic reference "
                    "bases (median lv60/6*).", "count": len(rows),
                    "items": rows}, indent=2) + "\n")

    import statistics as st
    vals = [r["reforge_wss"] for r in rows]
    epic = [r for r in rows if r["rank"] == "Epic"]
    equipped = [r for r in rows if r["equipped_by"]]
    L = ["# Gear report", "",
         f"1068 pieces. Scored by **reforge-projected WSS** (CLAUDE.md gear math). "
         f"Reference bases: median lv60/6* Atk {fmt_int(d.ref_base['att'])}, "
         f"HP {fmt_int(d.ref_base['max_hp'])}, Def {fmt_int(d.ref_base['def'])}.",
         "",
         f"- Median WSS {st.median(vals):.1f} · p90 {sorted(vals)[int(len(vals)*.9)]:.1f} · max {max(vals):.1f}",
         f"- Equipped pieces: {len(equipped)} · spare: {len(rows)-len(equipped)}",
         f"- Ranks: " + ", ".join(f"{k} {v}" for k, v in Counter(r['rank'] for r in rows).items()),
         ""]

    L += ["## Top 20 pieces (reforge-projected WSS)", "",
          "| WSS | cur | gear | set | main | +enh | lv | equipped by |",
          "|--:|--:|---|---|---|--:|--:|---|"]
    for r in sorted(rows, key=lambda r: -r["reforge_wss"])[:20]:
        L.append(f"| {r['reforge_wss']:.1f} | {r['wss']:.1f} | {r['gear']} | "
                 f"{r['set'].replace('Set','')} | {r['main']} | +{r['enhance']} | "
                 f"{r['level']} | {r['equipped_by'] or '—'} |")

    pending = sorted([r for r in rows if r["reforge_pending"]],
                     key=lambda r: -r["reforge_gain"])
    L += ["", "## Reforge-pending (lv85, not yet reforged to 90)", "",
          f"{len(pending)} pieces would gain WSS from reforge. Top gains:", "",
          "| +WSS gain | -> reforged | gear | set | equipped by |",
          "|--:|--:|---|---|---|"]
    for r in pending[:20]:
        L.append(f"| +{r['reforge_gain']:.1f} | {r['reforge_wss']:.1f} | {r['gear']} | "
                 f"{r['set'].replace('Set','')} | {r['equipped_by'] or '—'} |")

    # enhance EV: +0 epic/heroic pieces, projected +15 via reforgedStats already
    # reflects full substats; for +0 pieces reforgedStats==current low value, so
    # rank spare unenhanced epics by their current partial WSS as a keep signal.
    unenh = [r for r in rows if r["enhance"] == 0 and r["rank"] in ("Epic", "Heroic")
             and not r["equipped_by"]]
    L += ["", "## Enhancement EV (spare un-enhanced epic/heroic)", "",
          f"{len(unenh)} spare +0 epic/heroic pieces. Only 10 pieces sit at "
          "partial enhance (+3/+6/+9) — you've maxed your meaningful gear, so "
          "this is mostly a keep/feed call. Highest early-substat spares "
          "(best enhance candidates):", "",
          "| cur WSS | gear | set | main | rank |", "|--:|---|---|---|---|"]
    for r in sorted(unenh, key=lambda r: -r["wss"])[:12]:
        L.append(f"| {r['wss']:.1f} | {r['gear']} | {r['set'].replace('Set','')} | "
                 f"{r['main']} | {r['rank']} |")
    L += ["", f"_Reference: {len([r for r in unenh if r['wss'] < 12])} of the {len(unenh)} "
          "spare +0 epics have very low starting substats — fodder/sell candidates._", ""]

    (ANALYSIS / "gear_report.md").write_text("\n".join(L) + "\n")
    return pending


# ---------------------------------------------------------------------------
# (c) per built hero: WSS + meta set alignment
# ---------------------------------------------------------------------------

def hero_builds(d: Data) -> list[dict]:
    built = [h for h in d.heroes if h.get("equipment") and len(h["equipment"]) == 6]
    out = []
    for h in built:
        eq = list(h["equipment"].values())
        total = sum(d.reforge_wss(it) for it in eq)
        base = d.hero_base(h["name"])
        total_hero = sum(d.reforge_wss(it, base) for it in eq) if base else None
        sets = active_sets(eq)
        meta = d.meta_for(h["name"])
        rec = {
            "name": h["name"], "spd": h.get("spd"), "cr": h.get("cr"),
            "cd": h.get("cd"), "eff": h.get("eff"), "res": h.get("res"),
            "cp": h.get("cp"),
            "total_wss": round(total, 1),
            "sets": [CODE_TO_NAME.get(c, c) for c in sets],
            "set_codes": sets,
            "meta_source": meta["source"] if meta else None,
        }
        if meta:
            m = meta["record"]
            rec["meta_wr"] = m.get("derived", {}).get("win_rate")
            rec["meta_games"] = m.get("sample_size")
            top_build = (m.get("top_builds") or [{}])[0]
            rec["meta_top_build"] = top_build.get("set_agg_code")
            rec["meta_top_sets"] = [s.get("set_code") for s in (m.get("top_sets") or [])[:3]]
            # alignment: is my set combo the meta's most-used?
            mine = set(sets)
            metab = set((top_build.get("set_agg_code") or "").split("+")) - {""}
            rec["set_aligned"] = bool(metab) and mine == metab
        out.append(rec)
    return out


def hero_builds_report(builds: list[dict]) -> None:
    L = ["# Hero build report (56 built heroes)", "",
         "Per hero: total **reforge-projected WSS** across 6 pieces, active set "
         "bonuses, and alignment vs the RTA meta's most-used build. "
         "**No numeric stat targets** (speed/crit) are available yet — the T0 "
         "`recommend_equip` table isn't normalized and epic7db rank-targets are "
         "deferred (KNOWN UNKNOWNS), so 'gap' here means set/artifact-vs-meta, "
         "not stat-vs-target. Artifact alignment is unavailable (the export "
         "doesn't record equipped artifacts).",
         "",
         "| Hero | WSS | Spd | CR | CD | My sets | Meta build | Aligned | Meta WR (games) |",
         "|---|--:|--:|--:|--:|---|---|:-:|---|"]
    for r in sorted(builds, key=lambda r: -r["total_wss"]):
        meta_build = "+".join(CODE_TO_NAME.get(c, c) for c in
                              (r.get("meta_top_build") or "").split("+") if c) or "—"
        wr = f"{r['meta_wr']*100:.1f}% ({fmt_int(r['meta_games'])})" if r.get("meta_wr") else "—"
        aligned = "✓" if r.get("set_aligned") else ("·" if r.get("meta_source") else "—")
        src = "" if r.get("meta_source") in (None, "current") else " ᶠ"  # ss20f fallback
        L.append(f"| {r['name']}{src} | {r['total_wss']:.0f} | {r['spd']} | {r['cr']} | "
                 f"{r['cd']} | {'+'.join(r['sets']) or '—'} | {meta_build} | {aligned} | {wr} |")
    L += ["", "_ᶠ = meta from frozen ss20f snapshot (hero thin/absent in current "
          "Fall season). ✓ = your active sets match the meta's most-used build; "
          "· = meta exists but your sets differ; — = no RTA meta for this hero._", ""]
    (ANALYSIS / "hero_builds.md").write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------------------
# (d) priority lists
# ---------------------------------------------------------------------------

def priority_report(d: Data, builds: list[dict]) -> None:
    role_of = {h["name"]: h.get("role") for h in d.heroes}
    for b in builds:
        b["role"] = role_of.get(b["name"])

    L = ["# Hero readiness & priority", "",
         "Owner priority (CLAUDE.md ROSTER GOALS, 2026-08-12): **all-mode "
         "readiness with PvE co-equal — NOT RTA-first.** So this is organized "
         "as *mode-coverage readiness* (are the right roles well-geared?), not "
         "an RTA win-rate ladder.", "",
         "> **Data caveat, stated plainly:** the repo's only large-sample "
         "numeric data is RTA. Hunt / Abyss / Tower / GW-defense comps and "
         "stat thresholds are **not in the repo yet (session 6)**. So the "
         "PvE-weighted priority you actually want is *blocked on session 6*; "
         "below, PvE/GW readiness is provisional (role + gear), and only the "
         "RTA column is data-backed.", ""]

    # --- Readiness by role (the all-mode spine) ---
    L += ["## 1. Readiness by role (your all-mode spine)", "",
          "Your best-geared built heroes in each role. Good mode coverage means "
          "each role has options; thin roles are where new investment pays off "
          "across *every* mode.", ""]
    by_role = defaultdict(list)
    for b in builds:
        by_role[b["role"] or "unknown"].append(b)
    for role in sorted(by_role, key=lambda r: -len(by_role[r])):
        hs = sorted(by_role[role], key=lambda b: -b["total_wss"])
        line = ", ".join(f"{b['name']} ({b['total_wss']:.0f})" for b in hs[:6])
        more = f" +{len(hs)-6} more" if len(hs) > 6 else ""
        L.append(f"- **{role}** ({len(hs)} built): {line}{more}")
    L += ["", "_Number in parens = total reforge-projected WSS (gear quality). "
          "Role labels are from the Fribbels export._", ""]

    # --- Actionable fixes (data-backed, mode-agnostic) ---
    L += ["## 2. Highest-value fixes (act on these regardless of mode)", "",
          "These come straight from the gear data and help in *every* mode:", ""]
    no_set = [b for b in builds if not b["sets"]]
    if no_set:
        L.append(f"- **No active set bonus** ({len(no_set)}): "
                 + ", ".join(f"{b['name']}" for b in sorted(no_set, key=lambda b:-b['total_wss']))
                 + ". These waste their substats — re-slot into a real set (see "
                 "the allocator). Biggest loss: your best-geared piece is often here.")
    mismatched = [b for b in builds if b.get("meta_source") and b.get("set_aligned") is False
                  and b.get("meta_top_build")]
    if mismatched:
        L.append(f"- **Set differs from RTA meta** ({len(mismatched)}), for the "
                 "heroes where we *have* RTA data — worth a look for PvP:")
        for b in sorted(mismatched, key=lambda b:-(b.get('meta_wr') or 0))[:8]:
            mb = "+".join(CODE_TO_NAME.get(c,c) for c in (b.get('meta_top_build') or '').split('+') if c)
            L.append(f"    - {b['name']}: you run {'+'.join(b['sets']) or 'no set'} · "
                     f"meta {mb} ({b['meta_wr']*100:.0f}% WR)")
    L.append("- **Reforge-pending**: 438 lv85 pieces gain WSS from a free reforge "
             "(see gear_report.md) — cheapest upgrade across all modes.")
    L.append("")

    # --- Per-mode ---
    L += ["## 3. Per-mode readiness", "",
          "### RTA (data-backed)",
          "Built heroes present in the RTA meta, with your set alignment:", "",
          "| Hero | RTA WR | Games | Your sets | Meta build | Aligned |",
          "|---|--:|--:|---|---|:-:|"]
    metaed = sorted([b for b in builds if b.get("meta_wr")],
                    key=lambda b: -(b["meta_wr"] or 0))
    for b in metaed:
        mb = "+".join(CODE_TO_NAME.get(c, c) for c in
                      (b.get("meta_top_build") or "").split("+") if c) or "—"
        L.append(f"| {b['name']} | {b['meta_wr']*100:.1f}% | {fmt_int(b['meta_games'])} | "
                 f"{'+'.join(b['sets']) or 'no set'} | {mb} | {'✓' if b.get('set_aligned') else '·'} |")
    L += ["", f"_Only {len(metaed)} of your 56 built heroes are in the RTA meta; "
          "the rest are older/PvE-oriented and can't be ranked on PvP data._", ""]

    L += ["### Arena / Guild War offense",
          "Overlaps RTA heavily; use the RTA table as the working proxy until a "
          "dedicated arena-defense / GW sample is added. **Not separately "
          "data-backed.**", "",
          "### PvE (hunts, Abyss, Tower, seasonal) — PROVISIONAL",
          "**No PvE comp/threshold data in the repo yet — session 6.** Until "
          "then this is only 'who is well-geared, by role' (section 1), which is "
          "necessary but not sufficient: PvE wants *specific* units hitting "
          "*specific* speed/bulk breakpoints per boss. Do not treat section 1 as "
          "a PvE tier list.", "",
          "---", "",
          "### What actually moves your stated priority forward",
          "1. **Run session 6 next** — it builds the hunt/Abyss/Tower/GW comp "
          "library with per-slot stat thresholds. That is the missing input for "
          "a real PvE-weighted priority; everything else here is method waiting "
          "on that data.",
          "2. Meanwhile, the section-2 fixes (no-set builds, reforge-pending) "
          "help in every mode and need no new data.",
          "3. Optional T0 upgrade: normalize the datamine `recommend_equip` "
          "table (local re-run) for per-hero recommended sets/artifacts/stat "
          "weights — usable for PvE too, not just RTA.", ""]
    (ANALYSIS / "priority.md").write_text("\n".join(L) + "\n")


def main():
    d = load()
    rows = score_all(d)
    gear_report(d, rows)
    builds = hero_builds(d)
    hero_builds_report(builds)
    priority_report(d, builds)
    print(f"wrote analysis/: gear_scores.json, gear_report.md, "
          f"hero_builds.md, priority.md ({len(rows)} pieces, {len(builds)} built heroes)")


if __name__ == "__main__":
    main()
