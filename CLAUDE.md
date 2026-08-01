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

**Dead, do not use:** EpicSevenDB (closed Jan 2023), gamepress.

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
  the % of the relevant base stat it represents, using datamined base stats,
  then weight as a % stat)

Mechanics that analysis code must model:

- Substat rolls occur every 3 enhancement levels (+3/+6/+9/+12/+15).
- Lv85+ reforge: reforge gains scale with how many rolls each substat
  received — reforge-projected score ≠ current score.
- Modification gems replace one substat (so a piece's worst substat is
  partially recoverable; factor into keep/sell and EV decisions).

## KNOWN UNKNOWNS

Resolve these **from data (datamine, official site, scrapes), never from model
memory** — model knowledge here is stale or absent:

- Current hunt drop tables post-renewal.
- The **Weakened** and **Fevor** gear sets (added ~June 2026) — effects,
  piece counts, where they drop.
- Current Warfare Rules.
- Anything numeric about the live meta (usage, win rates, stat targets).

## ROSTER GOALS

<!-- TODO(owner): fill in priority heroes and content targets
     (RTA rank goal, hunt auto-teams, Abyss/Tower push, guild war core, etc.).
     Analysis sessions (5+) read this section to decide who gets gear. -->

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
  discovery (fetches the page + JS bundles, extracts candidate API URLs) so
  endpoint knowledge comes from the live site, not model memory.

### Site-specific scrape status

- **epic7rtastats.com**: pending first successful run (see above). The
  scraper refuses to emit hero files until the endpoint response validates,
  so `meta/rta/` never contains fabricated data.
- **epic7db.com** rank-targets stretch scraper: deferred until
  `scrape_rta_stats.py` has one verified live run (gate set in the session-1
  brief).
