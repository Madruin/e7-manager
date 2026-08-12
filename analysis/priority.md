# Hero investment priority

Two lists, per owner request: a cross-mode priority and per-mode lists. Built from your **56 fully-geared heroes**, the **RTA meta** (current Fall season + frozen ss20f snapshot), and gear quality (total reforge-projected WSS). 

**Data honesty:** our only large-sample numeric meta is RTA (epic7rtastats). Arena/GW-offense overlap RTA heavily and use it as a proxy. **Hunt and GW-defense have no comp/threshold data in the repo yet — that's session 6**; those lists below are provisional, from role + gear, and should not be treated as meta-backed.

## 1. Cross-mode priority (who to invest in next)

Ranked by RTA meta strength × your current gear investment. Heroes already at the top are your safest continued investments; strong-meta heroes with lower WSS are your best *upgrade* targets.

| # | Hero | Total WSS | RTA WR | Note |
|--:|---|--:|--:|---|
| 1 | Sage Baal & Sezan | 416 | 54.1% | meta-relevant, well-geared — maintain |
| 2 | Boss Arunka | 372 | 57.2% | meta-relevant, well-geared — maintain |
| 3 | Silvertide Christy | 376 | 53.1% | meta-relevant, well-geared — maintain |
| 4 | Mercedes | 405 | no RTA data | not in RTA meta; value is PvE/niche |
| 5 | All-Rounder Wanda | 403 | no RTA data | not in RTA meta; value is PvE/niche |
| 6 | Tenebria | 398 | no RTA data | not in RTA meta; value is PvE/niche |
| 7 | Champion Zerato | 394 | no RTA data | not in RTA meta; value is PvE/niche |
| 8 | Mediator Kawerik | 389 | no RTA data | not in RTA meta; value is PvE/niche |
| 9 | Elphelt | 388 | no RTA data | not in RTA meta; value is PvE/niche |
| 10 | Specter Tenebria | 386 | no RTA data | not in RTA meta; value is PvE/niche |
| 11 | Briar Witch Iseria | 388 | 49.7% | meta-relevant, well-geared — maintain |
| 12 | Kikirat v2 | 385 | no RTA data | not in RTA meta; value is PvE/niche |
| 13 | Blood Blade Karin | 385 | no RTA data | not in RTA meta; value is PvE/niche |
| 14 | Genesis Ras | 358 | 52.6% | meta-relevant, well-geared — maintain |
| 15 | Shuna | 382 | no RTA data | not in RTA meta; value is PvE/niche |
| 16 | Conqueror Lilias | 382 | no RTA data | not in RTA meta; value is PvE/niche |
| 17 | Ruele of Light | 359 | 52.3% | meta-relevant, well-geared — maintain |
| 18 | Basar | 381 | no RTA data | not in RTA meta; value is PvE/niche |
| 19 | Politis | 369 | 51.1% | meta-relevant, well-geared — maintain |
| 20 | Landy | 378 | no RTA data | not in RTA meta; value is PvE/niche |

## 2. Per-mode lists

### RTA (meta-backed)

Your built heroes that appear in the RTA meta, by win rate:

| Hero | RTA WR | Games | Your sets | Meta build | Aligned |
|---|--:|--:|---|---|:-:|
| Boss Arunka | 57.2% | 1,290 | Health+Health+Health | Protection+Immunity | · |
| Sage Baal & Sezan | 54.1% | 3,722 | — | Speed+Hit | · |
| Silvertide Christy | 53.1% | 20,279 | Immunity+Health+Health | Resist+Resist+Resist | · |
| Genesis Ras | 52.6% | 20,145 | Destruction+Health | Destruction+Health | ✓ |
| Ruele of Light | 52.3% | 17,685 | Health+Resist+Resist | Reversal+Immunity | · |
| Politis | 51.1% | 4,612 | Critical+Defense | Weakening+Hit | · |
| Setsuka | 50.8% | 21,788 | Hit+Critical | Riposte+Immunity | · |
| Briar Witch Iseria | 49.7% | 13,980 | Speed | Speed | ✓ |
| Dark Corvus | 48.8% | 5,840 | Health+Health | Warfare+Health | · |
| Spirit Eye Celine | 48.8% | 13,857 | Destruction | Speed+Penetration | · |
| Celine | 48.5% | 11,615 | Hit+Critical+Critical | Destruction+Penetration | · |
| Elena | 48.3% | 3,056 | Critical+Defense | Speed+Resist | · |
| Straze | 46.8% | 3,410 | Attack | Speed+Torrent | · |

### Arena / Guild War offense (RTA-proxy)

No dedicated arena-defense or GW-offense sample in the repo; RTA is the closest proxy. Treat the RTA list above as the working order for PvP offense until a dedicated source is added.

### Hunt / PvE (provisional — session 6 will replace this)

No hunt one-shot/auto comp data yet (session 6). Provisional read: your best-geared heroes by role, since hunt teams want a bruiser/CR pusher + sustain + DPS. Confirm against real comps later.

| Hero | Role | Total WSS | Spd |
|---|---|--:|--:|
| Sage Baal & Sezan | mage | 416 | 184 |
| Mercedes | mage | 405 | 178 |
| All-Rounder Wanda | ranger | 403 | 205 |
| Tenebria | mage | 398 | 244 |
| Champion Zerato | mage | 394 | 169 |
| Mediator Kawerik | warrior | 389 | 225 |
| Elphelt | ranger | 388 | 204 |
| Briar Witch Iseria | ranger | 388 | 183 |
| Specter Tenebria | mage | 386 | 183 |
| Kikirat v2 | knight | 385 | 168 |
| Blood Blade Karin | assassin | 385 | 131 |
| Shuna | manauser | 382 | 166 |

---

### Recommended next actions
- Confirm or adjust these lists; I'll record the confirmed priority in CLAUDE.md ROSTER GOALS so later sessions read it.
- Session 6 adds hunt/endgame comps + thresholds, which will replace the provisional PvE list with real per-slot targets.
- To sharpen RTA gap reports with numeric stat targets, either normalize the T0 `recommend_equip` datamine table (local re-run) or revisit the epic7db rank-target scraper (deferred).

