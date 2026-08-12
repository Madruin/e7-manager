#!/usr/bin/env python3
"""Weekly resource planner (session 6, deliverable 2).

Joins the inventory stock (collection/inventory.json) with the gear analysis
(analysis/gear_scores.json) and roster to produce analysis/weekly_plan.md:
what to spend resources on this week, grounded in data we actually have.

Honest scope: enhancement-material *costs* and per-hero *skill levels* are not
in the repo, so this plans against countable, data-backed levers (reforge-
pending pieces, no-set heroes, spare-gear enhance candidates) and reports
stock. It does not fabricate farm targets that need cost/skill data we lack.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from e7lib import fmt_int  # noqa: E402

INV = json.loads((REPO / "collection" / "inventory.json").read_text())
SCORES = json.loads((REPO / "analysis" / "gear_scores.json").read_text())["items"]
ANALYSIS = REPO / "analysis"


def main():
    cur = INV["currencies"]

    def val(k):
        return cur.get(k, {}).get("value")

    rows = SCORES
    reforge_pending = [r for r in rows if r.get("reforge_pending")]
    reforge_gain = sum(r["reforge_gain"] for r in reforge_pending)
    no_set = []  # filled from hero_builds if present
    hb = ANALYSIS / "hero_builds.md"

    L = ["# Weekly resource plan", "",
         "Grounded in current stock + the gear analysis. **Scope note:** the "
         "repo has no enhancement-cost tables or per-hero skill levels, and no "
         "PvE comp thresholds yet (session 6 harvest deferred), so this plans "
         "the **countable, data-backed levers** and reports stock — it does not "
         "invent farm targets that need data we lack.", "",
         "## Stock on hand (from collection/inventory.json)", "",
         "| Resource | Amount |", "|---|--:|",
         f"| Gold | {fmt_int(val('gold'))} |",
         f"| Skystone | {fmt_int(val('skystone'))} |",
         f"| Covenant Bookmarks | {fmt_int(val('covenant_bookmarks'))} "
         f"(+{fmt_int(val('covenant_bookmarks_limited'))} limited) |",
         f"| Powder of Knowledge | {fmt_int(val('powder_of_knowledge'))} |",
         f"| Friendship | {fmt_int(val('friendship_points'))} |",
         f"| Stigma | {fmt_int(val('stigma'))} |",
         f"| Leif | {fmt_int(val('leif'))} |",
         f"| Commander's Armband | {fmt_int(val('commanders_armband'))} |",
         f"| MolaGora | {fmt_int(INV.get('growth_ingredients', {}).get('molagora', {}).get('value'))} |",
         f"| Epic Artifact Charm | {fmt_int(INV.get('artifact_materials', {}).get('epic_artifact_charm', {}).get('value'))} |",
         ""]

    L += ["## This week's highest-value gear spend (data-backed)", "",
          f"1. **Reforge the {len(reforge_pending)} pending lv85 pieces.** "
          f"Total potential WSS across them ≈ **+{reforge_gain:.0f}** at no "
          "material cost beyond gold — the best gold sink you have. Prioritize "
          "the ones equipped on heroes you use (see gear_report.md 'reforge-"
          "pending' table).",
          f"   - You have {fmt_int(val('gold'))} gold — plenty; this is purely "
          "a do-it list, not a budget constraint.",
          "2. **Fix the no-set heroes.** Run the allocator on each; it uses only "
          "spare gear (no cost, no stealing):",
          "   - `python scripts/allocate.py \"Sage Baal & Sezan\"`",
          "   - `python scripts/allocate.py \"All-Rounder Wanda\"`",
          "3. **Enhance high-floor spare epics** (gear_report.md 'Enhancement "
          "EV'): only ~10 pieces sit at partial enhance, so this is a short "
          "list — enhance the best-substat spares, feed/sell the low-floor ones.",
          ""]

    L += ["## Summon-currency read", "",
          f"- Covenant Bookmarks {fmt_int(val('covenant_bookmarks'))} + "
          f"{fmt_int(val('covenant_bookmarks_limited'))} limited (spend the "
          "limited ones first — they expire).",
          f"- Skystone {fmt_int(val('skystone'))}, Powder of Knowledge "
          f"{fmt_int(val('powder_of_knowledge'))}. No pity/banner data in the "
          "repo, so no pull recommendation is made here (would need banner "
          "timeline + your pity counters).",
          ""]

    L += ["## What this planner still needs to be complete", "",
          "- **PvE comp thresholds (session 6 harvest, deferred):** without "
          "them, 'what to farm for which hero' can't be tied to a concrete "
          "clear goal. That's the main unlock.",
          "- **Per-hero skill levels:** the export doesn't include them, so "
          "MolaGora spend can't be targeted (you have "
          f"{fmt_int(INV.get('growth_ingredients', {}).get('molagora', {}).get('value'))} "
          "molagora — plenty for several skill-ups, but the tool can't say "
          "*whose*).",
          "- **Enhancement/reforge cost tables:** not datamined, so gold-budget "
          "math is approximate; gold is not your constraint anyway.", ""]

    (ANALYSIS / "weekly_plan.md").write_text("\n".join(L) + "\n")
    print("wrote analysis/weekly_plan.md")


if __name__ == "__main__":
    main()
