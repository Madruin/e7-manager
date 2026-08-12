#!/usr/bin/env python3
"""Generate a self-contained browsable dashboard (analysis/dashboard.html).

Embeds the current analysis data (roster, built heroes, gear summary, PvE
comps, resources, priority) into one static HTML file so the owner can browse
everything without reading raw JSON. Regenerate after any sync:
    python scripts/analyze.py && python scripts/build_dashboard.py
"""

from __future__ import annotations

import html as _html
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from e7lib import Data  # noqa: E402
from analyze import active_sets, CODE_TO_NAME, hero_builds  # noqa: E402

OUT = REPO / "analysis" / "dashboard.html"


def gather():
    d = Data()
    builds = hero_builds(d)
    for b in builds:
        b["role"] = next((h.get("role") for h in d.heroes if h["name"] == b["name"]), None)

    scores = json.loads((REPO / "analysis" / "gear_scores.json").read_text())["items"]
    reforge_pending = [r for r in scores if r.get("reforge_pending")]
    top_gear = sorted(scores, key=lambda r: -r["reforge_wss"])[:25]

    inv = json.loads((REPO / "collection" / "inventory.json").read_text())
    cur = inv["currencies"]
    resources = {
        "Gold": cur.get("gold", {}).get("value"),
        "Skystone": cur.get("skystone", {}).get("value"),
        "Covenant Bookmarks": cur.get("covenant_bookmarks", {}).get("value"),
        "Powder of Knowledge": cur.get("powder_of_knowledge", {}).get("value"),
        "MolaGora": inv.get("growth_ingredients", {}).get("molagora", {}).get("value"),
        "Friendship": cur.get("friendship_points", {}).get("value"),
        "Stigma": cur.get("stigma", {}).get("value"),
        "Leif": cur.get("leif", {}).get("value"),
    }

    comps_doc = json.loads((REPO / "meta" / "pve" / "comps.json").read_text())
    owned_names = {h["name"] for h in d.heroes}
    comps = []
    for c in comps_doc["comps"]:
        if c.get("kind") == "specialty_change" or \
                c["title"].lower().startswith("specialty change"):
            continue
        teams = []
        for t in c["teams"]:
            teams.append([
                {"name": h["name"] or h["slug"], "owned": h["name"] in owned_names}
                for h in t
            ])
        comps.append({"title": c["title"], "tags": c["content_tags"],
                      "url": c["source_url"], "teams": teams})

    no_set = [b["name"] for b in builds if not b["sets"]]
    by_role = defaultdict(int)
    for b in builds:
        by_role[b["role"] or "?"] += 1

    return {
        "roster": len(d.heroes), "built": len(builds), "gear": len(scores),
        "reforge_pending": len(reforge_pending),
        "reforge_gain": round(sum(r["reforge_gain"] for r in reforge_pending)),
        "no_set": no_set,
        "role_counts": dict(sorted(by_role.items(), key=lambda kv: -kv[1])),
        "resources": resources,
        "heroes": [{
            "name": b["name"], "role": b["role"], "wss": b["total_wss"],
            "spd": b["spd"], "cr": b["cr"], "cd": b["cd"],
            "sets": "+".join(b["sets"]) or "—",
            "no_set": not b["sets"],
            "meta_wr": b.get("meta_wr"),
            "meta_build": "+".join(CODE_TO_NAME.get(c, c) for c in
                                   (b.get("meta_top_build") or "").split("+") if c) or None,
            "aligned": b.get("set_aligned"),
        } for b in sorted(builds, key=lambda b: -b["total_wss"])],
        "top_gear": [{
            "gear": r["gear"], "set": r["set"].replace("Set", ""),
            "main": r["main"], "wss": r["reforge_wss"], "enh": r["enhance"],
            "by": r["equipped_by"] or "spare",
        } for r in top_gear],
        "comps": comps,
    }


def esc(s):
    return _html.escape(str(s)) if s is not None else ""


def render(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return TEMPLATE.replace("/*DATA*/", payload)


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
  --gold:#b4832a; --good:#2f9e6b; --warn:#c78a1e; --crit:#c9524c;
  --shadow:0 1px 2px rgba(20,24,40,.06),0 4px 16px rgba(20,24,40,.06);
}
:root:not([data-theme="light"]){}
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
.wrap{max-width:1120px;margin:0 auto;padding:28px 20px 80px}
header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:4px}
h1{font-size:26px;margin:0;letter-spacing:-.02em;font-weight:700}
.sub{color:var(--muted);font-size:13.5px}
.tabs{display:flex;gap:4px;flex-wrap:wrap;margin:22px 0 20px;border-bottom:1px solid var(--border)}
.tab{appearance:none;background:none;border:0;color:var(--muted);font:inherit;
  font-weight:600;padding:9px 14px;cursor:pointer;border-bottom:2px solid transparent;
  margin-bottom:-1px;border-radius:6px 6px 0 0}
.tab:hover{color:var(--text);background:var(--surface-2)}
.tab[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent)}
.tab:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.panel{display:none}.panel.on{display:block;animation:f .18s ease}
@keyframes f{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){.panel.on{animation:none}}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:22px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:14px 16px;box-shadow:var(--shadow)}
.card .k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}
.card .v{font-size:24px;font-weight:700;margin-top:3px;font-variant-numeric:tabular-nums}
.card .v small{font-size:13px;color:var(--muted);font-weight:600}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:720px){.grid2{grid-template-columns:1fr}}
.block{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:16px 18px;box-shadow:var(--shadow);margin-bottom:18px}
.block h2{font-size:15px;margin:0 0 12px;letter-spacing:-.01em}
.tools{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
input[type=search],select{background:var(--surface);color:var(--text);border:1px solid var(--border);
  border-radius:8px;padding:8px 11px;font:inherit}
input[type=search]{min-width:200px;flex:1}
input:focus,select:focus{outline:2px solid var(--accent);outline-offset:1px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
.scroll{overflow-x:auto}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--border);white-space:nowrap}
th{color:var(--muted);font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;
  cursor:pointer;user-select:none;position:sticky;top:0;background:var(--surface)}
th.num,td.num{text-align:right;font-variant-numeric:tabular-nums}
tbody tr:hover{background:var(--surface-2)}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11.5px;font-weight:600;
  border:1px solid transparent}
.pill.good{color:var(--good);background:color-mix(in srgb,var(--good) 14%,transparent)}
.pill.warn{color:var(--warn);background:color-mix(in srgb,var(--warn) 16%,transparent)}
.pill.mut{color:var(--muted);background:var(--surface-2)}
.pill.acc{color:var(--accent);background:var(--accent-soft)}
.bar{height:6px;border-radius:3px;background:var(--surface-2);overflow:hidden;min-width:60px}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--gold))}
.team{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
.hchip{padding:3px 9px;border-radius:8px;font-size:12.5px;border:1px solid var(--border);background:var(--surface-2)}
.hchip.owned{border-color:var(--good);color:var(--good);background:color-mix(in srgb,var(--good) 10%,transparent)}
.note{color:var(--muted);font-size:12.5px;margin-top:8px}
.toggle{margin-left:auto;background:var(--surface);border:1px solid var(--border);color:var(--muted);
  border-radius:8px;padding:7px 11px;font:inherit;cursor:pointer}
.toggle:hover{color:var(--text)}
a{color:var(--accent)}
.tag{font-size:11px;color:var(--gold);border:1px solid color-mix(in srgb,var(--gold) 40%,transparent);
  border-radius:6px;padding:1px 6px;margin-right:4px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Astromancer</h1>
    <span class="sub" id="stamp"></span>
    <button class="toggle" id="themeBtn" type="button">Theme</button>
  </header>
  <div class="sub">Your Epic Seven account, browsable. Snapshot from the repo data — regenerate with <code>python scripts/build_dashboard.py</code>.</div>

  <nav class="tabs" role="tablist">
    <button class="tab" role="tab" data-p="overview" aria-selected="true">Overview</button>
    <button class="tab" role="tab" data-p="heroes" aria-selected="false">Heroes</button>
    <button class="tab" role="tab" data-p="gear" aria-selected="false">Gear</button>
    <button class="tab" role="tab" data-p="pve" aria-selected="false">PvE comps</button>
  </nav>

  <section class="panel on" id="overview"></section>
  <section class="panel" id="heroes"></section>
  <section class="panel" id="gear"></section>
  <section class="panel" id="pve"></section>
</div>

<script id="data" type="application/json">/*DATA*/</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const fmt=n=>n==null?'—':n.toLocaleString();
const el=(h)=>{const t=document.createElement('template');t.innerHTML=h.trim();return t.content.firstChild};

// theme toggle (cycles system -> dark -> light)
const root=document.documentElement, tb=document.getElementById('themeBtn');
tb.onclick=()=>{const c=root.getAttribute('data-theme');
  root.setAttribute('data-theme', c==='dark'?'light':(c==='light'?'':'dark'));
  if(!root.getAttribute('data-theme'))root.removeAttribute('data-theme');};

// --- Overview ---
function overview(){
  const r=D.resources;
  const resRows=Object.entries(r).map(([k,v])=>`<tr><td>${k}</td><td class="num">${fmt(v)}</td></tr>`).join('');
  const roles=Object.entries(D.role_counts).map(([k,v])=>`<span class="pill mut">${k} ${v}</span>`).join(' ');
  const noset=D.no_set.map(n=>`<span class="pill warn">${n}</span>`).join(' ')||'<span class="pill good">none</span>';
  return `
  <div class="cards">
    <div class="card"><div class="k">Roster</div><div class="v">${D.roster}</div></div>
    <div class="card"><div class="k">Built (6 gear)</div><div class="v">${D.built}</div></div>
    <div class="card"><div class="k">Gear pieces</div><div class="v">${fmt(D.gear)}</div></div>
    <div class="card"><div class="k">Reforge-pending</div><div class="v">${D.reforge_pending} <small>+${D.reforge_gain} WSS</small></div></div>
  </div>
  <div class="grid2">
    <div class="block"><h2>Highest-value fixes</h2>
      <p style="margin:.2em 0 .6em">These help in every mode, no new data needed:</p>
      <p><b>Reforge ${D.reforge_pending} lv85 pieces</b> — ~+${D.reforge_gain} WSS total, gold only.</p>
      <p><b>No active set bonus:</b> ${noset}<br><span class="note">Run <code>scripts/allocate.py "&lt;hero&gt;"</code> to re-slot from spare gear.</span></p>
    </div>
    <div class="block"><h2>Resources on hand</h2>
      <div class="scroll"><table><tbody>${resRows}</tbody></table></div>
    </div>
  </div>
  <div class="block"><h2>Role coverage (built heroes)</h2><div>${roles}</div>
    <p class="note">All-mode readiness: each role has options. Targeting per-PvE-mode needs comp thresholds (prose-only on epic7db) — team comps are in the PvE tab.</p>
  </div>`;
}

// --- Heroes (sortable/searchable) ---
let hSort={k:'wss',dir:-1};
function heroesPanel(){
  const p=document.getElementById('heroes');
  p.innerHTML=`<div class="block"><div class="tools">
    <input type="search" id="hq" placeholder="Search hero or set…">
    <select id="hrole"><option value="">All roles</option></select>
    <select id="hfilter"><option value="">All</option><option value="noset">No set bonus</option>
      <option value="meta">In RTA meta</option><option value="misaligned">Meta set mismatch</option></select>
    <span class="pill mut" id="hcount"></span></div>
    <div class="scroll"><table id="htab"><thead><tr>
      <th data-k="name">Hero</th><th data-k="role">Role</th><th class="num" data-k="wss">WSS</th>
      <th class="num" data-k="spd">Spd</th><th class="num" data-k="cr">CR</th><th class="num" data-k="cd">CD</th>
      <th data-k="sets">Sets</th><th class="num" data-k="meta_wr">RTA WR</th><th data-k="meta_build">Meta build</th>
    </tr></thead><tbody></tbody></table></div>
    <p class="note">WSS = total reforge-projected weighted substat score across 6 pieces. RTA WR only exists for meta heroes; "gap" is set-vs-meta, not stat-vs-target (no stat targets in data yet).</p></div>`;
  const roleSel=p.querySelector('#hrole');
  [...new Set(D.heroes.map(h=>h.role))].filter(Boolean).sort().forEach(r=>roleSel.append(el(`<option>${r}</option>`)));
  const draw=()=>{
    const q=p.querySelector('#hq').value.toLowerCase(), role=roleSel.value, f=p.querySelector('#hfilter').value;
    let rows=D.heroes.filter(h=>{
      if(role&&h.role!==role)return false;
      if(q&&!(h.name.toLowerCase().includes(q)||h.sets.toLowerCase().includes(q)))return false;
      if(f==='noset'&&!h.no_set)return false;
      if(f==='meta'&&h.meta_wr==null)return false;
      if(f==='misaligned'&&!(h.meta_build&&!h.aligned))return false;
      return true;});
    rows.sort((a,b)=>{const k=hSort.k;let x=a[k],y=b[k];
      if(x==null)x=-Infinity;if(y==null)y=-Infinity;
      return (x<y?-1:x>y?1:0)*hSort.dir;});
    const maxw=Math.max(...D.heroes.map(h=>h.wss));
    p.querySelector('#hcount').textContent=rows.length+' heroes';
    p.querySelector('tbody').innerHTML=rows.map(h=>{
      const wr=h.meta_wr!=null?(h.meta_wr*100).toFixed(1)+'%':'—';
      const al=h.aligned?'<span class="pill good">✓</span>':(h.meta_build?'<span class="pill warn">≠</span>':'');
      const setc=h.no_set?`<span class="pill warn">${h.sets}</span>`:h.sets;
      return `<tr><td>${h.name}</td><td>${h.role||'?'}</td>
        <td class="num"><div style="display:flex;gap:8px;align-items:center;justify-content:flex-end">${h.wss.toFixed(0)}<span class="bar" style="width:52px"><i style="width:${h.wss/maxw*100}%"></i></span></div></td>
        <td class="num">${h.spd}</td><td class="num">${h.cr}</td><td class="num">${h.cd}</td>
        <td>${setc}</td><td class="num">${wr}</td><td>${h.meta_build?h.meta_build+' '+al:'—'}</td></tr>`;
    }).join('');
  };
  p.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{
    const k=th.dataset.k; hSort.dir=(hSort.k===k)?-hSort.dir:(['name','role','sets','meta_build'].includes(k)?1:-1);
    hSort.k=k; draw();});
  p.querySelector('#hq').oninput=draw; roleSel.onchange=draw; p.querySelector('#hfilter').onchange=draw;
  draw();
}

// --- Gear ---
function gearPanel(){
  const rows=D.top_gear.map(g=>`<tr><td class="num">${g.wss.toFixed(1)}</td><td>${g.gear}</td>
    <td>${g.set}</td><td>${g.main}</td><td class="num">+${g.enh}</td>
    <td>${g.by==='spare'?'<span class="pill mut">spare</span>':g.by}</td></tr>`).join('');
  document.getElementById('gear').innerHTML=`
  <div class="cards">
    <div class="card"><div class="k">Reforge-pending</div><div class="v">${D.reforge_pending}</div></div>
    <div class="card"><div class="k">Potential gain</div><div class="v">+${D.reforge_gain} <small>WSS</small></div></div>
    <div class="card"><div class="k">Total pieces</div><div class="v">${fmt(D.gear)}</div></div>
  </div>
  <div class="block"><h2>Top 25 pieces (reforge-projected WSS)</h2>
   <div class="scroll"><table><thead><tr><th class="num">WSS</th><th>Slot</th><th>Set</th><th>Main</th><th class="num">+</th><th>Equipped by</th></tr></thead>
   <tbody>${rows}</tbody></table></div></div>`;
}

// --- PvE ---
function pvePanel(){
  const cards=D.comps.map(c=>{
    const tags=(c.tags||[]).map(t=>`<span class="tag">${t}</span>`).join('');
    const teams=c.teams.map(t=>`<div class="team">${t.map(h=>`<span class="hchip${h.owned?' owned':''}">${h.name}</span>`).join('')}</div>`).join('');
    return `<div class="block"><h2>${c.title} ${tags}</h2>
      <div class="note" style="margin:0 0 4px">${c.teams.length} team(s) · <a href="${c.url}" target="_blank" rel="noopener">source</a> · green = you own the hero</div>
      ${teams}</div>`;
  }).join('');
  document.getElementById('pve').innerHTML=`
  <div class="block" style="background:var(--accent-soft);border-color:var(--accent)">
    <b>Hunt & endgame comps</b> harvested from epic7db guides. Team lists only — per-slot stat thresholds are prose on the source and aren't captured yet. Heroes you own are highlighted green.
  </div>${cards||'<div class="block">No comps harvested.</div>'}`;
}

// tabs
const panels={overview,heroes:heroesPanel,gear:gearPanel,pve:pvePanel};
document.getElementById('overview').innerHTML=overview();
let drawn={overview:1};
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.setAttribute('aria-selected','false'));
  document.querySelectorAll('.panel').forEach(x=>x.classList.remove('on'));
  t.setAttribute('aria-selected','true');
  const id=t.dataset.p; document.getElementById(id).classList.add('on');
  if(!drawn[id]){panels[id]();drawn[id]=1;}
});
</script>
</body>
</html>
"""


def main():
    data = gather()
    OUT.write_text(render(data))
    print(f"wrote {OUT.relative_to(REPO)} "
          f"({len(data['heroes'])} heroes, {len(data['comps'])} comps, "
          f"{OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
