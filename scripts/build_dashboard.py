#!/usr/bin/env python3
"""Generate a self-contained, prescriptive dashboard (analysis/dashboard.html).

Not just a data dump — it tells you what to DO: which pieces to reforge, how
each built hero compares to the RTA meta, where each hero is used in PvE, and
which no-set builds to fix. Regenerate after any sync:
    python scripts/analyze.py && python scripts/build_dashboard.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from e7lib import Data  # noqa: E402
from analyze import active_sets, CODE_TO_NAME, hero_builds  # noqa: E402
import allocate  # noqa: E402

OUT = REPO / "analysis" / "dashboard.html"


def norm(s: str) -> str:
    """Punctuation-insensitive key: 'Ainos 2.0' == 'ainos-20' == 'ainos20'."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def gather():
    d = Data()
    builds = hero_builds(d)
    role_of = {h["name"]: h.get("role") for h in d.heroes}
    for b in builds:
        b["role"] = role_of.get(b["name"])

    # roster ownership key set (built/promoted heroes only — the export has
    # no heroes below 5*, so this is "built roster", not full ownership)
    roster_keys = {norm(h["name"]): h["name"] for h in d.heroes}
    # datamine display names for resolving comp slugs
    dm = json.loads((REPO / "datamine" / "heroes.json").read_text())["heroes"]
    dm_by_key = {}
    for h in dm:
        k = norm(h["name"])
        if k not in dm_by_key or not h.get("is_variant", False):
            dm_by_key[k] = h["name"]

    scores = json.loads((REPO / "analysis" / "gear_scores.json").read_text())["items"]
    reforge_pending = [r for r in scores if r.get("reforge_pending")]
    # upgrade priority: pending pieces on a hero, biggest gain first
    up = sorted([r for r in reforge_pending if r.get("equipped_by")],
                key=lambda r: -r["reforge_gain"])
    upgrade_list = [{
        "hero": r["equipped_by"], "gear": r["gear"], "set": r["set"].replace("Set", ""),
        "gain": round(r["reforge_gain"], 1), "to": round(r["reforge_wss"], 1),
    } for r in up[:40]]

    inv = json.loads((REPO / "collection" / "inventory.json").read_text())
    cur = inv["currencies"]
    resources = {
        "Gold": cur.get("gold", {}).get("value"),
        "Skystone": cur.get("skystone", {}).get("value"),
        "Covenant Bookmarks": cur.get("covenant_bookmarks", {}).get("value"),
        "Powder of Knowledge": cur.get("powder_of_knowledge", {}).get("value"),
        "MolaGora": inv.get("growth_ingredients", {}).get("molagora", {}).get("value"),
        "Friendship": cur.get("friendship_points", {}).get("value"),
    }

    # --- per built hero detail ---
    pending_by_hero = defaultdict(int)
    for r in reforge_pending:
        if r.get("equipped_by"):
            pending_by_hero[r["equipped_by"]] += 1

    comps_doc = json.loads((REPO / "meta" / "pve" / "comps.json").read_text())
    comp_use = defaultdict(list)          # roster hero name -> [comp titles]
    comps_out = []
    for c in comps_doc["comps"]:
        if c.get("kind") == "specialty_change" or \
                c["title"].lower().startswith("specialty change"):
            continue
        teams = []
        for t in c["teams"]:
            team = []
            for h in t:
                key = norm(h.get("slug") or h.get("name") or "")
                display = dm_by_key.get(key) or h.get("name") or h.get("slug")
                in_roster = key in roster_keys
                if in_roster:
                    comp_use[roster_keys[key]].append(c["title"])
                team.append({"name": display, "in_roster": in_roster})
            teams.append(team)
        comps_out.append({"title": c["title"], "tags": c["content_tags"],
                          "url": c["source_url"], "teams": teams})

    heroes_detail = []
    hero_obj = {h["name"]: h for h in d.heroes}
    for b in sorted(builds, key=lambda b: -b["total_wss"]):
        h = hero_obj[b["name"]]
        pieces = []
        for slot, it in (h.get("equipment") or {}).items():
            pieces.append({"slot": slot, "set": it["set"].replace("Set", ""),
                           "main": it["main"]["type"],
                           "wss": round(d.reforge_wss(it), 1),
                           "enh": it["enhance"]})
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
            "pve": sorted(set(comp_use.get(b["name"], []))),
        })

    # allocator suggestions for the no-set heroes (cheap: only a few)
    fixes = []
    for b in builds:
        if b["sets"]:
            continue
        try:
            hero, current, best, _ = allocate.best_build(d, b["name"])
        except SystemExit:
            best = None
        cur_w = sum(d.reforge_wss(it) for it in current.values())
        if best:
            w, combo, sets = best
            fixes.append({
                "hero": b["name"], "cur_wss": round(cur_w),
                "new_wss": round(w), "gain": round(w - cur_w),
                "new_sets": "+".join(CODE_TO_NAME.get(c, c) for c in sets),
            })

    by_role = defaultdict(int)
    for b in builds:
        by_role[b["role"] or "?"] += 1

    return {
        "roster": len(d.heroes), "built": len(builds), "gear": len(scores),
        "reforge_pending": len(reforge_pending),
        "reforge_gain": round(sum(r["reforge_gain"] for r in reforge_pending)),
        "resources": resources, "upgrade_list": upgrade_list,
        "role_counts": dict(sorted(by_role.items(), key=lambda kv: -kv[1])),
        "no_set_fixes": fixes,
        "heroes": heroes_detail, "comps": comps_out,
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
.bar{display:inline-block;height:6px;border-radius:3px;background:var(--surface-2);overflow:hidden;width:52px;vertical-align:middle}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--gold))}
.team{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
.hchip{padding:3px 9px;border-radius:8px;font-size:12.5px;border:1px solid var(--border);background:var(--surface-2)}
.hchip.own{border-color:var(--good);color:var(--good);background:color-mix(in srgb,var(--good) 10%,transparent)}
.note{color:var(--muted);font-size:12.5px;margin-top:8px}
.toggle{margin-left:auto;background:var(--surface);border:1px solid var(--border);color:var(--muted);border-radius:8px;padding:7px 11px;font:inherit;cursor:pointer}
.toggle:hover{color:var(--text)}
a{color:var(--accent)}
.tag{font-size:11px;color:var(--gold);border:1px solid color-mix(in srgb,var(--gold) 40%,transparent);border-radius:6px;padding:1px 6px;margin-left:6px}
.rec{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:13px;margin:6px 0}
.rec b{color:var(--muted);font-weight:600}
.mini{font-size:12.5px;color:var(--muted)}
.kbd{font-family:ui-monospace,monospace;background:var(--surface-2);border:1px solid var(--border);border-radius:5px;padding:1px 6px;font-size:12px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Astromancer</h1>
    <button class="toggle" id="themeBtn" type="button">Theme</button>
  </header>
  <div class="sub">Your Epic Seven account with recommendations. Snapshot from repo data — regenerate with <span class="kbd">python scripts/build_dashboard.py</span>.</div>
  <nav class="tabs" role="tablist">
    <button class="tab" role="tab" data-p="do" aria-selected="true">What to do</button>
    <button class="tab" role="tab" data-p="heroes" aria-selected="false">Heroes</button>
    <button class="tab" role="tab" data-p="pve" aria-selected="false">PvE comps</button>
  </nav>
  <section class="panel on" id="do"></section>
  <section class="panel" id="heroes"></section>
  <section class="panel" id="pve"></section>
</div>
<script id="data" type="application/json">/*DATA*/</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const fmt=n=>n==null?'—':n.toLocaleString();
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const root=document.documentElement, tb=document.getElementById('themeBtn');
tb.onclick=()=>{const c=root.getAttribute('data-theme');
  const n=c==='dark'?'light':(c==='light'?'':'dark');
  if(n)root.setAttribute('data-theme',n);else root.removeAttribute('data-theme');};

// ---- What to do ----
function doPanel(){
  const r=D.resources;
  const res=Object.entries(r).map(([k,v])=>`<tr><td>${k}</td><td class="num">${fmt(v)}</td></tr>`).join('');
  const fixes=D.no_set_fixes.map(f=>`<li><b>${esc(f.hero)}</b> has no set bonus (${f.cur_wss} WSS). Re-slot from spare gear → <b>${f.new_sets}</b>, ${f.new_wss} WSS <span class="pill good">+${f.gain}</span><br><span class="mini">Run <span class="kbd">python scripts/allocate.py "${esc(f.hero)}"</span> for the exact pieces.</span></li>`).join('')||'<li>All built heroes have a set bonus.</li>';
  const up=D.upgrade_list.map(u=>`<tr><td class="num"><span class="pill good">+${u.gain}</span></td><td>${esc(u.hero)}</td><td>${u.gear}</td><td>${u.set}</td><td class="num">${u.to}</td></tr>`).join('');
  document.getElementById('do').innerHTML=`
  <div class="cards">
    <div class="card"><div class="k">Built heroes</div><div class="v">${D.built} <small>/ ${D.roster}</small></div></div>
    <div class="card"><div class="k">Reforge now</div><div class="v">${D.reforge_pending} <small>+${D.reforge_gain} WSS</small></div></div>
    <div class="card"><div class="k">No-set fixes</div><div class="v">${D.no_set_fixes.length}</div></div>
    <div class="card"><div class="k">Gear pieces</div><div class="v">${fmt(D.gear)}</div></div>
  </div>
  <div class="block"><h2>1 · Fix heroes with no set bonus</h2>
    <p class="lead">Wasted substats — the biggest free power gain, in any mode.</p>
    <ul style="margin:0;padding-left:20px;line-height:1.7">${fixes}</ul></div>
  <div class="block"><h2>2 · Reforge these next</h2>
    <p class="lead">lv85 pieces on your heroes that gain WSS from a free reforge (gold only). Ranked by gain.</p>
    <div class="scroll"><table><thead><tr><th class="num">Gain</th><th>Hero</th><th>Slot</th><th>Set</th><th class="num">→ WSS</th></tr></thead><tbody>${up}</tbody></table></div>
    <p class="note">Showing top ${D.upgrade_list.length} of ${D.reforge_pending} pending. Spare (unequipped) pending pieces omitted — reforge those only when you equip them.</p></div>
  <div class="block"><h2>Resources on hand</h2><div class="scroll"><table><tbody>${res}</tbody></table></div></div>`;
}

// ---- Heroes (expandable rows with recommendations) ----
let hSort={k:'wss',dir:-1};
function heroesPanel(){
  const p=document.getElementById('heroes');
  p.innerHTML=`<div class="block"><div class="tools">
    <input type="search" id="hq" placeholder="Search hero or set…">
    <select id="hrole"><option value="">All roles</option></select>
    <select id="hf"><option value="">All</option><option value="noset">No set bonus</option>
      <option value="meta">In RTA meta</option><option value="mis">Meta set mismatch</option>
      <option value="pve">Used in a PvE comp</option></select>
    <span class="pill mut" id="hc"></span></div>
    <div class="scroll"><table><thead><tr>
      <th data-k="name">Hero</th><th data-k="role">Role</th><th class="num" data-k="wss">WSS</th>
      <th class="num" data-k="spd">Spd</th><th data-k="sets">Sets</th>
      <th class="num" data-k="meta_wr">RTA WR</th><th class="num" data-k="pending">Reforge</th>
    </tr></thead><tbody></tbody></table></div>
    <p class="note">Click a hero for their pieces, RTA build recommendation, and PvE usage. WSS = reforge-projected weighted substat score across 6 pieces.</p></div>`;
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
      if(f==='pve'&&!h.pve.length)return false;
      return true;});
    rows.sort((a,b)=>{let x=a[hSort.k],y=b[hSort.k];if(x==null)x=-Infinity;if(y==null)y=-Infinity;return (x<y?-1:x>y?1:0)*hSort.dir;});
    const mx=Math.max(...D.heroes.map(h=>h.wss));
    p.querySelector('#hc').textContent=rows.length+' heroes';
    const tb=p.querySelector('tbody');tb.innerHTML='';
    rows.forEach((h,i)=>{
      const wr=h.meta_wr!=null?(h.meta_wr*100).toFixed(1)+'%':'—';
      const setc=h.no_set?`<span class="pill warn">no set</span>`:h.sets;
      const pend=h.pending?`<span class="pill acc">${h.pending}</span>`:'·';
      tb.insertAdjacentHTML('beforeend',`<tr class="h" data-i="${i}">
        <td>${esc(h.name)}</td><td>${h.role||'?'}</td>
        <td class="num">${h.wss.toFixed(0)} <span class="bar"><i style="width:${h.wss/mx*100}%"></i></span></td>
        <td class="num">${h.spd}</td><td>${setc}</td><td class="num">${wr}</td><td class="num">${pend}</td></tr>`);
      tb.lastElementChild._h=h;
    });
    tb.querySelectorAll('tr.h').forEach(tr=>tr.onclick=()=>toggle(tr));
  };
  const toggle=(tr)=>{
    if(tr.nextElementSibling&&tr.nextElementSibling.classList.contains('detail')){tr.nextElementSibling.remove();return;}
    const h=tr._h;
    const pieces=h.pieces.map(pc=>`<tr><td>${pc.slot}</td><td>${pc.set}</td><td>${pc.main}</td><td class="num">+${pc.enh}</td><td class="num">${pc.wss}</td></tr>`).join('');
    const rta=h.rec_sets?`<div class="rec"><b>RTA meta sets</b><span>${h.rec_sets} ${h.aligned?'<span class="pill good">you match</span>':'<span class="pill warn">you run '+esc(h.sets)+'</span>'}</span>`+
      (h.rec_art?`<b>RTA artifact</b><span>${esc(h.rec_art)}</span>`:'')+
      `<b>RTA win rate</b><span>${(h.meta_wr*100).toFixed(1)}%</span></div>`
      :`<p class="mini">No RTA meta data for this hero (older / PvE-oriented). No stat targets exist in the data yet.</p>`;
    const pve=h.pve.length?`<div class="mini" style="margin-top:8px"><b style="color:var(--muted)">Used in PvE comps:</b> ${h.pve.map(esc).join(' · ')}</div>`:'';
    const fix=h.no_set?`<p class="pill warn" style="margin-top:8px">No set bonus — run <span class="kbd" style="background:transparent;border:0">allocate.py "${esc(h.name)}"</span></p>`:'';
    const d=document.createElement('tr');d.className='detail';
    d.innerHTML=`<td colspan="7"><div class="grid2"><div>
      <b class="mini" style="color:var(--muted)">Equipped pieces</b>
      <div class="scroll"><table><thead><tr><th>Slot</th><th>Set</th><th>Main</th><th class="num">+</th><th class="num">WSS</th></tr></thead><tbody>${pieces}</tbody></table></div>
      </div><div><b class="mini" style="color:var(--muted)">Recommendation</b>${rta}${pve}${fix}</div></div></td>`;
    tr.after(d);
  };
  p.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;
    hSort.dir=(hSort.k===k)?-hSort.dir:(['name','role','sets'].includes(k)?1:-1);hSort.k=k;draw();});
  p.querySelector('#hq').oninput=draw;rs.onchange=draw;p.querySelector('#hf').onchange=draw;draw();
}

// ---- PvE ----
function pvePanel(){
  const cards=D.comps.map(c=>{
    const tags=(c.tags||[]).map(t=>`<span class="tag">${t}</span>`).join('');
    const teams=c.teams.map(t=>`<div class="team">${t.map(h=>`<span class="hchip${h.in_roster?' own':''}">${esc(h.name)}</span>`).join('')}</div>`).join('');
    return `<div class="block"><h2>${esc(c.title)}${tags}</h2>
      <div class="note" style="margin:0 0 4px">${c.teams.length} team(s) · <a href="${esc(c.url)}" target="_blank" rel="noopener">source</a></div>${teams}</div>`;
  }).join('');
  document.getElementById('pve').innerHTML=`
  <div class="block" style="background:var(--accent-soft);border-color:var(--accent)">
    <b>Hunt & endgame comps</b> from epic7db guides (team lists only — per-slot stat thresholds are prose on the source, not captured).
    <br><span class="mini"><b style="color:var(--good)">Green</b> = the hero is in your <b>built roster</b> (5★+ in the Fribbels export). Your export has no heroes below 5★, so cheap 3★ units you own but haven't promoted (Helen, Ian, Adin…) will show grey even if you own them.</span>
  </div>${cards||'<div class="block">No comps harvested.</div>'}`;
}

const panels={do:doPanel,heroes:heroesPanel,pve:pvePanel};
doPanel();let drawn={do:1};
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
