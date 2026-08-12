#!/usr/bin/env python3
"""Generate a self-contained, action-first dashboard (analysis/dashboard.html).

Answers three concrete questions and nothing else:
  1. Which pieces do I REFORGE?  (equipped lv85 pieces, free gold-only WSS gain)
  2. Which pieces do I ENHANCE?  (partials to finish + best benched +0 to level)
  3. Which pieces do I ASSIGN?   (fix no-set heroes; the best idle bench per slot)

A Heroes reference tab shows each built hero's pieces + RTA meta sets/artifact.
Deliberately NO PvE-comp tab: those were team lists without stat targets and
read as guidance the data can't actually back. Regenerate after any sync:
    python scripts/analyze.py && python scripts/build_dashboard.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from e7lib import Data  # noqa: E402
from analyze import CODE_TO_NAME, hero_builds  # noqa: E402
import allocate  # noqa: E402

OUT = REPO / "analysis" / "dashboard.html"
SLOTS = ["Weapon", "Helmet", "Armor", "Necklace", "Ring", "Boots"]


def gather():
    d = Data()
    builds = hero_builds(d)
    role_of = {h["name"]: h.get("role") for h in d.heroes}
    for b in builds:
        b["role"] = role_of.get(b["name"])
    hero_obj = {h["name"]: h for h in d.heroes}

    scores = json.loads((REPO / "analysis" / "gear_scores.json").read_text())["items"]
    by_id = {r["ingameId"]: r for r in scores}

    # -- 1. REFORGE: equipped lv85 pieces with a pending free reforge ---------
    pending = [r for r in scores if r.get("reforge_pending")]
    equipped_pending = sorted([r for r in pending if r.get("equipped_by")],
                              key=lambda r: -r["reforge_gain"])
    reforge_list = [{
        "hero": r["equipped_by"], "gear": r["gear"],
        "set": r["set"].replace("Set", ""), "main": r["main"],
        "gain": round(r["reforge_gain"], 1), "to": round(r["reforge_wss"], 1),
    } for r in equipped_pending]
    spare_pending = len([r for r in pending if not r.get("equipped_by")])

    # -- 2. ENHANCE -----------------------------------------------------------
    # (a) partials you already started (+3/+6/+9/+12) — just gold to finish.
    partials = sorted([r for r in scores if 0 < r["enhance"] < 15],
                      key=lambda r: -r["reforge_wss"])
    partial_list = [{
        "gear": r["gear"], "set": r["set"].replace("Set", ""), "main": r["main"],
        "rank": r["rank"], "enh": r["enhance"], "wss": round(r["reforge_wss"], 1),
        "equipped_by": r.get("equipped_by"),
    } for r in partials]
    # (b) best benched +0 Epic/Heroic worth taking to +15 (gamble on rolls).
    #     Restrict to 4-substat pieces so all substat *types* are already
    #     revealed — a fair "good starting stats" signal (final value is RNG).
    coll_by_id = {it["ingameId"]: it for it in d.items}
    gamble = []
    for r in scores:
        if r["enhance"] != 0 or r["rank"] not in ("Epic", "Heroic") or r.get("equipped_by"):
            continue
        it = coll_by_id.get(r["ingameId"])
        if not it or len(it.get("substats") or []) < 4:
            continue
        gamble.append(r)
    gamble_by_slot = {}
    for slot in SLOTS:
        rows = sorted([r for r in gamble if r["gear"] == slot],
                      key=lambda r: -r["reforge_wss"])[:5]
        gamble_by_slot[slot] = [{
            "set": r["set"].replace("Set", ""), "main": r["main"], "rank": r["rank"],
            "wss": round(r["reforge_wss"], 1),
        } for r in rows]

    # -- 3. ASSIGN ------------------------------------------------------------
    # (a) no-set heroes: coherent-set fix, conflict-aware so two heroes never
    #     get handed the same physical spare piece.
    noset = [b["name"] for b in builds if not b["sets"]]
    prelim = []
    for n in noset:
        try:
            _, cur, best, _ = allocate.best_build(d, n)
        except SystemExit:
            continue
        if not best:
            continue
        cw = sum(d.reforge_wss(it) for it in cur.values())
        prelim.append((best[0] - cw, n))
    prelim.sort(reverse=True)
    used_ids: set = set()
    no_set_fixes = []
    for _, n in prelim:
        _, cur, best, _ = allocate.best_build(d, n, exclude_ids=used_ids)
        if not best:
            continue
        cw = sum(d.reforge_wss(it) for it in cur.values())
        w, combo, sets = best
        pieces = []
        for slot, it in zip(SLOTS, combo):
            c = cur.get(slot)
            changed = c is None or c.get("ingameId") != it.get("ingameId")
            if changed and it.get("ingameId"):
                used_ids.add(it["ingameId"])
            pieces.append({
                "slot": slot, "set": it["set"].replace("Set", ""),
                "main": it["main"]["type"], "enh": it["enhance"],
                "wss": round(d.reforge_wss(it), 1), "changed": changed,
            })
        no_set_fixes.append({
            "hero": n, "cur_wss": round(cw), "new_wss": round(w),
            "gain": round(w - cw),
            "new_sets": "+".join(CODE_TO_NAME.get(c, c) for c in sets),
            "pieces": pieces,
        })

    # (b) the bench: best idle (unequipped) +15 pieces per slot, ready to equip.
    idle = [r for r in scores if not r.get("equipped_by") and r["enhance"] == 15]
    bench = {}
    for slot in SLOTS:
        rows = sorted([r for r in idle if r["gear"] == slot],
                      key=lambda r: -r["reforge_wss"])[:6]
        bench[slot] = [{
            "set": r["set"].replace("Set", ""), "main": r["main"], "rank": r["rank"],
            "wss": round(r["reforge_wss"], 1),
        } for r in rows]
    idle_count = len(idle)

    # -- Heroes reference tab -------------------------------------------------
    pending_by_hero = defaultdict(int)
    for r in equipped_pending:
        pending_by_hero[r["equipped_by"]] += 1
    heroes_detail = []
    for b in sorted(builds, key=lambda b: -b["total_wss"]):
        h = hero_obj[b["name"]]
        pieces = []
        for slot, it in (h.get("equipment") or {}).items():
            pieces.append({"slot": slot, "set": it["set"].replace("Set", ""),
                           "main": it["main"]["type"],
                           "wss": round(d.reforge_wss(it), 1), "enh": it["enhance"]})
        meta = d.meta_for(b["name"])
        rec_sets = rec_art = meta_wr = None
        if meta:
            m = meta["record"]
            meta_wr = m.get("derived", {}).get("win_rate")
            tb = (m.get("top_builds") or [{}])[0].get("set_agg_code")
            rec_sets = "+".join(CODE_TO_NAME.get(x, x) for x in (tb or "").split("+") if x) or None
            arts = m.get("top_artifacts") or []
            rec_art = arts[0].get("artifact_name") if arts else None
        heroes_detail.append({
            "name": b["name"], "role": b["role"], "wss": b["total_wss"],
            "spd": b["spd"], "cr": b["cr"], "cd": b["cd"],
            "sets": "+".join(b["sets"]) or "—", "no_set": not b["sets"],
            "meta_wr": meta_wr, "rec_sets": rec_sets, "rec_art": rec_art,
            "aligned": b.get("set_aligned"),
            "pending": pending_by_hero.get(b["name"], 0),
            "pieces": sorted(pieces, key=lambda p: -p["wss"]),
        })

    # -- resources (reforge + enhance both cost gold) -------------------------
    inv = json.loads((REPO / "collection" / "inventory.json").read_text())
    cur = inv["currencies"]
    resources = {
        "Gold": cur.get("gold", {}).get("value"),
        "Skystone": cur.get("skystone", {}).get("value"),
        "Covenant Bookmarks": cur.get("covenant_bookmarks", {}).get("value"),
        "Powder of Knowledge": cur.get("powder_of_knowledge", {}).get("value"),
        "MolaGora": inv.get("growth_ingredients", {}).get("molagora", {}).get("value"),
    }

    return {
        "roster": len(d.heroes), "built": len(builds), "gear": len(scores),
        "reforge_list": reforge_list,
        "reforge_gain": round(sum(r["reforge_gain"] for r in equipped_pending)),
        "spare_pending": spare_pending,
        "partials": partial_list, "gamble": gamble_by_slot,
        "no_set_fixes": no_set_fixes, "bench": bench, "idle_count": idle_count,
        "heroes": heroes_detail, "resources": resources,
    }


def render(data: dict) -> str:
    return TEMPLATE.replace("/*DATA*/", json.dumps(data, ensure_ascii=False))


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Astromancer</title>
<style>
:root{
  --ground:#f3f4f8; --surface:#ffffff; --surface-2:#eef0f6; --border:#d9dde8;
  --text:#1a1d27; --muted:#606779; --accent:#1f8fc7; --accent-soft:#dceef7;
  --gold:#a9781f; --good:#2f9e6b; --warn:#c78a1e; --crit:#c9524c;
  --shadow:0 1px 2px rgba(20,24,40,.06),0 4px 16px rgba(20,24,40,.06);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#0c0e15; --surface:#151925; --surface-2:#1c2130; --border:#29303f;
  --text:#e7eaf2; --muted:#8b93a7; --accent:#45b7e8; --accent-soft:#132a38;
  --gold:#e0b64a; --good:#4fbf87; --warn:#e0a33a; --crit:#e0655f;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 6px 22px rgba(0,0,0,.35);
}}
:root[data-theme="dark"]{
  --ground:#0c0e15; --surface:#151925; --surface-2:#1c2130; --border:#29303f;
  --text:#e7eaf2; --muted:#8b93a7; --accent:#45b7e8; --accent-soft:#132a38;
  --gold:#e0b64a; --good:#4fbf87; --warn:#e0a33a; --crit:#e0655f;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 6px 22px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--text);
  font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:26px 20px 90px}
header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
h1{font-size:25px;margin:0;letter-spacing:-.02em;font-weight:700}
.sub{color:var(--muted);font-size:13.5px}
.tabs{display:flex;gap:4px;flex-wrap:wrap;margin:20px 0;border-bottom:1px solid var(--border)}
.tab{appearance:none;background:none;border:0;color:var(--muted);font:inherit;font-weight:600;
  padding:9px 14px;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;border-radius:6px 6px 0 0}
.tab:hover{color:var(--text);background:var(--surface-2)}
.tab[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent)}
.tab:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.panel{display:none}.panel.on{display:block}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow)}
.card .k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}
.card .v{font-size:23px;font-weight:700;margin-top:3px;font-variant-numeric:tabular-nums}
.card .v small{font-size:13px;color:var(--muted);font-weight:600}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
@media(max-width:760px){.grid2{grid-template-columns:1fr}}
.block{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow);margin-bottom:16px}
.block h2{font-size:15px;margin:0 0 4px;letter-spacing:-.01em}
.lead{color:var(--muted);font-size:13px;margin:0 0 12px}
.tools{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
input[type=search],select{background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:8px 11px;font:inherit}
input[type=search]{min-width:190px;flex:1}
input:focus,select:focus{outline:2px solid var(--accent);outline-offset:1px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
.scroll{overflow-x:auto}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--border);white-space:nowrap}
th{color:var(--muted);font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;cursor:pointer;user-select:none}
th.num,td.num{text-align:right;font-variant-numeric:tabular-nums}
tbody tr.h{cursor:pointer}
tbody tr.h:hover{background:var(--surface-2)}
tr.detail>td{background:var(--surface-2);white-space:normal}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid transparent}
.pill.good{color:var(--good);background:color-mix(in srgb,var(--good) 14%,transparent)}
.pill.warn{color:var(--warn);background:color-mix(in srgb,var(--warn) 16%,transparent)}
.pill.mut{color:var(--muted);background:var(--surface-2)}
.pill.acc{color:var(--accent);background:var(--accent-soft)}
.pill.crit{color:var(--crit);background:color-mix(in srgb,var(--crit) 14%,transparent)}
.bar{display:inline-block;height:6px;border-radius:3px;background:var(--surface-2);overflow:hidden;width:52px;vertical-align:middle}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--gold))}
.note{color:var(--muted);font-size:12.5px;margin-top:8px}
.chg{color:var(--accent);font-weight:700}
.toggle{margin-left:auto;background:var(--surface);border:1px solid var(--border);color:var(--muted);border-radius:8px;padding:7px 11px;font:inherit;cursor:pointer}
.toggle:hover{color:var(--text)}
a{color:var(--accent)}
.rec{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:13px;margin:6px 0}
.rec b{color:var(--muted);font-weight:600}
.mini{font-size:12.5px;color:var(--muted)}
.kbd{font-family:ui-monospace,monospace;background:var(--surface-2);border:1px solid var(--border);border-radius:5px;padding:1px 6px;font-size:12px}
.callout{background:var(--accent-soft);border:1px solid var(--accent);border-radius:12px;padding:14px 16px;margin-bottom:16px;font-size:13.5px}
.slotcard{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 12px}
.slotcard h3{margin:0 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.slotcard .row{display:flex;justify-content:space-between;gap:8px;font-size:12.5px;padding:2px 0;border-bottom:1px dashed var(--border)}
.slotcard .row:last-child{border-bottom:0}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Astromancer</h1>
    <button class="toggle" id="themeBtn" type="button">Theme</button>
  </header>
  <div class="sub">Gear actions for your Epic Seven account. Snapshot from repo data — regenerate with <span class="kbd">python scripts/analyze.py &amp;&amp; python scripts/build_dashboard.py</span>.</div>
  <nav class="tabs" role="tablist">
    <button class="tab" role="tab" data-p="reforge" aria-selected="true">Reforge</button>
    <button class="tab" role="tab" data-p="enhance" aria-selected="false">Enhance</button>
    <button class="tab" role="tab" data-p="assign" aria-selected="false">Assign gear</button>
    <button class="tab" role="tab" data-p="heroes" aria-selected="false">Heroes</button>
  </nav>
  <section class="panel on" id="reforge"></section>
  <section class="panel" id="enhance"></section>
  <section class="panel" id="assign"></section>
  <section class="panel" id="heroes"></section>
</div>
<script id="data" type="application/json">/*DATA*/</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const fmt=n=>n==null?'—':n.toLocaleString();
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const short=s=>String(s).replace('Percent','%').replace('CriticalHitChance','Crit').replace('CriticalHitDamage','CritDmg').replace('Effectiveness','Eff').replace('EffectResistance','ER');
const root=document.documentElement, tb=document.getElementById('themeBtn');
tb.onclick=()=>{const c=root.getAttribute('data-theme');
  const n=c==='dark'?'light':(c==='light'?'':'dark');
  if(n)root.setAttribute('data-theme',n);else root.removeAttribute('data-theme');};

// ---- 1. Reforge ----
function reforgePanel(){
  const rows=D.reforge_list.map(u=>`<tr>
    <td class="num"><span class="pill good">+${u.gain}</span></td>
    <td>${esc(u.hero)}</td><td>${u.gear}</td><td>${u.set}</td>
    <td>${short(u.main)}</td><td class="num">${u.to}</td></tr>`).join('')
    ||'<tr><td colspan="6">No pending reforges — every equipped lv85 piece is already reforged.</td></tr>';
  document.getElementById('reforge').innerHTML=`
  <div class="cards">
    <div class="card"><div class="k">Ready to reforge</div><div class="v">${D.reforge_list.length}</div></div>
    <div class="card"><div class="k">Total WSS gained</div><div class="v">+${D.reforge_gain}</div></div>
    <div class="card"><div class="k">Gold on hand</div><div class="v">${fmt(D.resources.Gold)}</div></div>
    <div class="card"><div class="k">Built heroes</div><div class="v">${D.built} <small>/ ${D.roster}</small></div></div>
  </div>
  <div class="callout"><b>Do this first — it's free power.</b> Every piece below is a lv85 gear item
    already on one of your heroes that can be <b>reforged</b> (costs only gold, never lowers a stat).
    Reforging raises substats permanently. Work top-down by WSS gain.</div>
  <div class="block"><h2>Reforge these — equipped lv85 pieces, biggest gain first</h2>
    <p class="lead">WSS = weighted substat score across the piece's 4 substats (Speed ×2, Crit ×1.6, etc.). "→ WSS" is where the piece lands after reforge.</p>
    <div class="scroll"><table><thead><tr>
      <th class="num">WSS gain</th><th>Hero</th><th>Slot</th><th>Set</th><th>Main</th><th class="num">→ WSS</th>
    </tr></thead><tbody>${rows}</tbody></table></div>
    <p class="note">${D.spare_pending} more lv85 pieces sit unequipped and can be reforged too — do those only once you equip them (below, Assign tab).</p></div>`;
}

// ---- 2. Enhance ----
function enhancePanel(){
  const parts=D.partials.map(p=>{
    const where=p.equipped_by?`<span class="mini">on ${esc(p.equipped_by)}</span>`:`<span class="pill mut">bench</span>`;
    return `<tr><td class="num"><span class="pill warn">+${p.enh}</span></td><td>${p.gear}</td><td>${p.set}</td>
      <td>${short(p.main)}</td><td>${p.rank}</td><td class="num">${p.wss}</td><td>${where}</td></tr>`;
  }).join('')||'<tr><td colspan="7">No half-enhanced pieces — nothing sitting at +3/+6/+9.</td></tr>';
  const slots=Object.entries(D.gamble).map(([slot,rows])=>{
    const body=rows.map(r=>`<div class="row"><span>${r.set} · ${short(r.main)}</span><span class="num">${r.wss}</span></div>`).join('')
      ||'<div class="row mini">none</div>';
    return `<div class="slotcard"><h3>${slot}</h3>${body}</div>`;
  }).join('');
  document.getElementById('enhance').innerHTML=`
  <div class="callout"><b>Two kinds of enhance.</b> First finish pieces you already started paying for.
    Then, if you want more benched gear ready, take the best +0 pieces to +15 — but that's a
    <b>gamble on which substats roll up</b>, so only do it when you need a slot filled.</div>
  <div class="block"><h2>1 · Finish these half-enhanced pieces</h2>
    <p class="lead">Already partly enhanced (gold sunk in). Completing them to +15 unlocks their remaining substat rolls. Ranked by current projected WSS.</p>
    <div class="scroll"><table><thead><tr>
      <th class="num">At</th><th>Slot</th><th>Set</th><th>Main</th><th>Rank</th><th class="num">WSS now</th><th>Where</th>
    </tr></thead><tbody>${parts}</tbody></table></div></div>
  <div class="block"><h2>2 · Best benched +0 pieces worth leveling</h2>
    <p class="lead">Unequipped Epic/Heroic pieces at +0 whose four substats are already all revealed — the best "starting stats" per slot. Enhancing to +15 rolls those substats up 5 times (random which), so treat WSS here as a <b>floor, not a promise</b>. Level these only when you're filling a slot for a hero.</p>
    <div class="grid3">${slots}</div></div>`;
}

// ---- 3. Assign gear ----
function assignPanel(){
  const fixes=D.no_set_fixes.map(f=>{
    const rows=f.pieces.map(p=>`<tr class="${p.changed?'':'mini'}">
      <td>${p.changed?'<span class="chg">▸</span>':''} ${p.slot}</td>
      <td>${p.changed?'<b>'+p.set+'</b>':p.set}</td><td>${short(p.main)}</td>
      <td class="num">+${p.enh}</td><td class="num">${p.wss}</td>
      <td>${p.changed?'<span class="pill acc">move in</span>':'<span class="pill mut">keep</span>'}</td></tr>`).join('');
    return `<div class="block"><h2>${esc(f.hero)} — currently <span class="pill crit">no set bonus</span></h2>
      <p class="lead">Re-slot into <b>${f.new_sets}</b>: ${f.cur_wss} → <b>${f.new_wss} WSS</b> <span class="pill good">+${f.gain}</span>, and gains a real set effect. Pieces marked ▸ move in from your bench (each piece is reserved to one hero, so these two plans don't collide).</p>
      <div class="scroll"><table><thead><tr><th>Slot</th><th>Set</th><th>Main</th><th class="num">+</th><th class="num">WSS</th><th>Action</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
  }).join('')||'<div class="block">Every built hero already has a set bonus. 🎉</div>';
  const bench=Object.entries(D.bench).map(([slot,rows])=>{
    const body=rows.map(r=>`<div class="row"><span>${r.set} · ${short(r.main)} <span class="mini">${r.rank[0]}</span></span><span class="num">${r.wss}</span></div>`).join('')
      ||'<div class="row mini">none</div>';
    return `<div class="slotcard"><h3>${slot}</h3>${body}</div>`;
  }).join('');
  document.getElementById('assign').innerHTML=`
  <div class="callout"><b>Why there's no one-click "optimal gear for everyone".</b>
    Picking the single best piece for each hero needs a per-hero <b>stat target</b>
    (e.g. "Speed 250, Crit 100%, Atk 4000") — that's the job Fribbels' optimizer does.
    The repo has those targets only for RTA heroes, not for every mode, so a blind
    "max WSS" pass would just hand your few best pieces to whoever's checked first.
    What <i>is</i> unambiguous: heroes wearing gear with <b>no set bonus at all</b>
    (pure waste), and <b>which spare pieces are your strongest bench</b> to pull from
    when you build any hero. Both are below.</div>
  <div class="block"><h2>1 · Fix heroes running no set bonus</h2>
    <p class="lead">The clearest free upgrade in any mode: a set bonus you're currently throwing away.</p></div>
  ${fixes}
  <div class="block"><h2>2 · Your strongest bench — best idle pieces per slot</h2>
    <p class="lead">${fmt(D.idle_count)} fully-enhanced pieces sit unequipped. These are the top ones by WSS in each slot — the pool to pull from when gearing a hero for hunts, Arena, GW, or RTA. <span class="mini">Letter = rank (E/H).</span></p>
    <div class="grid3">${bench}</div></div>`;
}

// ---- 4. Heroes (reference) ----
let hSort={k:'wss',dir:-1};
function heroesPanel(){
  const p=document.getElementById('heroes');
  p.innerHTML=`<div class="block"><div class="tools">
    <input type="search" id="hq" placeholder="Search hero or set…">
    <select id="hrole"><option value="">All roles</option></select>
    <select id="hf"><option value="">All</option><option value="noset">No set bonus</option>
      <option value="meta">In RTA meta</option><option value="mis">Meta set mismatch</option></select>
    <span class="pill mut" id="hc"></span></div>
    <div class="scroll"><table><thead><tr>
      <th data-k="name">Hero</th><th data-k="role">Role</th><th class="num" data-k="wss">WSS</th>
      <th class="num" data-k="spd">Spd</th><th data-k="sets">Sets</th>
      <th class="num" data-k="meta_wr">RTA WR</th><th class="num" data-k="pending">Reforge</th>
    </tr></thead><tbody></tbody></table></div>
    <p class="note">Reference only. Click a hero for their pieces and RTA meta build. WSS = reforge-projected weighted substat score across 6 pieces. "Reforge" = pending free reforges on that hero (see Reforge tab).</p></div>`;
  const rs=p.querySelector('#hrole');
  [...new Set(D.heroes.map(h=>h.role))].filter(Boolean).sort().forEach(r=>rs.insertAdjacentHTML('beforeend',`<option>${r}</option>`));
  const draw=()=>{
    const q=p.querySelector('#hq').value.toLowerCase(),role=rs.value,f=p.querySelector('#hf').value;
    let rows=D.heroes.filter(h=>{
      if(role&&h.role!==role)return false;
      if(q&&!(h.name.toLowerCase().includes(q)||h.sets.toLowerCase().includes(q)))return false;
      if(f==='noset'&&!h.no_set)return false;
      if(f==='meta'&&h.meta_wr==null)return false;
      if(f==='mis'&&!(h.rec_sets&&!h.aligned))return false;
      return true;});
    rows.sort((a,b)=>{let x=a[hSort.k],y=b[hSort.k];if(x==null)x=-Infinity;if(y==null)y=-Infinity;return (x<y?-1:x>y?1:0)*hSort.dir;});
    const mx=Math.max(...D.heroes.map(h=>h.wss));
    p.querySelector('#hc').textContent=rows.length+' heroes';
    const tbb=p.querySelector('tbody');tbb.innerHTML='';
    rows.forEach((h,i)=>{
      const wr=h.meta_wr!=null?(h.meta_wr*100).toFixed(1)+'%':'—';
      const setc=h.no_set?`<span class="pill warn">no set</span>`:h.sets;
      const pend=h.pending?`<span class="pill acc">${h.pending}</span>`:'·';
      tbb.insertAdjacentHTML('beforeend',`<tr class="h" data-i="${i}">
        <td>${esc(h.name)}</td><td>${h.role||'?'}</td>
        <td class="num">${h.wss.toFixed(0)} <span class="bar"><i style="width:${h.wss/mx*100}%"></i></span></td>
        <td class="num">${h.spd}</td><td>${setc}</td><td class="num">${wr}</td><td class="num">${pend}</td></tr>`);
      tbb.lastElementChild._h=h;
    });
    tbb.querySelectorAll('tr.h').forEach(tr=>tr.onclick=()=>toggle(tr));
  };
  const toggle=(tr)=>{
    if(tr.nextElementSibling&&tr.nextElementSibling.classList.contains('detail')){tr.nextElementSibling.remove();return;}
    const h=tr._h;
    const pieces=h.pieces.map(pc=>`<tr><td>${pc.slot}</td><td>${pc.set}</td><td>${short(pc.main)}</td><td class="num">+${pc.enh}</td><td class="num">${pc.wss}</td></tr>`).join('');
    const rta=h.rec_sets?`<div class="rec"><b>RTA meta sets</b><span>${h.rec_sets} ${h.aligned?'<span class="pill good">you match</span>':'<span class="pill warn">you run '+esc(h.sets)+'</span>'}</span>`+
      (h.rec_art?`<b>RTA artifact</b><span>${esc(h.rec_art)}</span>`:'')+
      `<b>RTA win rate</b><span>${(h.meta_wr*100).toFixed(1)}%</span></div>`
      :`<p class="mini">No RTA meta data for this hero (older / PvE-oriented). No per-slot stat targets exist in the data yet.</p>`;
    const fix=h.no_set?`<p class="pill warn" style="margin-top:8px">No set bonus — see the Assign tab for the exact fix.</p>`:'';
    const dd=document.createElement('tr');dd.className='detail';
    dd.innerHTML=`<td colspan="7"><div class="grid2"><div>
      <b class="mini" style="color:var(--muted)">Equipped pieces</b>
      <div class="scroll"><table><thead><tr><th>Slot</th><th>Set</th><th>Main</th><th class="num">+</th><th class="num">WSS</th></tr></thead><tbody>${pieces}</tbody></table></div>
      </div><div><b class="mini" style="color:var(--muted)">RTA recommendation</b>${rta}${fix}</div></div></td>`;
    tr.after(dd);
  };
  p.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;
    hSort.dir=(hSort.k===k)?-hSort.dir:(['name','role','sets'].includes(k)?1:-1);hSort.k=k;draw();});
  p.querySelector('#hq').oninput=draw;rs.onchange=draw;p.querySelector('#hf').onchange=draw;draw();
}

const panels={reforge:reforgePanel,enhance:enhancePanel,assign:assignPanel,heroes:heroesPanel};
reforgePanel();let drawn={reforge:1};
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.setAttribute('aria-selected','false'));
  document.querySelectorAll('.panel').forEach(x=>x.classList.remove('on'));
  t.setAttribute('aria-selected','true');const id=t.dataset.p;
  document.getElementById(id).classList.add('on');if(!drawn[id]){panels[id]();drawn[id]=1;}});
</script>
</body>
</html>
"""


def main():
    OUT.write_text(render(gather()))
    print(f"wrote {OUT.relative_to(REPO)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
