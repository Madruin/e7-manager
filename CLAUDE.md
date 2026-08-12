# CLAUDE.md — e7-manager

Permanent project context. Read this before doing anything in this repo.

## PURPOSE

This repo is a data pipeline and analysis system for optimizing a single Epic
Seven account: it aggregates datamined game data, scraped meta statistics, and
the owner's exported collection into one place. Analysis tooling then answers
questions like "which hero gets this gear", "which piece is worth enhancing",
and "how far is my build from the meta target".

## DATA SOURCES

Trust tiers: **T0** = ground truth (datamine), **T1** = official, **T2** =
community aggregates (large-sample, but methodology varies), **T3** =
wiki/guides (human-curated, can be stale or opinionated). When sources
conflict, lower tier number wins.

| Source | URL | Provides | Tier | Refresh |
|---|---|---|---|---|
| EpicSevenAssetRipper | https://github.com/CeciliaBot/EpicSevenAssetRipper | Extracts hero kits, skill multipliers, items from the game client's `data.pack` | T0 | After balance patches |
| Official hero record | https://epic7.onstove.com/en/gg/herorecord | Official per-season/league hero stats | T1 | Daily |
| epic7rtastats | https://www.epic7rtastats.com | Per-hero/set/artifact RTA stats, draft explorer | T2 | Ongoing (scrape weekly) |
| e7rtabot | https://e7rtabot.com/stats | Champion+ build usage / win rates | T2 | Ongoing |
| epic7db | https://epic7db.com | Per-rank RTA stat targets (Master→Legend), guide library | T2/T3 | Ongoing |
| CeciliaBot site | https://ceciliabot.github.io | Banner timeline, hero/artifact DB | T3 | Ongoing |
| e7calc | https://e7calc.xyz | Damage calculator + skill multipliers | T3 | After balance patches |
| Fribbels E7 Optimizer | https://github.com/fribbels/Fribbels-Epic-7-Optimizer | `data/cache/herodata.json` → per-hero base stats (T0 substitute, see KNOWN UNKNOWNS); the app itself produces the gear export in `collection/` | T3 | Per game patch |

**Dead, do not use:** EpicSevenDB (closed Jan 2023), gamepress.

## DATAMINE

Verified working locally 2026-08-11 (session 2). The EpicSevenAssetRipper
route is **not** broken on the current pack format — no fallback to
CeciliaBot's published data was needed, so `datamine/*.json` is genuinely T0.

### Running it

Local desktop only — it reads the installed game client.

```
pip install pathvalidate                 # only third-party dependency
python scripts/rip_datamine.py           # data.pack -> datamine/raw/tables/*.json
python scripts/normalize_datamine.py     # -> datamine/{heroes,skills,items}.json
```

- `data.pack` lives at `C:\ProgramData\Smilegate\Games\EpicSeven\data.pack`
  (STOVE install; override with `--pack` or `$E7_PACK`). 7.3 GB, 89 552
  records. A full scan takes ~7 s; the whole pipeline runs in ~2 min.
- `scripts/rip_datamine.py` clones the ripper to `tools/EpicSevenAssetRipper`
  on first use (gitignored; override with `$E7_RIPPER`). Only `pathvalidate`
  is needed — the ripper's `app/` package is driven headlessly, its PyQt6 GUI
  is never imported.
- Useful flags: `--list REGEX` searches the pack file tree, `--extract-raw
  REGEX` dumps records verbatim, `--all-db` parses all ~950 `db/` tables
  instead of the curated list in `TABLES`.
- `datamine/raw/manifest.json` records provenance for every run: pack path,
  size, mtime, per-partition data versions, ripper commit, and the row/column
  count of each table (plus anything that failed). The normalized files copy
  that into their `source` block.

### Pack format (reverse-engineered locally, session 2)

Two encryption layers, documented in `scripts/e7pack.py`:

1. `data.pack` is a `PLPcK` container XOR-encrypted with a 128-byte key at
   absolute file offset. The ripper handles this layer and the record scan.
2. Each extracted `.db` payload is a **second** `PLPcK` container, XOR'd with
   a **different 256-byte key at a per-file rotation**. The ripper does *not*
   decode this. The key was recovered from the live pack (not from any
   published source): `db/level_enter_drops.db` decrypts to ~61 % NUL bytes,
   so the per-residue modal ciphertext byte over its key-length blocks is the
   key. Every other table then decrypts at some rotation 0–255, recovered from
   the known 5-byte `PLPcK` magic and **confirmed against the container's
   trailing footer** before any data is returned — a key or format change
   fails loudly instead of yielding garbage.

Inside a decrypted container: header, an offset hash table, then back-to-back
nodes (`u32 total | u8 tag=2 | u8 key_len | u32 val_len | u8 pad | u32 ptr |
key | value`), then a footer. Tables are rebuilt from four key shapes —
`\x09cols`, `\x09rows`, `\x09<i>` (column name), `\x09\x09<i>` (row id) — with
the row's own node holding its column values NUL-joined.

English strings live in `text/en/text.db` (140 958 rows); every `*_nm`,
`*_name`, `*_de`, `chrn_*`, `sk_*_sknm` key in the tables resolves there.

### Tables worth knowing

| Table | Holds |
|---|---|
| `db/character_player*.db` | roster (3 files: base, grade2, grade3) |
| `db/skill_player*.db`, `db/sklv.db` | skills and per-skill-level scaling |
| `db/equip_item.db` | gear, artifacts, exclusive equipment |
| `db/equip_stat.db` | main/substat value ranges (`val_min`/`val_max`) |
| `db/item_set.db`, `db/item_set_rate.db` | gear sets; per-content drop pools |
| `db/level_enter_drops.db` | every stage's drops (10 716 rows) |
| `db/level_battlemenu_hunt.db`, `..._chaosgate.db` | hunt / Chaos Gate config |
| `db/recommend_equip.db` | per-hero recommended sets, artifacts, stat weights |
| `db/item_material.db` | catalysts, runes, charms, gems, reforge mats |
| `db/cs_player.db` | condition states (buffs/debuffs), *not* character stats |

### Coverage (measured 2026-08-11)

**907 of 926** `db/` tables (story scripts excluded) parse with the code
above; all 20 curated tables in `rip_datamine.py`'s `TABLES` are in that set.
The 19 that don't fall into two groups, neither of which blocks anything so
far:

- **12 tiny stubs** (57–535 B) with no valid key rotation — `cs.db`,
  `skill.db`, `character.db`, `skillset.db`, `level_enter.db`,
  `level_stage_2_data.db`, `support_unit.db`, `support_unit_stat.db`,
  `background.db`, `background_flip.db`, `tile_sub_event.db`,
  `tile_sub_action.db`. Each has a much larger sibling that does parse
  (`cs_player.db`, `skill_player.db`, `level_stage_1_info.db`, …), so these
  look like stubs or shard indexes rather than data.
- **7 tables whose row-id nodes carry binary keys** (`\x1bk\x00\x00…`)
  instead of string ids, so the row lookup misses — `pvp_npcbattle.db`,
  `pvp_npcbattle_team.db` (224 KB), `tile_sub_object_data.db`,
  `tile_sub_mission.db`, `level_chapter_starmig.db`, `character_recall.db`,
  `equip_item_undress.db`. A second row-key encoding is the likely cause;
  worth revisiting only if one of these tables is actually needed.

Also not decoded: `pass/public.pass` (Lua bundle — `formula.lua`,
`battle_logic_stat.lua`; a different encryption scheme than the `.db` layer).
That is what blocks hero base stats, see KNOWN UNKNOWNS.

## COLLECTION FORMATS

Placeholder. The Fribbels E7 Optimizer `autosave.json` schema gets documented
here **from a real exported file in session 3** — do not invent or assume it
from model memory. Until then, nothing in `collection/` has a defined schema
except `collection/screenshots/` (raw images, `YYYY-MM-DD/` subfolders).

## GEAR MATH

Substat weighting (WSS — weighted substat score):

- Speed ×2
- Crit Chance ×1.6
- Crit Damage ×8/7
- % stats (Atk%/Def%/HP%/Eff/ER) ×1
- Flat stats normalized against their % equivalents (convert a flat roll to
  the % of the relevant base stat it represents, then weight as a % stat).
  **Unblocked as of 2026-08-12, with a tier downgrade** — use
  `datamine/base_stats.json` (`heroes[<id>].lv60_6star_awakened`), which is
  **T3**, not T0: see KNOWN UNKNOWNS. Per-roll `val_min`/`val_max` ranges for
  every main/substat are in `datamine/items.json` → `stat_scales`.

Stat vocabulary is shared across `datamine/*.json` and comes from the T0
tables: `att`, `max_hp`, `def`, `speed`, `cri`, `cri_dmg`, `acc`, `res`,
`coop` (and the `*_rate` percentage forms). `base_stats.json` renames its
upstream keys into this vocabulary and records the mapping in its own
`source.key_mapping`.

Mechanics that analysis code must model:

- Substat rolls occur every 3 enhancement levels (+3/+6/+9/+12/+15).
- Lv85+ reforge: reforge gains scale with how many rolls each substat
  received — reforge-projected score ≠ current score.
- Modification gems replace one substat (so a piece's worst substat is
  partially recoverable; factor into keep/sell and EV decisions).

## KNOWN UNKNOWNS

Resolve these **from data (datamine, official site, scrapes), never from model
memory** — model knowledge here is stale or absent:

- Anything numeric about the live meta (usage, win rates, stat targets).
- **The T0 base-stat formula.** `character_player.db` stores only the
  personality seeds (`bra`/`int`/`fai`/`des`) plus class, rarity and the
  `*_rate` multipliers; the client derives Atk/HP/Def/Spd from those at
  runtime via `formula.lua` inside `pack:pass/public.pass`, which uses a
  *different* encryption scheme than the `.db` layer and is still not decoded.
  **Worked around, not solved** — see the T3 substitute below. Cracking
  `public.pass` would upgrade `base_stats.json` back to T0 and is the only
  reason to revisit this.
- The per-season **Warfare Rule list**. The mechanic is resolved (below), but
  the individual rules in effect are server-driven and are not in the client
  tables that were searched.

### Worked around 2026-08-12 (session 3, T0 → T3 downgrade)

- **Hero base stats** now live in `datamine/base_stats.json`, built by
  `scripts/fetch_base_stats.py` from the Fribbels E7 Optimizer's bundled
  `data/cache/herodata.json` (the data the optimizer itself optimizes
  against; its maintainers refresh it per game patch). **This is T3, not
  T0** — treat it as authoritative only until `formula.lua` is decoded, and
  re-run the fetch after each game patch.
  - Coverage: **447 of 456** roster heroes. The 9 gaps are 4 alternate
    Mercedes story forms (Mercedes herself is covered via `c0002`) and the
    5 Lefundos 2★ story mages, none of which upstream carries.
  - Upstream lags our pack by roughly one patch (herodata was at
    `patch 20260716` when the 2026-08-11 pack was ripped), so a brand-new
    hero can be missing or stale. `unmatched_heroes` in the file lists who.
  - **Verify before trusting.** `scripts/crosscheck_base_stats.py` re-checks
    a sample against epic7db, an independent source. Result on
    2026-08-12: 4/5 exact on all four stats (Ras, Vildred, Arbiter Vildred,
    Harsetti); **Belian mismatched on Speed — ours 110, epic7db 106**, other
    three stats agree. Unresolved: one of the two sources is stale. Confirm
    in-game before relying on Belian's speed.

### Resolved 2026-08-11 (session 2 datamine, T0 — see DATAMINE section)

- **Hunt drop tables, post-renewal.** Five hunts remain, each with four
  stages (`<key>009`, `011`, `013`, `101`) — `db/level_battlemenu_hunt.db`
  plus `db/level_enter_drops.db`. Gear-set pool per hunt (uniform over the
  rows `db/item_set_rate.db` lists, so equal probability):
  - Wyvern (`hunw`): Hit / Critical / Speed — 1/3 each
  - Golem (`hung`): Attack / Defense / Health / Protection — 1/4 each
  - Banshee (`hunb`): Counter / Destruction / Resist / Lifesteal — 1/4 each
  - Azimanak (`hunq`): Unity / Immunity / Rage — 1/3 each
  - Caides (`hund`): Penetration / Revenge / Injury / Torrent — 1/4 each
  Full per-stage drops (gear ids, materials, counts) are in
  `datamine/items.json` → `hunts[].stages`.
- **"Weakened" and "Fevor" sets.** Their real English names are
  **Weakening Set** (`set_weak`) and **Fervor Set** (`set_might`).
  - Weakening Set — **4-piece**: Speed +15%, and +15% chance to inflict
    debuffs.
  - Fervor Set — **2-piece**: at the start of an extra turn, increases the
    damage of the next attack by 20%. Does not stack with other sets of the
    same name.
  - Source: **Chaos Gate**, season 3 (`chaosgate_ss3`, "Remnant of
    Supremacy") — pool `set_chaosgate3` = {Weakening, Fervor}. Chaos Gate
    seasons 1 and 2 drop Reversal/Riposte and Pursuit/Warfare respectively.
    They do **not** drop from any hunt.
- **What "Warfare Rules" are.** An RTA (World Arena) mechanic, not a gear
  mechanic — distinct from the Warfare *Set* (`set_opener`). Client text
  (`help_inforta_13_1_desc`, `pvp_rta_opening_rule_*`): a random set of
  special rules is selected per match, revealed before the pre-ban phase,
  inspectable during ban/pick and in combat, and applied only in ranked
  matches at **Champion league or higher**. The season's full rule list is
  shown in the World Arena lobby (server-driven).

## ROSTER GOALS

Owner's framing (2026-08-11): specific hero priorities are **deliberately
premature** until the collection is imported. The primary goal is:

> Develop a comprehensive list of my heroes, gear, and resources, and have
> up-to-date resources connected to that data which allow me to optimize my
> characters and actions in Epic Seven across all game modes — particularly
> hunt, guild wars, arena, and RTA, as well as difficult seasonal events.

Implications for analysis sessions until specific heroes are listed here:

- Optimize for **mode coverage** (hunt, GW, arena, RTA, seasonal), not for
  a named-hero shortlist.
- After session 3 (collection import), propose a concrete priority list
  from the actual roster + meta data, and ask the owner to confirm it —
  then record the confirmed list in this section.

<!-- TODO(owner, after session 3): confirm priority heroes + content
     targets (RTA rank goal, hunt auto-teams, GW core, etc.). -->

## CONVENTIONS

- JSON: `snake_case` keys.
- `meta/rta/`: one file per hero, named by slug. Slug = lowercase hero name,
  non-alphanumeric runs collapsed to `-` (e.g. `perfumer-byblis.json`).
- Every scraped file carries `source_url` and `scraped_at` (UTC ISO 8601)
  fields. Merged files carry them per top-level section.
- Commit prefixes: `[scrape]` / `[datamine]` / `[collection]` / `[analysis]`.
- Scrapers: descriptive User-Agent, ≥1s between requests, raw responses
  cached in `scripts/.cache/` (gitignored). Never write output fields the
  source didn't provide.

## OPERATIONAL NOTES

### Cloud session network access (observed 2026-08-01)

The Claude Code cloud environment's egress policy **blocks every game-data
host** at the proxy — this is a session-side policy denial, not the sites
blocking datacenter IPs. Exact failure, identical for all of the following:
`curl: (56) CONNECT tunnel failed, response 403` (agent proxy log:
`connect_rejected — gateway answered 403 to CONNECT (policy denial)`).
Blocked: `www.epic7rtastats.com`, `epic7db.com`, `e7rtabot.com`,
`epic7.onstove.com`, `ceciliabot.github.io`. Reachable: `github.com`,
`api.github.com`, `raw.githubusercontent.com`.

Consequences:

- Scrapers must run **locally** or **via GitHub Actions** (Actions runners
  have open egress; see `.github/workflows/meta-sync.yml`, which also has a
  `workflow_dispatch` trigger for on-demand runs). Cloud sessions iterate on
  scraper code by dispatching the workflow and reading its logs.
- Whether the target sites additionally block datacenter/Actions IPs is
  recorded below per site once observed — if a site blocks Actions runners
  too, that scraper is local-only.
- `scripts/scrape_rta_stats.py --discover` performs runtime endpoint
  discovery (fetches the page + JS bundles, extracts candidate API URLs,
  analyzes RSC flight payloads or raw HTML) so endpoint knowledge comes
  from the live site, not model memory. `E7_SCRAPER_BASE=<url>` points
  discovery at another site for recon.
- More cloud-session gotchas observed 2026-08-01: raw `curl` to
  `api.github.com` is intercepted (use the GitHub MCP tools instead); the
  session's GitHub token cannot `workflow_dispatch` (403) — trigger CI by
  pushing to a branch with a push-trigger workflow; Actions artifact
  downloads live on `*.blob.core.windows.net`, which the egress policy
  also blocks, so get data out of CI via logs or by having CI commit it.

### Site-specific scrape status

- **epic7rtastats.com** (verified live 2026-08-01, via Actions runners —
  no datacenter-IP block observed): Next.js App Router site with **no
  public JSON API** — `/api/...` probes 404 and the client bundles contain
  no fetch URLs. Data ships inside each page's RSC flight payload
  (`self.__next_f.push` chunks) as flat JSON objects, which is what
  `scrape_rta_stats.py` extracts (embedded JSON, not rendered-HTML
  parsing). Key routes: `/heroes` (hero index + current-season per-hero
  aggregates: total_games/wins/losses/bans/prebans), `/heroes/{hero_code}`
  (setStats, artifact stats, buildStats, usage denominators, season
  metadata incl. the source's own `last_updated`). The numeric-id and slug
  route variants return empty shells — always use the `cXXXX` hero code.
  Semantics note: `total_games` ≈ wins + losses + prebans for low-preban
  heroes but not in general — treat counts as source-verbatim and only
  trust the derived formulas stated inside each output file.
  The scraper validates every record before writing, so `meta/rta/` never
  contains fabricated data.
- **epic7db.com** rank-targets stretch scraper: **deferred** after recon
  2026-08-01. Findings: reachable from Actions runners; server-rendered
  HTML (no RSC/Next payload, no JSON API surfaced). Hero list at `/heroes`
  (654 KB; `<li class="hero" data-name=... data-element=... data-stars=...>`),
  hero pages at `/heroes/{kebab-slug}` with base stats + a recommended
  build-stats block (`cm_icon_stat_*` icons) — but **no per-rank
  Master→Legend breakdown found on hero detail pages** (zero
  "Master"/"Legend" text hits), so where epic7db keeps its per-rank RTA
  stat targets is still unlocated. Also: new heroes lag — `/heroes/aube`
  404s while Harsetti exists. Next attempt should recon their nav/guide
  URLs for an RTA-builds section before writing any parser. Re-run recon:
  `E7_SCRAPER_BASE=https://epic7db.com python scripts/scrape_rta_stats.py
  --discover --page /heroes/<slug>` (works from Actions or locally, not
  from cloud sessions).
