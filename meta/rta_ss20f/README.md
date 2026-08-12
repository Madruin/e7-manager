# meta/rta_ss20f — pinned Pre-Season snapshot (frozen)

Frozen RTA meta from **`pvp_rta_ss20f`** (Pre-Season, Post Summer 2026), the
last completed season before the 2026-08-12 rollover to Fall 2026 (`ss21`).

**Why this exists:** right after a season rollover the live `meta/rta/`
(current season) has tiny samples. This folder keeps the previous season's
robust data (tens of thousands of games per hero) as a stable reference for
analysis until Fall 2026 accumulates enough games.

**Coverage caveat:** this snapshot is **only the heroes we had already
scraped during ss20f** (the sample set). Full-roster ss20f coverage is **not
recoverable** post-rollover — `epic7rtastats.com/heroes` only serves the
currently-displayed season, so `--all --season pvp_rta_ss20f` finds no rows.
If the site turns out to expose a past-season parameter (the one-shot
workflow probes for one; check its logs), full ss20f coverage could be
back-filled — otherwise treat this as the sample-hero reference only.

Numbers here are captured near season end (e.g. Notos 135k games), so they
are the most complete ss20f figures we hold. Do not overwrite — this is a
deliberate frozen snapshot, not a synced folder.
