"""
Core VAST MC2 visualization artifact generator.

Builds focused HTML visualizations for the challenge questions from the
analysis JSON files under VAST_Challenge_2026_MC2/src. The output shape is
compatible with the OpenTrace frontend Inspector visualization tab.
"""
import json
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping


Artifact = Dict[str, Any]


def build_core_visualization_artifacts(src_dir: Path | str) -> Dict[str, Artifact]:
    src_path = Path(src_dir)
    node04 = _read_json(src_path / "node_04_source_trace.json")
    node09 = _read_json(src_path / "node_09_instruction_outcome_comparison.json")
    node12 = _read_json(src_path / "node_12_john_all_posts_analysis.json")
    node20 = _read_json(src_path / "node_20_content_and_creator_verification.json")
    node24 = _read_json(src_path / "node_24_system_change_recommendations.json")
    node25 = _read_json(src_path / "node_25_final_investigation_summary.json")

    artifacts = {
        "node_04_source_trace": _node04_route_and_timeline(node04),
        "node_09_instruction_outcome_comparison": _node09_recurrence_matrix(node09, node12, node20),
        "node_12_john_all_posts_analysis": _node12_posting_behavior(node12),
        "node_20_content_and_creator_verification": _node20_content_autopsy(node04, node20),
        "node_24_system_change_recommendations": _node24_intervention_gate(node24, node12),
        "node_25_final_investigation_summary": _node25_summary_dashboard(node25, node04, node12),
    }
    return artifacts


def write_core_visualization_artifacts(src_dir: Path | str, output_dir: Path | str) -> Dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    written: Dict[str, Path] = {}
    for key, artifact in build_core_visualization_artifacts(src_dir).items():
        target = output_path / f"{key}.analysis.json"
        target.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        written[key] = target
    return written


def write_standalone_html_visualizations(src_dir: Path | str, output_dir: Path | str) -> Dict[str, Path]:
    """Write browser-openable HTML files for standalone preview."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    written: Dict[str, Path] = {}
    artifacts = build_core_visualization_artifacts(src_dir)
    for key, artifact in artifacts.items():
        target = output_path / f"{key}.html"
        target.write_text(_standalone_html(artifact), encoding="utf-8")
        written[key] = target

    index = output_path / "index.html"
    index.write_text(_standalone_index(artifacts), encoding="utf-8")
    written["index"] = index
    return written


def write_report_question_visualizations(src_dir: Path | str, output_dir: Path | str) -> Dict[str, Path]:
    """Write exactly one standalone HTML visualization for each report question."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    artifacts = build_report_question_visualization_artifacts(src_dir)
    written: Dict[str, Path] = {}
    for key, artifact in artifacts.items():
        target = output_path / f"{key}.html"
        target.write_text(_standalone_html(artifact), encoding="utf-8")
        written[key] = target
    index = output_path / "index.html"
    index.write_text(_standalone_index(artifacts), encoding="utf-8")
    written["index"] = index
    return written


def build_report_question_visualization_artifacts(src_dir: Path | str) -> Dict[str, Artifact]:
    """Build six report-question visualizations, independent from analysis-node naming."""
    src_path = Path(src_dir)
    node04 = _read_json(src_path / "node_04_source_trace.json")
    node09 = _read_json(src_path / "node_09_instruction_outcome_comparison.json")
    node12 = _read_json(src_path / "node_12_john_all_posts_analysis.json")
    node20 = _read_json(src_path / "node_20_content_and_creator_verification.json")
    node24 = _read_json(src_path / "node_24_system_change_recommendations.json")
    node25 = _read_json(src_path / "node_25_final_investigation_summary.json")
    return {
        "q1_how_posts_made": _q1_how_posts_made(node04),
        "q2_detailed_event_chain": _q2_detailed_event_chain(node04),
        "q3_system_overview": _q3_system_overview(node04, node09, node12, node25),
        "q4_post_meaning_origin": _q4_post_meaning_origin(node04, node20),
        "q5_historic_recurrence": _q5_historic_recurrence(node09, node12, node20),
        "q6_intervention_point": _q6_intervention_point(node24, node12),
    }


def _q1_how_posts_made(node04: Mapping[str, Any]) -> Artifact:
    source = escape(str(node04.get("content_source", "SwiftWren.txt")))
    target = node04.get("target_post", {})
    body = f"""
    <div class="visual-question">How was the anomalous SaidIT post made?</div>
    <svg class="question-svg" viewBox="0 0 1180 520" role="img" aria-label="Route map showing people, file, system actions, and anomalous output">
      <defs>
        <marker id="q1arrow" markerWidth="11" markerHeight="11" refX="9" refY="4" orient="auto"><path d="M0,0 L0,8 L10,4 z" fill="#6f6257"/></marker>
        <marker id="q1red" markerWidth="11" markerHeight="11" refX="9" refY="4" orient="auto"><path d="M0,0 L0,8 L10,4 z" fill="#d84a3a"/></marker>
        <filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#3b2415" flood-opacity="0.16"/></filter>
      </defs>
      <rect x="28" y="45" width="1124" height="398" rx="28" fill="#fff8ee" stroke="#dcc8b5"/>
      <text x="52" y="86" class="svg-kicker">ROUTE MAP · PEOPLE + FILE + SYSTEM INTERACTIONS</text>
      <text x="52" y="116" class="svg-title">Target post {escape(str(target.get('id', '373902')))} is produced by a cross-person task route ending in a SaidIT content-source fault</text>

      <g filter="url(#softShadow)">
        <rect x="60" y="175" width="130" height="88" rx="20" fill="#fff1df" stroke="#d97745" stroke-width="2"/>
        <text x="125" y="211" text-anchor="middle" class="svg-node-title">Emma Harbor</text>
        <text x="125" y="235" text-anchor="middle" class="svg-node-sub">creates file</text>

        <rect x="245" y="170" width="145" height="98" rx="18" fill="#eaf6ff" stroke="#2f80c1" stroke-width="2"/>
        <path d="M274 187 H344 L364 207 V251 H274 Z" fill="#ffffff" stroke="#2f80c1"/>
        <path d="M344 187 V207 H364" fill="none" stroke="#2f80c1"/>
        <text x="318" y="230" text-anchor="middle" class="svg-node-title">{source}</text>
        <text x="318" y="251" text-anchor="middle" class="svg-node-sub">content source</text>

        <rect x="448" y="175" width="135" height="88" rx="20" fill="#f0fbf4" stroke="#3c9d70" stroke-width="2"/>
        <text x="515" y="211" text-anchor="middle" class="svg-node-title">Daniel</text>
        <text x="515" y="235" text-anchor="middle" class="svg-node-sub">assigns Chloe</text>

        <rect x="642" y="175" width="135" height="88" rx="20" fill="#f0fbf4" stroke="#3c9d70" stroke-width="2"/>
        <text x="710" y="211" text-anchor="middle" class="svg-node-title">Chloe</text>
        <text x="710" y="235" text-anchor="middle" class="svg-node-sub">delegates John</text>

        <rect x="835" y="175" width="135" height="88" rx="20" fill="#eaf2ff" stroke="#376fae" stroke-width="2"/>
        <text x="902" y="211" text-anchor="middle" class="svg-node-title">John</text>
        <text x="902" y="235" text-anchor="middle" class="svg-node-sub">executes post</text>

        <rect x="835" y="330" width="135" height="72" rx="18" fill="#f7f7fa" stroke="#64748b" stroke-width="2"/>
        <text x="902" y="360" text-anchor="middle" class="svg-node-title">saidit_post</text>
        <text x="902" y="383" text-anchor="middle" class="svg-node-sub">forum=general</text>

        <path d="M1045 326 C1095 326 1122 354 1122 384 C1122 420 1085 442 1036 431 L1005 450 L1014 420 C986 407 974 390 974 370 C974 344 1004 326 1045 326 Z" fill="#fff1ef" stroke="#d84a3a" stroke-width="3"/>
        <text x="1048" y="371" text-anchor="middle" class="svg-node-title" fill="#9e2f25">EMPTY POST</text>
        <text x="1048" y="394" text-anchor="middle" class="svg-node-sub">content = ""</text>
      </g>

      <path d="M190 219 H245" stroke="#6f6257" stroke-width="3" marker-end="url(#q1arrow)"/>
      <path d="M390 219 H448" stroke="#6f6257" stroke-width="3" marker-end="url(#q1arrow)"/>
      <path d="M583 219 H642" stroke="#6f6257" stroke-width="3" marker-end="url(#q1arrow)"/>
      <path d="M777 219 H835" stroke="#6f6257" stroke-width="3" marker-end="url(#q1arrow)"/>
      <path d="M902 263 V330" stroke="#6f6257" stroke-width="3" marker-end="url(#q1arrow)"/>
      <path d="M970 366 H1002" stroke="#d84a3a" stroke-width="5" marker-end="url(#q1red)"/>
      <path d="M318 268 C420 345 650 390 835 366" stroke="#2f80c1" stroke-width="3" stroke-dasharray="9 7" fill="none"/>
      <text x="480" y="350" class="svg-label" fill="#2f80c1">content_source reference</text>
      <path d="M528 388 C690 455 902 458 1024 426" stroke="#d84a3a" stroke-width="4" stroke-dasharray="12 8" fill="none"/>
      <text x="650" y="454" class="svg-label" fill="#d84a3a">expected file text → post body is missing</text>
    </svg>
    <div class="legend-row"><span class="legend person-dot">person</span><span class="legend file-dot">file</span><span class="legend task-dot">task delegation</span><span class="legend anomaly-dot">anomaly</span></div>
    """
    return _artifact("Q1 · How was the anomalous SaidIT post made?", "Visual route map of the people, source file, task delegation, and SaidIT system interaction that produced the post.", body)


def _q2_detailed_event_chain(node04: Mapping[str, Any]) -> Artifact:
    created = (node04.get("file_lifecycle", {}).get("created") or [{}])[0]
    events = [created, *node04.get("task_chain_near_post", [])]
    rows = []
    lane_order = ["Emma Harbor", "Daniel Gangway", "Chloe Ballast", "John Windward", "SaidIT / File System"]
    for event in events:
        if not event:
            continue
        actor = _event_actor(event)
        lane = actor if actor in lane_order else "SaidIT / File System"
        if event.get("short_name") in {"saidit_post", "saidit_post_check", "delete_file"}:
            lane = "John Windward" if "john_windward" in " ".join(map(str, event.get("parties", []))) else lane
        cls = "anomaly" if event.get("short_name") == "saidit_post" else ("system" if "saidit" in " ".join(map(str, event.get("parties", []))) else "task")
        rows.append(
            f"<div class='timeline-row'><div class='time'>{escape(str(event.get('datetime','unknown')))}</div>"
            f"<div class='lane'>{escape(lane)}</div><div class='vast-node {cls}'><strong>{escape(str(event.get('short_name','event')))}</strong>"
            f"<span>{escape(_details_text(event.get('details') or {}))}</span></div></div>"
        )
    body = f"""
    <p class="vast-subtitle">Exact chain of events for the message of interest, with the target post highlighted at the moment content_source becomes an empty public post.</p>
    <div class="vast-grid" style="grid-template-columns:repeat(5,1fr); margin:12px 0;">{''.join(f'<div class="vast-chip">{escape(l)}</div>' for l in lane_order)}</div>
    <div class="timeline">{''.join(rows)}</div>
    <div class="fault" style="margin-top:14px"><strong>Critical second:</strong> 2046-05-17 19:21:15 · John Windward calls saidit_post with content_source=SwiftWren.txt; the resulting post body is empty.</div>
    """
    extra_css = ".timeline{display:grid;gap:8px}.timeline-row{display:grid;grid-template-columns:170px 150px 1fr;gap:10px;align-items:center}.time,.lane{font:11px ui-monospace,Consolas,monospace;color:var(--muted)}"
    return _artifact("Q2 · Exact chain of events", "A swimlane-style event timeline focused on the exact message chain.", body | SafeStr if False else body)


def _q3_system_overview(node04: Mapping[str, Any], node09: Mapping[str, Any], node12: Mapping[str, Any], node25: Mapping[str, Any]) -> Artifact:
    summary = node09.get("summary", {})
    body = f"""
    <p class="vast-subtitle">System overview that contextualizes the message chain inside organization roles, task delegation, file handling, and SaidIT posting behavior.</p>
    <div class="vast-grid" style="grid-template-columns:repeat(4,1fr); margin:14px 0;">
      <div class="vast-card"><div class="vast-kicker">Executive / Finance</div><div class="vast-node person" style="margin-top:10px"><strong>Emma Harbor</strong><span>creates SwiftWren.txt</span></div></div>
      <div class="vast-card"><div class="vast-kicker">IT / Infrastructure</div><div class="vast-node person" style="margin-top:10px"><strong>Chloe Ballast / Lily Anchorline</strong><span>instruction sources in anomalous cases</span></div></div>
      <div class="vast-card"><div class="vast-kicker">Customer Support</div><div class="vast-node person" style="margin-top:10px"><strong>John Windward</strong><span>only observed abnormal poster</span></div></div>
      <div class="vast-card"><div class="vast-kicker">SaidIT System</div><div class="vast-node anomaly" style="margin-top:10px"><strong>saidit_post</strong><span>shared convergence point</span></div></div>
    </div>
    <div class="vast-grid" style="grid-template-columns:repeat(4,1fr); margin-bottom:14px;">
      <div class="metric"><b>{escape(str(summary.get('instruction_tasks', 186)))}</b><span>related instruction tasks</span></div>
      <div class="metric"><b>{escape(str(node12.get('john_saidit_activity', {}).get('total_posts', 45)))}</b><span>John SaidIT posts</span></div>
      <div class="metric"><b>{escape(str(node12.get('john_saidit_activity', {}).get('abnormal_posts', 3)))}</b><span>John anomalous posts</span></div>
      <div class="metric"><b>{escape(str(node25.get('key_findings', {}).get('historical_instances', 3)))}</b><span>recurring instances</span></div>
    </div>
    <div class="vast-card"><strong>Contextual claim</strong><p style="color:var(--muted);line-height:1.45">The target chain crosses organizational boundaries but the observed failure converges in one system module: saidit_post. The full system contains many instruction tasks, but only the John → SaidIT content_source pattern produces the empty-post anomaly.</p></div>
    """
    return _artifact("Q3 · System overview", "A clustered overview placing the target message chain in the larger system.", body)


def _q4_post_meaning_origin(node04: Mapping[str, Any], node20: Mapping[str, Any]) -> Artifact:
    artifact = _node20_content_autopsy(node04, node20)
    artifact["visualization_title"] = "Q4 · What do the posts mean? What is the origin of their contents?"
    artifact["visualization_summary"] = "Evidence autopsy showing content_source origin, empty published body, and the reasoning behind the malfunction interpretation."
    artifact["description"] = artifact["visualization_summary"]
    artifact["visualization"] = artifact["visualization"].replace("Content Origin Autopsy", "Q4 · What do the posts mean? What is the origin of their contents?")
    return artifact


def _q5_historic_recurrence(node09: Mapping[str, Any], node12: Mapping[str, Any], node20: Mapping[str, Any]) -> Artifact:
    artifact = _node09_recurrence_matrix(node09, node12, node20)
    artifact["visualization_title"] = "Q5 · Historic recurrence and contrast"
    artifact["visualization_summary"] = "A recurrence matrix illustrating prior instances and contrasting them with the latest SwiftWren case."
    artifact["description"] = artifact["visualization_summary"]
    artifact["visualization"] = artifact["visualization"].replace("Historical Recurrence Matrix", "Q5 · Historic recurrence and contrast")
    return artifact


def _q6_intervention_point(node24: Mapping[str, Any], node12: Mapping[str, Any]) -> Artifact:
    artifact = _node24_intervention_gate(node24, node12)
    artifact["visualization_title"] = "Q6 · Intervention point"
    artifact["visualization_summary"] = "A before/after intervention diagram showing why saidit_post validation is the best single control point."
    artifact["description"] = artifact["visualization_summary"]
    artifact["visualization"] = artifact["visualization"].replace("Intervention Gate Simulation", "Q6 · Intervention point")
    return artifact


def _standalone_html(artifact: Mapping[str, Any]) -> str:
    title = escape(str(artifact.get("visualization_title", "VAST Visualization")))
    summary = escape(str(artifact.get("visualization_summary", "")))
    visualization = str(artifact.get("visualization", ""))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>
    body {{ margin:0; padding:32px; background:#221a14; color:#fffaf3; }}
    .page {{ max-width:1280px; margin:0 auto; }}
    .masthead {{ margin:0 0 22px; font-family:Georgia, 'Times New Roman', serif; }}
    .masthead h1 {{ margin:0; font-size:34px; letter-spacing:-.03em; }}
    .masthead p {{ margin:8px 0 0; max-width:860px; color:#d8c4b0; line-height:1.5; }}
  </style>
</head>
<body>
  <main class="page">
    <header class="masthead">
      <h1>{title}</h1>
      <p>{summary}</p>
    </header>
    {visualization}
  </main>
</body>
</html>
"""


def _standalone_index(artifacts: Mapping[str, Artifact]) -> str:
    cards = []
    for key, artifact in artifacts.items():
        title = escape(str(artifact.get("visualization_title", key)))
        summary = escape(str(artifact.get("visualization_summary", "")))
        cards.append(
            f"<a class='card' href='{escape(key)}.html'><span>{escape(key)}</span><strong>{title}</strong><p>{summary}</p></a>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>VAST MC2 Core Visualizations</title>
  <style>
    body {{ margin:0; min-height:100vh; padding:36px; background:radial-gradient(circle at top left,#5c3524,#201812 42%,#120e0b); color:#fffaf3; font-family:Georgia,'Times New Roman',serif; }}
    main {{ max-width:1180px; margin:0 auto; }}
    h1 {{ font-size:42px; line-height:1; margin:0 0 8px; letter-spacing:-.04em; }}
    .subtitle {{ color:#dbc7b4; margin:0 0 28px; max-width:820px; line-height:1.5; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; }}
    .card {{ display:block; text-decoration:none; color:#30251d; background:#fffaf3; border:1px solid #dcc8b5; border-radius:22px; padding:18px; box-shadow:0 22px 55px rgba(0,0,0,.24); transition:transform .18s ease, box-shadow .18s ease; }}
    .card:hover {{ transform:translateY(-4px); box-shadow:0 28px 70px rgba(0,0,0,.34); }}
    .card span {{ display:block; color:#d97745; font:700 11px ui-monospace,Consolas,monospace; text-transform:uppercase; letter-spacing:.12em; margin-bottom:10px; }}
    .card strong {{ display:block; font-size:22px; }}
    .card p {{ color:#7a6859; line-height:1.45; margin:8px 0 0; }}
  </style>
</head>
<body>
  <main>
    <h1>VAST MC2 Core Visualizations</h1>
    <p class="subtitle">Standalone HTML previews for the core challenge questions: route, timeline, system context, meaning, recurrence, and intervention.</p>
    <section class="grid">{''.join(cards)}</section>
  </main>
</body>
</html>
"""


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _person_label(agent_id: str | None) -> str:
    if not agent_id:
        return "Unknown"
    raw = agent_id.split(":")[-1]
    return " ".join(part.capitalize() for part in raw.split("_"))


def _event_actor(event: Mapping[str, Any], index: int = 0) -> str:
    parties = event.get("parties") or []
    if len(parties) > index:
        return _person_label(str(parties[index]))
    return "Unknown"


def _details_text(details: Mapping[str, Any] | None) -> str:
    if not details:
        return "—"
    parts = []
    for key, value in details.items():
        if isinstance(value, Mapping):
            value = ", ".join(f"{k}={v}" for k, v in value.items())
        parts.append(f"{key}: {value}")
    return " · ".join(parts)


def _wrap(title: str, body: str, extra_css: str = "") -> str:
    return f"""
<div class="vast-viz vast-cartography">
  <style>
    .vast-cartography {{
      --paper:#fffaf3; --panel:#fffdf8; --ink:#30251d; --muted:#7a6859;
      --line:#dcc8b5; --orange:#d97745; --blue:#2f80c1; --green:#3c9d70;
      --red:#d84a3a; --slate:#64748b; --gold:#b98225;
      color:var(--ink); font-family: ui-serif, Georgia, "Times New Roman", serif;
      background: radial-gradient(circle at 14% 6%, rgba(217,119,69,.10), transparent 22rem),
                  linear-gradient(135deg, #fffaf3, #fffdf8 48%, #f8efe4);
      border:1px solid var(--line); border-radius:22px; padding:20px; min-width:760px;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.8), 0 18px 45px rgba(70,48,30,.10);
    }}
    .vast-cartography * {{ box-sizing:border-box; }}
    .vast-title {{ display:flex; align-items:flex-start; justify-content:space-between; gap:18px; margin-bottom:16px; }}
    .vast-title h3 {{ margin:0; font-size:24px; letter-spacing:-.02em; }}
    .vast-kicker {{ font-family:ui-monospace, SFMono-Regular, Consolas, monospace; color:var(--orange); font-size:11px; text-transform:uppercase; letter-spacing:.14em; font-weight:800; }}
    .vast-subtitle {{ color:var(--muted); line-height:1.45; font-size:13px; max-width:680px; margin-top:4px; }}
    .vast-grid {{ display:grid; gap:12px; }}
    .vast-card {{ background:rgba(255,255,255,.72); border:1px solid rgba(220,200,181,.82); border-radius:16px; padding:12px; }}
    .vast-chip {{ display:inline-flex; align-items:center; gap:6px; padding:5px 9px; border-radius:999px; border:1px solid var(--line); background:#fff; font-family:ui-monospace, SFMono-Regular, Consolas, monospace; font-size:11px; color:var(--muted); }}
    .vast-node {{ border:1.5px solid var(--line); background:#fff; border-radius:15px; padding:10px 12px; min-height:54px; box-shadow:0 8px 22px rgba(70,48,30,.06); }}
    .vast-node strong {{ display:block; font-size:14px; }}
    .vast-node span {{ display:block; margin-top:3px; color:var(--muted); font:11px ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .person {{ border-color:rgba(217,119,69,.55); background:#fff7ed; }}
    .file {{ border-color:rgba(47,128,193,.45); background:#eff8ff; }}
    .task {{ border-color:rgba(60,157,112,.45); background:#effaf3; }}
    .system {{ border-color:rgba(100,116,139,.42); background:#f8fafc; }}
    .anomaly {{ border-color:rgba(216,74,58,.65); background:#fff1ef; }}
    .arrow {{ color:var(--slate); font:700 22px ui-monospace, SFMono-Regular, Consolas, monospace; align-self:center; justify-self:center; }}
    .fault {{ border:2px solid rgba(216,74,58,.68); background:linear-gradient(135deg,#fff1ef,#fff); color:#992b21; border-radius:16px; padding:12px; }}
    .metric {{ text-align:center; padding:12px; border-radius:16px; background:#fff; border:1px solid var(--line); }}
    .metric b {{ display:block; font-size:28px; color:var(--orange); line-height:1; }}
    .metric span {{ color:var(--muted); font:11px ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .matrix {{ width:100%; border-collapse:separate; border-spacing:0 8px; font-family:ui-monospace, SFMono-Regular, Consolas, monospace; font-size:12px; }}
    .matrix th {{ color:var(--muted); text-align:left; padding:4px 8px; font-size:10px; text-transform:uppercase; letter-spacing:.1em; }}
    .matrix td {{ background:#fff; border-top:1px solid var(--line); border-bottom:1px solid var(--line); padding:10px 8px; }}
    .matrix td:first-child {{ border-left:1px solid var(--line); border-radius:12px 0 0 12px; font-weight:800; }}
    .matrix td:last-child {{ border-right:1px solid var(--line); border-radius:0 12px 12px 0; }}
    .empty {{ color:var(--red); font-weight:900; }}
    .ok {{ color:var(--green); font-weight:900; }}
    .visual-question {{ font:800 13px ui-monospace, SFMono-Regular, Consolas, monospace; color:var(--orange); letter-spacing:.08em; text-transform:uppercase; margin-bottom:10px; }}
    .question-svg {{ width:100%; height:auto; display:block; background:linear-gradient(135deg,rgba(255,255,255,.72),rgba(255,250,243,.2)); border:1px solid rgba(220,200,181,.72); border-radius:20px; }}
    .svg-kicker {{ font:800 11px ui-monospace, SFMono-Regular, Consolas, monospace; fill:#d97745; letter-spacing:.12em; }}
    .svg-title {{ font:700 18px Georgia, 'Times New Roman', serif; fill:#30251d; }}
    .svg-node-title {{ font:800 15px Georgia, 'Times New Roman', serif; fill:#30251d; }}
    .svg-node-sub {{ font:11px ui-monospace, SFMono-Regular, Consolas, monospace; fill:#7a6859; }}
    .svg-label {{ font:700 12px ui-monospace, SFMono-Regular, Consolas, monospace; }}
    .legend-row {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }}
    .legend {{ display:inline-flex; align-items:center; gap:7px; font:11px ui-monospace, SFMono-Regular, Consolas, monospace; color:var(--muted); }}
    .legend::before {{ content:''; width:12px; height:12px; border-radius:999px; display:inline-block; border:1px solid currentColor; }}
    .person-dot::before {{ background:#fff1df; color:#d97745; }} .file-dot::before {{ background:#eaf6ff; color:#2f80c1; }} .task-dot::before {{ background:#f0fbf4; color:#3c9d70; }} .anomaly-dot::before {{ background:#fff1ef; color:#d84a3a; }}
    {extra_css}
  </style>
  <div class="vast-title">
    <div>
      <div class="vast-kicker">VAST Challenge 2026 MC2</div>
      <h3>{escape(title)}</h3>
    </div>
  </div>
  {body}
</div>
"""


def _node04_route_and_timeline(node04: Mapping[str, Any]) -> Artifact:
    created = (node04.get("file_lifecycle", {}).get("created") or [{}])[0]
    chain = node04.get("task_chain_near_post", [])
    target = node04.get("target_post", {})
    source = escape(str(node04.get("content_source", "SwiftWren.txt")))

    route_nodes = [
        ("person", _event_actor(created), "created source file"),
        ("file", source, created.get("datetime", "unknown")),
        ("person", "Daniel Gangway", "delegates read task"),
        ("person", "Chloe Ballast", "delegates to John"),
        ("person", "John Windward", "executes SaidIT actions"),
        ("system", "saidit_post_check", "pre-post check"),
        ("system", "saidit_post", "forum=general"),
        ("anomaly", "Empty SaidIT post", "content_source exists · content empty"),
    ]
    route_html = "".join(
        f"<div class='vast-node {kind}'><strong>{escape(label)}</strong><span>{escape(sub)}</span></div>"
        + ("<div class='arrow'>→</div>" if i < len(route_nodes) - 1 else "")
        for i, (kind, label, sub) in enumerate(route_nodes)
    )

    event_cards = []
    for event in [created, *chain]:
        if not event:
            continue
        details = event.get("details") or {}
        event_cards.append(
            f"<div class='vast-card'><div class='vast-chip'>{escape(str(event.get('datetime', 'unknown')))}</div>"
            f"<h4 style='margin:8px 0 4px'>{escape(str(event.get('short_name', 'event')))}</h4>"
            f"<div style='color:var(--muted);font-size:12px'>{escape(' → '.join(_person_label(str(p)) if 'person:' in str(p) else str(p).replace('system:', '') for p in event.get('parties', [])))}</div>"
            f"<div style='margin-top:6px;font:11px ui-monospace,Consolas,monospace;color:var(--muted)'>{escape(_details_text(details))}</div></div>"
        )

    body = f"""
    <p class="vast-subtitle">Target post {escape(str(target.get('id', '')))} was produced through a cross-person task chain and a SaidIT posting action that referenced {source} but produced an empty body.</p>
    <div class="vast-grid" style="grid-template-columns:repeat(15, minmax(46px,1fr)); align-items:stretch; margin:16px 0;">{route_html}</div>
    <div class="fault"><strong>Observed break:</strong> content_source = {source}, but published content is empty. The expected file-to-body transfer is not observed.</div>
    <h4 style="margin:18px 0 8px">Second-by-second evidence chain</h4>
    <div class="vast-grid" style="grid-template-columns:repeat(2,minmax(260px,1fr));">{''.join(event_cards)}</div>
    """
    return _artifact("Exact Anomaly Chain", "Route map and timeline for the target anomalous SaidIT post.", body)


def _node09_recurrence_matrix(node09: Mapping[str, Any], node12: Mapping[str, Any], node20: Mapping[str, Any]) -> Artifact:
    posts = node12.get("john_saidit_activity", {}).get("abnormal_post_details", [])
    content_by_source = {
        p.get("content_source"): p for p in node20.get("investigation", {}).get("q1_post_content_analysis", {}).get("posts", [])
    }
    source_hint = {"HiddenOrca.txt": "Chloe Ballast", "MellowOtter.txt": "Lily Anchorline", "SwiftWren.txt": "Chloe Ballast"}
    rows = []
    for post in posts:
        source = post.get("content_source", "unknown")
        content = content_by_source.get(source, {})
        is_recent = source == "SwiftWren.txt"
        source_label = escape(str(source).replace(".txt", ""))
        latest_chip = ' <span class="vast-chip">latest</span>' if is_recent else ""
        rows.append(
            "<tr>"
            f"<td>{source_label}{latest_chip}</td>"
            f"<td>{escape(source_hint.get(str(source), 'Unknown'))}</td>"
            f"<td>{escape(str(source))}</td>"
            "<td>John Windward</td>"
            "<td>saidit_post</td>"
            f"<td class='empty'>EMPTY ({escape(str(content.get('content_length', 0)))} chars)</td>"
            "<td>source deleted / cleanup observed</td>"
            "</tr>"
        )
    summary = node09.get("summary", {})
    body = f"""
    <p class="vast-subtitle">Historical behavior shows the same failure mode recurring across three content_source posts. The newest SwiftWren case is one instance of a repeated pattern.</p>
    <div class="vast-grid" style="grid-template-columns:repeat(4,1fr); margin:14px 0;">
      <div class="metric"><b>{escape(str(len(posts)))}</b><span>anomalous posts</span></div>
      <div class="metric"><b>1</b><span>executor</span></div>
      <div class="metric"><b>{escape(str(summary.get('instruction_tasks', 186)))}</b><span>related instruction tasks</span></div>
      <div class="metric"><b>3/3</b><span>empty content</span></div>
    </div>
    <table class="matrix"><thead><tr><th>Instance</th><th>Instruction source</th><th>File</th><th>Executor</th><th>Module</th><th>Result</th><th>Aftermath</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
    <div class="fault"><strong>Contrast:</strong> file names and instruction sources vary, but John Windward, saidit_post, general forum, and empty content are invariant.</div>
    """
    return _artifact("Historical Recurrence Matrix", "Contrasts prior anomalous posts with the most recent SwiftWren post.", body)


def _node12_posting_behavior(node12: Mapping[str, Any]) -> Artifact:
    activity = node12.get("john_saidit_activity", {})
    total = int(activity.get("total_posts", 0))
    abnormal = int(activity.get("abnormal_posts", 0))
    normal = max(total - abnormal, 0)
    width = 100 if total == 0 else round(abnormal / total * 100, 1)
    rows = []
    for poster, stats in node12.get("all_posters_summary", {}).get("top_posters", [])[:10]:
        posts = stats.get("post_count", 0)
        abn = stats.get("abnormal_count", 0)
        rows.append(
            f"<tr><td>{escape(_person_label(str(poster)))}</td><td>{escape(str(posts))}</td><td class='{ 'empty' if abn else ''}'>{escape(str(abn))}</td></tr>"
        )
    body = f"""
    <p class="vast-subtitle">John is not merely a high-volume poster: he is the only observed poster with content_source anomalies.</p>
    <div class="vast-grid" style="grid-template-columns:1.2fr .8fr; margin:14px 0;">
      <div class="vast-card">
        <h4 style="margin:0 0 10px">John Windward SaidIT posts</h4>
        <div style="height:28px;border-radius:999px;overflow:hidden;background:#e8ded2;border:1px solid var(--line);display:flex">
          <div style="width:{100-width}%;background:#8fb9d8"></div><div style="width:{width}%;background:var(--red)"></div>
        </div>
        <div style="display:flex;justify-content:space-between;margin-top:8px;font:12px ui-monospace,Consolas,monospace;color:var(--muted)"><span>normal {normal}</span><span>anomalous {abnormal}</span></div>
      </div>
      <div class="vast-card"><strong>Identity</strong><p style="margin:8px 0 0;color:var(--muted)">Customer Support Department Lead · 10 direct subordinates · only abnormal poster observed.</p></div>
    </div>
    <table class="matrix"><thead><tr><th>Poster</th><th>Total posts</th><th>Anomalous posts</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
    """
    return _artifact("John Posting Behavior", "Shows why John Windward is a posting-behavior outlier.", body)


def _node20_content_autopsy(node04: Mapping[str, Any], node20: Mapping[str, Any]) -> Artifact:
    created = (node04.get("file_lifecycle", {}).get("created") or [{}])[0]
    creator = _event_actor(created)
    source = node04.get("content_source", "SwiftWren.txt")
    size = (created.get("details") or {}).get("size_hint", "unknown")
    posts = node20.get("investigation", {}).get("q1_post_content_analysis", {}).get("posts", [])
    rows = []
    for post in posts:
        rows.append(
            f"<tr><td>{escape(str(post.get('content_source')))}</td><td>{escape(str(post.get('post_id')))}</td><td class='empty'>{escape(str(post.get('content_length', 0)))} chars</td><td>{'yes' if post.get('is_gibberish') else 'no'}</td></tr>"
        )
    body = f"""
    <p class="vast-subtitle">The evidence points to a content-source handling fault: the post references a file, but the body is empty.</p>
    <div class="vast-grid" style="grid-template-columns:1fr 70px 1fr 70px 1fr; align-items:center; margin:16px 0;">
      <div class="vast-node file"><strong>{escape(str(source))}</strong><span>created by {escape(creator)} · {escape(str(size))} bytes</span></div>
      <div class="arrow">→</div>
      <div class="vast-node system"><strong>saidit_post parameters</strong><span>content_source={escape(str(source))} · content=""</span></div>
      <div class="arrow">⇥</div>
      <div class="vast-node anomaly"><strong>Published post</strong><span>forum=general · body empty</span></div>
    </div>
    <div class="fault"><strong>Meaning:</strong> the probable intended content was the source file content, but the observed public post contains no transferred file text. This supports an agent/system malfunction rather than successful content publication.</div>
    <table class="matrix"><thead><tr><th>Source</th><th>Post ID</th><th>Body length</th><th>Gibberish?</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
    """
    return _artifact("Content Origin Autopsy", "Illustrates the reasoning behind the post meaning and content origin.", body)


def _node24_intervention_gate(node24: Mapping[str, Any], node12: Mapping[str, Any]) -> Artifact:
    rec = node24.get("recommended_intervention", {})
    posts = node12.get("john_saidit_activity", {}).get("abnormal_post_details", [])
    chips = "".join(f"<span class='vast-chip'>✓ {escape(str(p.get('content_source')))}</span>" for p in posts)
    why = "".join(f"<li>{escape(str(item))}</li>" for item in rec.get("why_this_location", []))
    body = f"""
    <p class="vast-subtitle">Pick one intervention point: the SaidIT saidit_post module, where all known anomalies become visible as content_source + empty content.</p>
    <div class="vast-grid" style="grid-template-columns:1fr 1fr; gap:16px; margin:16px 0;">
      <div class="vast-card"><div class="vast-kicker">Before</div><div class="vast-node anomaly" style="margin-top:10px"><strong>saidit_post</strong><span>content_source exists · content empty</span></div><div class="arrow" style="text-align:center">↓</div><div class="vast-node anomaly"><strong>Empty post published</strong><span>fault reaches public forum</span></div></div>
      <div class="vast-card"><div class="vast-kicker">After</div><div class="vast-node system" style="margin-top:10px"><strong>saidit_post</strong><span>receives content_source request</span></div><div class="arrow" style="text-align:center">↓</div><div class="vast-node task"><strong>Validation Gate</strong><span>read file and fill content OR reject post</span></div><div class="arrow" style="text-align:center">↓</div><div class="vast-node task"><strong>Empty post prevented</strong><span>3/3 known anomalies covered</span></div></div>
    </div>
    <div class="vast-card"><strong>Why this location is effective</strong><ul style="margin:8px 0 0;color:var(--muted);line-height:1.45">{why}</ul><div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">{chips}</div></div>
    """
    return _artifact("Intervention Gate Simulation", "Before/after view of the recommended saidit_post validation gate.", body)


def _node25_summary_dashboard(node25: Mapping[str, Any], node04: Mapping[str, Any], node12: Mapping[str, Any]) -> Artifact:
    findings = node25.get("key_findings", {})
    status = node25.get("background_questions_status", {})
    questions = node25.get("questions_summary", [])
    q_cards = "".join(
        f"<div class='vast-card'><span class='vast-chip'>Q{i+1}</span><strong style='display:block;margin-top:8px'>{escape(str(q.get('q','')))}</strong><p style='color:var(--muted);font-size:12px'>{escape(str(q.get('a','')))}</p></div>"
        for i, q in enumerate(questions)
    )
    body = f"""
    <p class="vast-subtitle">Final visual summary: a repeated content_source posting malfunction, not a successful data leak.</p>
    <div class="vast-grid" style="grid-template-columns:repeat(4,1fr); margin:14px 0;">
      <div class="metric"><b>{escape(str(findings.get('historical_instances', 3)))}</b><span>historical instances</span></div>
      <div class="metric"><b>1</b><span>executor: John</span></div>
      <div class="metric"><b>{escape(str(status.get('answered', 6)))}/{escape(str(status.get('total_questions', 6)))}</b><span>questions answered</span></div>
      <div class="metric"><b>100%</b><span>known-case prevention</span></div>
    </div>
    <div class="vast-grid" style="grid-template-columns:repeat(3,1fr);">{q_cards}</div>
    <div class="fault" style="margin-top:14px"><strong>Root cause hypothesis:</strong> {escape(str(node25.get('problem_recharacterization', {}).get('root_cause_hypothesis', 'content_source handling fault')))}</div>
    """
    return _artifact("Investigation Summary Dashboard", "Consolidates the challenge answers and the recommended intervention.", body)


def _artifact(title: str, summary: str, body: str) -> Artifact:
    return {
        "description": summary,
        "visualization_title": title,
        "visualization_summary": summary,
        "visualization_type": "html",
        "visualization": _wrap(title, body),
        "key_findings": [summary],
    }


def main() -> None:
    src_dir = Path(__file__).parent
    question_dir = src_dir.parent / "report_question_visualizations"
    written = write_report_question_visualizations(src_dir, question_dir)
    for key, path in written.items():
        print(f"question {key}: {path}")


if __name__ == "__main__":
    main()
