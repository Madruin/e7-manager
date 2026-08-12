---
name: e7-optimize
description: >-
  Answer optimization questions about the owner's Epic Seven account from the
  data in this repo — gear scoring, who-gets-this-piece, re-gear/allocation,
  hero build vs meta, weekly resource plan, hunt/PvE reference. Use whenever
  the user asks about their heroes, gear, what to enhance/farm/pull, or which
  hero to invest in. Reads collection/, datamine/, meta/, analysis/.
---

# e7-optimize

Toolchain for optimizing this single Epic Seven account. **Read CLAUDE.md
first** (gear math, trust tiers, ROSTER GOALS, KNOWN UNKNOWNS). Never invent
meta/PvE numbers from model memory — use the repo's data or say it's missing.

## Data map
- `collection/autosave-latest.json` — roster (239) + gear (1068), full roll history.
- `collection/inventory.json` — currencies, molagora, materials (owner-confirmed).
- `datamine/{heroes,skills,items,base_stats}.json` — T0 kits/items + T3 base stats.
- `meta/rta/` (current season) + `meta/rta_ss20f/` (robust snapshot) — RTA usage/WR/sets/artifacts.
- `meta/pve/hunts.json` — T0 hunt/chaos structure; `comps: []` awaits epic7db harvest.
- `analysis/` — generated reports (below).

## Regenerate everything
```
python scripts/analyze.py            # gear_scores.json, gear_report.md, hero_builds.md, priority.md
python scripts/plan_resources.py     # weekly_plan.md
python scripts/build_pve_reference.py# meta/pve/hunts.json
```
Re-run after any new `collection/` sync or `meta/` scrape.

## Common queries → how to answer
- **"Score my gear / best pieces"** → `analysis/gear_report.md` (WSS per CLAUDE.md gear math, reforge-projected).
- **"What should I reforge/enhance this week?"** → `analysis/weekly_plan.md` (reforge-pending list is the top lever).
- **"Give <hero> a better build" / "who gets this piece"** → `python scripts/allocate.py "<Hero Name>"` (uses current+spare gear, never steals from other built heroes; `--sets a,b` to force a set combo). Extend `allocate.py` for a specific-piece query.
- **"How is <hero> built vs meta?"** → `analysis/hero_builds.md` (set alignment; RTA-only, no stat targets — see caveat).
- **"Who should I invest in?"** → `analysis/priority.md` (role-coverage readiness; all-mode, PvE co-equal per ROSTER GOALS; RTA is the only data-backed column).
- **"What drops from <hunt>?"** → `meta/pve/hunts.json`.

## Honesty guardrails (do not cross)
- No numeric stat targets exist yet (recommend_equip not normalized, epic7db rank-targets deferred) — "gap" = set-vs-meta, not stat-vs-target.
- PvE comps (`meta/pve/*.comps`) are empty pending the epic7db guide harvest — do not fill them from memory.
- The library (`scripts/e7lib.py`) is the single source of WSS/base-stat logic; reuse it, don't re-derive.
