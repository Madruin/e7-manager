# ROADMAP

Sessions 2–6, each as a ready-to-paste kickoff prompt. Session 1 (scaffold +
docs + first scraper) and session 2 (datamine) are done — see git history and
CLAUDE.md's DATAMINE section. Paste the fenced block for the session you're
starting; the LOCAL/cloud tag tells you where to run it.

---

## Session 2 — Datamine feasibility gate — DONE 2026-08-11 (LOCAL desktop CLI)

Ripper worked on the current pack format; no fallback needed, output is T0.
Re-run with `python scripts/rip_datamine.py && python scripts/normalize_datamine.py`.

```text
This is session 2 of e7-manager (read CLAUDE.md first): the datamine
feasibility gate. Run this on my desktop — it needs the game client.

1. Clone https://github.com/CeciliaBot/EpicSevenAssetRipper.
2. Prerequisite: the official Epic Seven PC client, installed via the STOVE
   launcher (the same account links across mobile/PC). Run the game once so
   data.pack downloads, then close it.
3. Use the ripper to extract the hero, skill, and item tables from data.pack.
   Raw extraction output goes to datamine/raw/ (gitignored).
4. Write scripts/normalize_datamine.py that converts the raw extraction into
   normalized, small JSON: datamine/heroes.json, datamine/skills.json,
   datamine/items.json (snake_case keys, per CLAUDE.md conventions).
5. Commit the normalized output only ([datamine] prefix); raw stays
   gitignored.
6. While you're in the raw data: resolve what you can of CLAUDE.md's KNOWN
   UNKNOWNS (Weakened/Fevor set effects, hunt drop tables if present) and
   update that section.

FALLBACK if the ripper is broken on the current pack format: pull kit data
from CeciliaBot's published data instead (their E7Tools / E7Assets repos on
GitHub), normalize that into the same three files, and document the
substitution (source, tier downgrade T0→T3, date) in CLAUDE.md.
```

---

## Session 3 — Gear export via Fribbels optimizer (LOCAL desktop CLI)

```text
This is session 3 of e7-manager (read CLAUDE.md first): getting my real gear
and hero collection into the repo. Run on my desktop.

0. First, close the base-stats gap left by session 2 (see KNOWN UNKNOWNS):
   produce datamine/base_stats.json with per-hero base Atk/HP/Def/Spd (and
   crit/eff/res if the source has them), keyed by our cXXXX hero ids.
   Candidate sources, in order — discover the actual file layout from the
   live source, never from memory:
   a. The Fribbels optimizer's bundled/fetched hero data (it must carry base
      stats to optimize; you're installing it in step 1 anyway).
   b. CeciliaBot's published data (E7Tools / E7Assets repos or the
      ceciliabot.github.io data files).
   Record source_url + scraped_at + an explicit tier note (T3 substitute for
   the T0 formula.lua we couldn't decrypt), cross-check 2-3 heroes against
   the in-game stat screen (owner can confirm) and epic7db hero pages, then
   update CLAUDE.md's GEAR MATH + KNOWN UNKNOWNS to unblocked-with-downgrade.

1. Install Fribbels E7 Optimizer
   (https://github.com/fribbels/Fribbels-Epic-7-Optimizer) and Npcap — Npcap
   must be installed with the "support raw 802.11 traffic" option enabled.
2. Run the Epic Seven PC client and the optimizer together and perform the
   optimizer's gear/hero import (it sniffs the game's network traffic).
3. Write scripts/sync_collection.py that:
   - copies the optimizer's autosave.json from its save directory
     (Documents/FribbelsOptimizerSaves) into collection/ with a dated
     filename (e.g. collection/autosave-YYYY-MM-DD.json),
   - maintains a "latest" symlink (or copy on Windows) pointing at the
     newest export,
   - commits with the [collection] prefix.
4. Document the ACTUAL observed autosave.json schema in CLAUDE.md's
   COLLECTION FORMATS section — from the real file, not from memory or the
   optimizer's docs.
5. Sanity-check before committing: imported gear count and hero count must
   match what I see in-game (I'll confirm the numbers); flag any mismatch
   instead of committing bad data.
```

---

## Session 4 — Vision inventory (cloud, from phone)

```text
This is session 4 of e7-manager (read CLAUDE.md first): parsing my inventory
screenshots. I'm uploading screenshots of my inventory tabs — catalysts,
runes, charms, currencies, artifacts, molagora, bookmarks/pity counters,
sanctuary levels — taken today. Store them under
collection/screenshots/YYYY-MM-DD/ (today's date).

Parse them into collection/inventory.json:
- snake_case keys, organized by category matching the tabs above,
- every parsed number carries a confidence field ("high" / "medium" /
  "low"),
- anything below high confidence goes into a "needs_verification" list that
  you present to me for manual confirmation at the end — never silently
  trust a low-confidence read,
- include source_screenshot (path) per entry, plus a top-level scraped_at.

Commit with the [collection] prefix once I've confirmed the flagged values.
```

---

## Session 5 — Analysis core (cloud)

```text
This is session 5 of e7-manager (read CLAUDE.md first): the analysis core,
in analysis/. Inputs: the Fribbels export in collection/ (schema documented
in CLAUDE.md), collection/inventory.json, meta/rta/*.json, datamine/*.json,
and the ROSTER GOALS section of CLAUDE.md. Build, in order:

(a) Gear scorer over the Fribbels export using CLAUDE.md's GEAR MATH
    (WSS weights, flat-stat normalization against datamined base stats),
    including reforge-projected scores for lv85+ gear (reforge scales with
    per-substat roll counts).

(b) Enhancement EV: for each piece sitting at +3/+6/+9/+12, the expected
    score gain from its remaining rolls, ranked against the charm and gold
    stock recorded in collection/inventory.json — i.e. "what should I
    actually spend my enhancement resources on".

(c) Gap reports: for each hero in ROSTER GOALS, compare my built stats
    against the meta/rta targets for that hero; output per-hero gaps
    (missing speed, crit, etc.) and which gear slots are the bottleneck.

(d) Cross-hero allocation: assign gear to ROSTER GOALS heroes in priority
    order (sequential greedy first); leave hooks for a smarter global
    solver later.

(e) Hero prioritization (owner's directive 2026-08-12: "as much info and
    mode-specific context as available"). Since ROSTER GOALS is still
    mode-based, produce BOTH, from the actual roster (collection) + meta
    (meta/rta/ current + meta/rta_ss20f/ robust) + datamine:
    - a single cross-mode priority list (who to invest in next, and why),
      and
    - a per-mode list (hunt / guild war offense+defense / arena / RTA /
      hard seasonal), each with the mode-specific context that justifies it
      (e.g. for RTA: pick/ban/WR + which of my built heroes are already
      meta; for hunt: which of my heroes can hit known one-shot/auto
      thresholds). Flag where the current Fall season is too thin and fall
      back to meta/rta_ss20f/, saying so.
    Present both for my confirmation, then record the confirmed lists in
    CLAUDE.md's ROSTER GOALS so later sessions read them.

Output: committed reports (format your choice, [analysis] prefix) plus
reusable scripts — analysis will be re-run after every collection sync.
Note: ROSTER GOALS is intentionally mode-based right now; do NOT stop for
lack of a named-hero list — deliverable (e) produces it. Use the whole
built roster for scoring/EV; use meta + modes to rank.
```

---

## Session 6 — PvE comp library, resource planner, query skill (cloud)

```text
This is session 6 of e7-manager (read CLAUDE.md first). Three deliverables:

1. PvE comp library: harvest hunt one-shot/auto comps and endgame comps
   (Abyss, Tower, guild-war offense/defense cores) from epic7db's guide
   library into meta/pve/ — one file per comp, as team composition plus
   per-slot stat thresholds. Validate thresholds against datamine boss/skill
   data (e.g. required speed/bulk actually lines up with boss stats) and
   flag anything that doesn't check out rather than committing it. Files
   carry source_url + scraped_at per CLAUDE.md conventions.

2. Weekly resource planner: a report generator that allocates
   gold/stamina/charms/molagora/catalysts/bookmarks (stock from
   collection/inventory.json) against ROSTER GOALS — what to farm, what to
   enhance, what to buy this week. Commit the generator ([analysis] prefix)
   and the first report.

3. A skill file wrapping common queries ("who gets this piece", "what do I
   farm this week", "gap report for X") so future sessions don't re-derive
   the toolchain.
```
