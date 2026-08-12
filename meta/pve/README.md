# meta/pve — PvE comp library

Goal (session 6): a library of PvE clear comps — hunts (one-shot/auto),
Abyss, Tower, Guild-War offense/defense — as **team composition + per-slot
stat thresholds**, so analysis can answer "can my roster clear Wyvern 13 on
auto?".

## What's here now

- **`hunts.json`** — the **T0 datamine foundation**: every hunt and Chaos
  Gate season, its boss id, the gear sets it drops (with probabilities),
  stages, and reward material. Built by `scripts/build_pve_reference.py`
  from `datamine/items.json`. This is solid and reusable.

## What is deliberately empty (and why)

Each hunt/chaos entry has a `comps: []` field that is **not yet populated**.
Filling it needs two things the repo does not have yet:

1. **The comps themselves** (which heroes clear what, on auto/one-shot) —
   these are community knowledge, intended source **epic7db's guide
   library**. Per CLAUDE.md KNOWN UNKNOWNS, these must come from data, **not
   model memory**, so they are NOT invented here. Status: the epic7db guide
   structure was probed (see `pve-recon` workflow / CLAUDE.md site notes);
   harvesting is **deferred** until the guide/comp URLs are located and a
   parser is written (mirrors the epic7db rank-target deferral).
2. **Boss stat thresholds** (speed/bulk breakpoints) — the datamine we have
   normalized carries hunt *structure* but **no boss stat tables**, so
   datamine-derived thresholds are not available either. Cracking the boss
   stat source (or reading thresholds from validated guides) is required.

## comp schema (when populated)

```json
{
  "name": "Wyvern 13 auto",
  "content": "wyvern", "stage": "hunw013", "auto": true, "difficulty": 13,
  "team": [{"hero": "Furious", "role": "dps", "artifact": "..."},  ...],
  "per_slot_thresholds": {"Furious": {"spd": 180, "atk": 4500, "cr": 100}},
  "validated_against_datamine": true,
  "source_url": "...", "scraped_at": "..."
}
```

Every populated comp must carry `source_url` + `scraped_at` (CONVENTIONS)
and, where possible, be validated against datamine boss/skill data before
committing (flag mismatches rather than committing them).
