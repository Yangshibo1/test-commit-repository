"""Draw an interactive 189-record VAST MC2 transfer-chain visualization."""
import json
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Mapping


def build_full_chain_html(src_dir: Path | str, org_chart_path: Path | str) -> str:
    src_path = Path(src_dir)
    node08 = _read_json(src_path / "node_08_similar_attempts.json")
    node04 = _read_json(src_path / "node_04_source_trace.json")
    org = _read_json(Path(org_chart_path))

    person_meta = _build_person_department_lookup(org)
    records = _build_189_records(node08, node04, person_meta)
    if len(records) != 189:
        raise ValueError(f"Expected 189 records, got {len(records)}")

    return _render_html(records)


def write_full_chain_html(src_dir: Path | str, org_chart_path: Path | str, output_path: Path | str) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_full_chain_html(src_dir, org_chart_path), encoding="utf-8")
    return output


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _build_person_department_lookup(org: Mapping[str, Any]) -> Dict[str, Dict[str, str]]:
    nodes = {node["id"]: node for node in org.get("nodes", [])}
    parent: Dict[str, str] = {}
    for edge in org.get("edges", []):
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            parent[target] = source

    lookup: Dict[str, Dict[str, str]] = {}
    for node_id, node in nodes.items():
        if not str(node_id).startswith("person:"):
            continue
        cur = node_id
        team = ""
        department = "Unknown"
        guard = 0
        while cur in parent and guard < 10:
            cur = parent[cur]
            cur_node = nodes.get(cur, {})
            if cur_node.get("type") == "team" and not team:
                team = str(cur_node.get("label", ""))
            if cur_node.get("type") == "department":
                department = str(cur_node.get("label", "Unknown"))
                break
            guard += 1
        lookup[node_id] = {
            "label": str(node.get("label", _person_label(node_id))),
            "title": str(node.get("title", "")),
            "team": team,
            "department": department,
        }
        lookup[f"Agent/{node_id}"] = lookup[node_id]
    return lookup


def _build_189_records(node08: Mapping[str, Any], node04: Mapping[str, Any], person_meta: Mapping[str, Mapping[str, str]]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for i, item in enumerate(node08.get("instruction_tasks", []), start=1):
        event = item.get("event", {})
        source = _normalize_person(item.get("source_agent"))
        target = _normalize_person(item.get("target_agent"))
        records.append({
            "index": i,
            "event_id": event.get("id"),
            "datetime": event.get("datetime"),
            "when": event.get("when"),
            "type": "queue_subordinate_task",
            "source": _person_label(source),
            "target": _person_label(target),
            "source_id": source,
            "target_id": target,
            "source_department": person_meta.get(source, {}).get("department", "Unknown"),
            "target_department": person_meta.get(target, {}).get("department", "Unknown"),
            "source_team": person_meta.get(source, {}).get("team", ""),
            "target_team": person_meta.get(target, {}).get("team", ""),
            "task": (event.get("details") or {}).get("task", "read_file"),
            "path": ((event.get("details") or {}).get("args") or {}).get("path", ""),
            "is_key": event.get("id") in {373882, 373893},
            "key_reason": "critical target-chain task" if event.get("id") in {373882, 373893} else "",
        })

    # Add the three non-delegation records that complete the 189-record visual chain:
    # source file creation, post check, and the target post.
    created = (node04.get("file_lifecycle", {}).get("created") or [{}])[0]
    target_post = node04.get("target_post", {})
    post_check = next((e for e in node04.get("task_chain_near_post", []) if e.get("short_name") == "saidit_post_check"), {})
    extras = [
        (created, "create_file", "Emma Harbor", "SwiftWren.txt", "file origin", True),
        (post_check, "saidit_post_check", "John Windward", "system:saidit", "pre-post check", True),
        (target_post, "saidit_post", "John Windward", "SaidIT general forum", "content_source=SwiftWren.txt", True),
    ]
    for event, event_type, source, target, task, is_key in extras:
        records.append({
            "index": len(records) + 1,
            "event_id": event.get("id"),
            "datetime": event.get("datetime"),
            "when": event.get("when"),
            "type": event_type,
            "source": source,
            "target": target,
            "source_id": _normalize_person(f"person:{source.lower().replace(' ', '_')}") if " " in source else source,
            "target_id": target,
            "source_department": "Executive Suite" if source == "Emma Harbor" else "Customer Support",
            "target_department": "File System" if "SwiftWren" in target else "SaidIT System",
            "source_team": "",
            "target_team": "",
            "task": task,
            "path": str((event.get("details") or {}).get("content_source", "")),
            "is_key": is_key,
            "key_reason": "key task",
        })
    return sorted(records, key=lambda r: (float(r.get("when") or 0), int(r.get("index") or 0)))


def _normalize_person(value: Any) -> str:
    text = str(value or "")
    text = text.replace("Agent/", "")
    if text.startswith("person:"):
        return text
    if "person:" in text:
        return text[text.index("person:"):]
    return text


def _person_label(person_id: str) -> str:
    raw = str(person_id).split(":")[-1]
    return " ".join(part.capitalize() for part in raw.split("_"))


def _render_html(records: List[Dict[str, Any]]) -> str:
    records_json = json.dumps(records, ensure_ascii=False)
    departments = sorted({r.get("source_department", "Unknown") for r in records} | {r.get("target_department", "Unknown") for r in records})
    department_json = json.dumps(departments, ensure_ascii=False)
    key_count = sum(1 for r in records if r.get("is_key"))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>VAST MC2 · 189 Record Transfer Chain</title>
<style>
  :root {{
    --bg:#15100c; --paper:#fff8ed; --ink:#2e241d; --muted:#7d6b5d; --line:#dcc6ae;
    --key:#dc3f32; --gold:#d3912c;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:radial-gradient(circle at 12% 0%, #5a331f, transparent 34rem), linear-gradient(135deg,#1d140e,#0f0b08); color:var(--paper); font-family:Georgia, 'Times New Roman', serif; }}
  main {{ max-width:1500px; margin:0 auto; padding:34px; }}
  header {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-start; margin-bottom:22px; }}
  h1 {{ margin:0; font-size:42px; line-height:.96; letter-spacing:-.045em; }}
  .subtitle {{ margin:10px 0 0; color:#d9c4af; max-width:900px; line-height:1.45; }}
  .stats {{ display:grid; grid-template-columns:repeat(3,140px); gap:10px; }}
  .stat {{ background:#fff8ed; color:var(--ink); border:1px solid #e7d3bd; border-radius:18px; padding:14px; text-align:center; }}
  .stat b {{ display:block; font-size:30px; color:#d97745; }}
  .stat span {{ font:11px ui-monospace, Consolas, monospace; color:var(--muted); }}
  .toolbar {{ background:rgba(255,248,237,.94); color:var(--ink); border:1px solid #e4ccb3; border-radius:24px; padding:14px; display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:14px; }}
  button, select, input {{ border:1px solid #ceb59c; background:#fff; color:var(--ink); border-radius:999px; padding:9px 12px; font:12px ui-monospace, Consolas, monospace; }}
  button {{ cursor:pointer; }} button.active {{ background:#2e241d; color:#fff8ed; }}
  .legend {{ display:flex; gap:8px; flex-wrap:wrap; margin-left:auto; }}
  .legend span {{ display:inline-flex; align-items:center; gap:6px; font:11px ui-monospace, Consolas, monospace; color:var(--muted); }}
  .legend i {{ width:11px; height:11px; border-radius:50%; display:inline-block; }}
  .viz-shell {{ background:var(--paper); color:var(--ink); border:1px solid #e4ccb3; border-radius:30px; padding:18px; box-shadow:0 28px 80px rgba(0,0,0,.35); }}
  #chain {{ position:relative; min-height:720px; overflow:auto; border-radius:22px; background:linear-gradient(90deg, rgba(217,119,69,.06), transparent), #fffdf8; border:1px solid #ead9c7; }}
  .row {{ display:grid; grid-template-columns:74px 170px 1fr 210px; gap:12px; align-items:center; min-height:62px; padding:9px 14px; border-bottom:1px solid rgba(220,198,174,.55); }}
  .row.hidden-middle {{ display:none; }}
  .idx {{ font:800 12px ui-monospace, Consolas, monospace; color:#8b735f; }}
  .time {{ font:11px ui-monospace, Consolas, monospace; color:#806d5d; }}
  .flow {{ display:grid; grid-template-columns:190px 1fr 190px; align-items:center; gap:8px; }}
  .person, .target {{ border-radius:16px; padding:10px; background:#fff; border:2px solid var(--dept-color, #aaa); box-shadow:0 8px 18px rgba(62,42,26,.08); }}
  .person b, .target b {{ display:block; font-size:14px; }}
  .person small, .target small {{ display:block; margin-top:3px; font:10px ui-monospace, Consolas, monospace; color:#806d5d; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .edge {{ position:relative; height:28px; border-top:3px solid #9b8978; }}
  .edge:after {{ content:''; position:absolute; right:-1px; top:-7px; width:0; height:0; border-left:12px solid #9b8978; border-top:6px solid transparent; border-bottom:6px solid transparent; }}
  .edge-label {{ position:absolute; left:50%; transform:translateX(-50%); top:-23px; background:#fffdf8; color:#6f6257; padding:2px 7px; border:1px solid #e3d0bd; border-radius:999px; font:10px ui-monospace, Consolas, monospace; white-space:nowrap; }}
  .meta {{ font:11px ui-monospace, Consolas, monospace; color:#806d5d; }}
  .key-task {{ background:linear-gradient(90deg, rgba(216,63,50,.16), rgba(255,248,237,.98)); }}
  .key-task .edge {{ border-top-color:var(--key); }} .key-task .edge:after {{ border-left-color:var(--key); }}
  .key-task .edge-label {{ color:#9e2f25; border-color:#e6a59d; }}
  .collapse-marker {{ text-align:center; padding:20px; background:#2e241d; color:#fff8ed; font:12px ui-monospace, Consolas, monospace; letter-spacing:.06em; }}
  .details {{ margin-top:14px; display:grid; grid-template-columns:1fr 330px; gap:14px; }}
  .panel {{ background:#fff8ed; color:var(--ink); border:1px solid #e4ccb3; border-radius:22px; padding:16px; }}
  .panel h3 {{ margin:0 0 10px; }}
  .mini-bars {{ display:grid; gap:7px; }}
  .bar {{ display:grid; grid-template-columns:150px 1fr 34px; gap:8px; align-items:center; font:11px ui-monospace, Consolas, monospace; }}
  .bar-track {{ height:12px; background:#ead9c7; border-radius:999px; overflow:hidden; }}
  .bar-fill {{ height:100%; background:var(--dept-color); }}
</style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>189-record SwiftWren transfer chain</h1>
      <p class="subtitle">Loaded {len(records)} real records from the VAST MC2 analysis data. The view starts with the first 5 and last 5 records; expand the middle to inspect the full transmission chain. People are color-coded by department. Key tasks are highlighted in red.</p>
    </div>
    <div class="stats"><div class="stat"><b>{len(records)}</b><span>real records</span></div><div class="stat"><b>{key_count}</b><span>key tasks</span></div><div class="stat"><b>{len(departments)}</b><span>departments/systems</span></div></div>
  </header>

  <section class="toolbar">
    <button id="toggleMiddle">Expand middle 179 records</button>
    <button id="showKey">Show key tasks only</button>
    <button id="reset" class="active">First 5 + Last 5</button>
    <input id="search" placeholder="Search person, event id, task..." />
    <select id="department"><option value="">All departments</option></select>
    <div class="legend" id="legend"></div>
  </section>

  <section class="viz-shell">
    <div id="chain"></div>
  </section>

  <section class="details">
    <div class="panel"><h3>Department activity</h3><div id="bars" class="mini-bars"></div></div>
    <div class="panel"><h3>Interaction rule</h3><p style="color:#7d6b5d;line-height:1.45">Initial state shows the edges of the sequence to preserve readability. Expand middle records to reveal all 189 time-ordered interactions. Red rows mark key events near the target post or the final SaidIT output.</p></div>
  </section>
</main>
<script>
const RECORDS = {records_json};
const DEPARTMENTS = {department_json};
const COLORS = {{
  "Executive Suite":"#d97745", "Products":"#7c3aed", "Human Resources":"#db2777", "Legal":"#ca8a04",
  "Information Technologies":"#16a34a", "Customer Support":"#2563eb", "SaidIT System":"#dc2626", "File System":"#64748b", "Unknown":"#78716c"
}};
let showMiddle = false;
let keyOnly = false;
const chain = document.getElementById('chain');
const deptSelect = document.getElementById('department');
const search = document.getElementById('search');

DEPARTMENTS.forEach(d => {{ const opt = document.createElement('option'); opt.value = d; opt.textContent = d; deptSelect.appendChild(opt); }});
document.getElementById('legend').innerHTML = DEPARTMENTS.map(d => `<span><i style="background:${{COLORS[d]||COLORS.Unknown}}"></i>${{d}}</span>`).join('');

document.getElementById('toggleMiddle').onclick = () => {{ showMiddle = !showMiddle; keyOnly = false; render(); }};
document.getElementById('showKey').onclick = () => {{ keyOnly = !keyOnly; render(); }};
document.getElementById('reset').onclick = () => {{ showMiddle = false; keyOnly = false; search.value = ''; deptSelect.value = ''; render(); }};
search.oninput = render; deptSelect.onchange = render;

function visibleRecords() {{
  const q = search.value.trim().toLowerCase();
  const dept = deptSelect.value;
  return RECORDS.filter((r, i) => {{
    const edgeVisible = showMiddle || i < 5 || i >= RECORDS.length - 5;
    if (!edgeVisible && !keyOnly) return false;
    if (keyOnly && !r.is_key) return false;
    if (dept && r.source_department !== dept && r.target_department !== dept) return false;
    if (q) {{
      const hay = `${{r.event_id}} ${{r.datetime}} ${{r.type}} ${{r.source}} ${{r.target}} ${{r.task}} ${{r.path}} ${{r.source_department}} ${{r.target_department}}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }}
    return true;
  }});
}}

function render() {{
  const visible = visibleRecords();
  const rows = [];
  visible.forEach((r, n) => {{
    const sourceColor = COLORS[r.source_department] || COLORS.Unknown;
    const targetColor = COLORS[r.target_department] || COLORS.Unknown;
    const cls = r.is_key ? 'row key-task' : 'row';
    rows.push(`<div class="${{cls}}">
      <div class="idx">#${{String(r.index).padStart(3,'0')}}<br><span class="time">${{r.event_id||''}}</span></div>
      <div class="time">${{r.datetime||''}}</div>
      <div class="flow">
        <div class="person" style="--dept-color:${{sourceColor}}"><b>${{escapeHtml(r.source)}}</b><small>${{escapeHtml(r.source_department)}}${{r.source_team ? ' · '+escapeHtml(r.source_team) : ''}}</small></div>
        <div class="edge"><span class="edge-label">${{escapeHtml(r.type)}} · ${{escapeHtml(r.task||'')}}</span></div>
        <div class="target" style="--dept-color:${{targetColor}}"><b>${{escapeHtml(r.target)}}</b><small>${{escapeHtml(r.target_department)}}${{r.target_team ? ' · '+escapeHtml(r.target_team) : ''}}</small></div>
      </div>
      <div class="meta">${{escapeHtml(r.path || r.key_reason || '')}}</div>
    </div>`);
    if (!showMiddle && !keyOnly && n === 4 && visible.length > 10) rows.push(`<div class="collapse-marker">middle records collapsed · click “Expand middle 179 records” to show the full 189-record chain</div>`);
  }});
  chain.innerHTML = rows.join('');
  document.getElementById('toggleMiddle').textContent = showMiddle ? 'Collapse middle records' : 'Expand middle 179 records';
  document.getElementById('showKey').classList.toggle('active', keyOnly);
  document.getElementById('reset').classList.toggle('active', !showMiddle && !keyOnly && !search.value && !deptSelect.value);
  renderBars();
}}

function renderBars() {{
  const counts = {{}};
  RECORDS.forEach(r => {{ counts[r.source_department] = (counts[r.source_department]||0)+1; counts[r.target_department] = (counts[r.target_department]||0)+1; }});
  const max = Math.max(...Object.values(counts));
  document.getElementById('bars').innerHTML = Object.entries(counts).sort((a,b)=>b[1]-a[1]).map(([d,c]) => `<div class="bar"><span>${{d}}</span><div class="bar-track"><div class="bar-fill" style="width:${{c/max*100}}%;--dept-color:${{COLORS[d]||COLORS.Unknown}}"></div></div><b>${{c}}</b></div>`).join('');
}}
function escapeHtml(s) {{ return String(s ?? '').replace(/[&<>'"]/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}}[ch])); }}
render();
</script>
</body>
</html>"""


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    out = base / "report_question_visualizations" / "q_full_189_transfer_chain.html"
    write_full_chain_html(base / "src", base / "org_chart.json", out)
    print(out)


if __name__ == "__main__":
    main()
