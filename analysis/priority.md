# Hero readiness & priority

Owner priority (CLAUDE.md ROSTER GOALS, 2026-08-12): **all-mode readiness with PvE co-equal — NOT RTA-first.** So this is organized as *mode-coverage readiness* (are the right roles well-geared?), not an RTA win-rate ladder.

> **Data caveat, stated plainly:** the repo's only large-sample numeric data is RTA. Hunt / Abyss / Tower / GW-defense comps and stat thresholds are **not in the repo yet (session 6)**. So the PvE-weighted priority you actually want is *blocked on session 6*; below, PvE/GW readiness is provisional (role + gear), and only the RTA column is data-backed.

## 1. Readiness by role (your all-mode spine)

Your best-geared built heroes in each role. Good mode coverage means each role has options; thin roles are where new investment pays off across *every* mode.

- **mage** (11 built): Sage Baal & Sezan (416), Mercedes (405), Tenebria (398), Champion Zerato (394), Specter Tenebria (386), Basar (381) +5 more
- **warrior** (11 built): Mediator Kawerik (389), Conqueror Lilias (382), Straze (380), Rimuru (371), Martial Artist Ken (369), Dark Corvus (362) +5 more
- **assassin** (9 built): Blood Blade Karin (385), Savior Adin (371), Tempest Surin (367), Setsuka (365), Muwi (361), Summer's Disciple Alexa (356) +3 more
- **ranger** (9 built): All-Rounder Wanda (403), Elphelt (388), Briar Witch Iseria (388), Landy (378), Seaside Bellona (374), Bellona (371) +3 more
- **knight** (8 built): Kikirat v2 (385), Silvertide Christy (376), Falconer Kluri (374), Boss Arunka (372), Charles (367), Lilias (364) +2 more
- **manauser** (8 built): Shuna (382), Elena (373), Tamarinne (366), Ruele of Light (359), Destina (356), Emilia (350) +2 more

_Number in parens = total reforge-projected WSS (gear quality). Role labels are from the Fribbels export._

## 2. Highest-value fixes (act on these regardless of mode)

These come straight from the gear data and help in *every* mode:

- **No active set bonus** (2): Sage Baal & Sezan, All-Rounder Wanda. These waste their substats — re-slot into a real set (see the allocator). Biggest loss: your best-geared piece is often here.
- **Set differs from RTA meta** (11), for the heroes where we *have* RTA data — worth a look for PvP:
    - Boss Arunka: you run Health+Health+Health · meta Protection+Immunity (57% WR)
    - Sage Baal & Sezan: you run no set · meta Speed+Hit (54% WR)
    - Silvertide Christy: you run Immunity+Health+Health · meta Resist+Resist+Resist (53% WR)
    - Ruele of Light: you run Health+Resist+Resist · meta Reversal+Immunity (52% WR)
    - Politis: you run Critical+Defense · meta Weakening+Hit (51% WR)
    - Setsuka: you run Hit+Critical · meta Riposte+Immunity (51% WR)
    - Dark Corvus: you run Health+Health · meta Warfare+Health (49% WR)
    - Spirit Eye Celine: you run Destruction · meta Speed+Penetration (49% WR)
- **Reforge-pending**: 438 lv85 pieces gain WSS from a free reforge (see gear_report.md) — cheapest upgrade across all modes.

## 3. Per-mode readiness

### RTA (data-backed)
Built heroes present in the RTA meta, with your set alignment:

| Hero | RTA WR | Games | Your sets | Meta build | Aligned |
|---|--:|--:|---|---|:-:|
| Boss Arunka | 57.2% | 1,290 | Health+Health+Health | Protection+Immunity | · |
| Sage Baal & Sezan | 54.1% | 3,722 | no set | Speed+Hit | · |
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

_Only 13 of your 56 built heroes are in the RTA meta; the rest are older/PvE-oriented and can't be ranked on PvP data._

### Arena / Guild War offense
Overlaps RTA heavily; use the RTA table as the working proxy until a dedicated arena-defense / GW sample is added. **Not separately data-backed.**

### PvE (hunts, Abyss, Tower, seasonal) — PROVISIONAL
**No PvE comp/threshold data in the repo yet — session 6.** Until then this is only 'who is well-geared, by role' (section 1), which is necessary but not sufficient: PvE wants *specific* units hitting *specific* speed/bulk breakpoints per boss. Do not treat section 1 as a PvE tier list.

---

### What actually moves your stated priority forward
1. **Run session 6 next** — it builds the hunt/Abyss/Tower/GW comp library with per-slot stat thresholds. That is the missing input for a real PvE-weighted priority; everything else here is method waiting on that data.
2. Meanwhile, the section-2 fixes (no-set builds, reforge-pending) help in every mode and need no new data.
3. Optional T0 upgrade: normalize the datamine `recommend_equip` table (local re-run) for per-hero recommended sets/artifacts/stat weights — usable for PvE too, not just RTA.

