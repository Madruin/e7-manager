# Weekly resource plan

Grounded in current stock + the gear analysis. **Scope note:** the repo has no enhancement-cost tables or per-hero skill levels, and no PvE comp thresholds yet (session 6 harvest deferred), so this plans the **countable, data-backed levers** and reports stock — it does not invent farm targets that need data we lack.

## Stock on hand (from collection/inventory.json)

| Resource | Amount |
|---|--:|
| Gold | 758,891,697 |
| Skystone | 4,347 |
| Covenant Bookmarks | 217 (+230 limited) |
| Powder of Knowledge | 1,125 |
| Friendship | 383,113 |
| Stigma | 845,419 |
| Leif | 1,286 |
| Commander's Armband | 515 |
| MolaGora | 705 |
| Epic Artifact Charm | 12 |

## This week's highest-value gear spend (data-backed)

1. **Reforge the 438 pending lv85 pieces.** Total potential WSS across them ≈ **+2327** at no material cost beyond gold — the best gold sink you have. Prioritize the ones equipped on heroes you use (see gear_report.md 'reforge-pending' table).
   - You have 758,891,697 gold — plenty; this is purely a do-it list, not a budget constraint.
2. **Fix the no-set heroes.** Run the allocator on each; it uses only spare gear (no cost, no stealing):
   - `python scripts/allocate.py "Sage Baal & Sezan"`
   - `python scripts/allocate.py "All-Rounder Wanda"`
3. **Enhance high-floor spare epics** (gear_report.md 'Enhancement EV'): only ~10 pieces sit at partial enhance, so this is a short list — enhance the best-substat spares, feed/sell the low-floor ones.

## Summon-currency read

- Covenant Bookmarks 217 + 230 limited (spend the limited ones first — they expire).
- Skystone 4,347, Powder of Knowledge 1,125. No pity/banner data in the repo, so no pull recommendation is made here (would need banner timeline + your pity counters).

## What this planner still needs to be complete

- **PvE comp thresholds (session 6 harvest, deferred):** without them, 'what to farm for which hero' can't be tied to a concrete clear goal. That's the main unlock.
- **Per-hero skill levels:** the export doesn't include them, so MolaGora spend can't be targeted (you have 705 molagora — plenty for several skill-ups, but the tool can't say *whose*).
- **Enhancement/reforge cost tables:** not datamined, so gold-budget math is approximate; gold is not your constraint anyway.

