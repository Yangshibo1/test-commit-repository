"""
生成Q1链路可视化 - 事件节点版（原始设计）
- 节点=事件，边=queue连接
- 节点三行：人名 | short_name | 第三行（根据事件类型）
"""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple


# 部门颜色配置（与org chart完全对应，无Unknown）
DEPARTMENT_COLORS = {
    "Executive Suite": {"border": "#d97745", "bg": "#fff7ed", "text": "#9a3412"},
    "Customer Support": {"border": "#2563eb", "bg": "#eff8ff", "text": "#1e40af"},
    "Products": {"border": "#7c3aed", "bg": "#f5f3ff", "text": "#5b21b6"},
    "Human Resources": {"border": "#db2777", "bg": "#fdf2f8", "text": "#9f1239"},
    "Legal": {"border": "#ca8a04", "bg": "#fefce8", "text": "#854d0e"},
    "Information Technologies": {"border": "#16a34a", "bg": "#f0fdf4", "text": "#166534"},
}


def convert_utc_to_mst(unix_timestamp: Optional[float]) -> Optional[str]:
    """将UTC时间戳转换为MST (Mountain Time, UTC-7)"""
    if unix_timestamp is None:
        return None
    try:
        utc_time = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
        mst_time = utc_time + timedelta(hours=-7)
        return mst_time.strftime("%b %d, %Y at %I:%M%p").lower()
    except (ValueError, OSError):
        return None


def get_third_line_content(event: Dict[str, Any]) -> str:
    """根据事件类型生成第三行内容"""
    short_name = event.get("short_name", "")
    details = event.get("details", {})

    if short_name == "create_file":
        return details.get("target", "")
    elif short_name == "delete_file":
        return details.get("target", "")
    elif short_name == "queue_subordinate_task":
        return details.get("task", "")
    elif short_name == "saidit_post":
        return details.get("content_source", "")
    else:
        return ""


def transform_enhanced_data(chain_data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    转换增强的链路数据为节点和边

    节点: 有department的人员事件
    边: queue事件连接前后节点
    """
    events = chain_data["chain_events"]
    nodes = []
    edges = []

    # 为事件添加chronological_order（如果没有的话）
    for i, event in enumerate(events):
        if "chronological_order" not in event:
            event["chronological_order"] = i + 1

    for event in events:
        short_name = event.get("short_name", "")
        details = event.get("details", {})
        source_dept = event.get("source_agent_department")
        target_dept = event.get("target_agent_department")
        source_name = event.get("source_agent_name", "")
        target_name = event.get("target_agent_name", "")

        # 转换时间
        display_time = convert_utc_to_mst(event.get("when"))
        # 兼容不同的字段名
        event_id = event.get("event_id") or event.get("id")
        third_line = get_third_line_content(event)

        if short_name == "queue_subordinate_task":
            # queue事件作为边，连接前后两个事件
            if source_dept and target_dept:
                edge = {
                    "edge_id": event_id,
                    "type": "queue",
                    "source": source_name,
                    "source_dept": source_dept,
                    "target": target_name,
                    "target_dept": target_dept,
                    "task": details.get("task", ""),
                    "path": details.get("args", {}).get("path", ""),
                    "display_time": display_time,
                    "chronological_order": event.get("chronological_order")
                }
                edges.append(edge)

            # queue事件也作为节点
            node = {
                "node_id": event_id,
                "event_id": event_id,
                "short_name": short_name,
                "person": source_name,
                "department": source_dept,
                "display_time": display_time,
                "third_line": third_line,
                "stage": event.get("stage", "unknown"),
                "chronological_order": event.get("chronological_order"),
                "is_key": False  # 稍后统一设置
            }
            nodes.append(node)

        # 有部门的人员事件也作为节点
        elif source_dept:
            node = {
                "node_id": event_id,
                "event_id": event_id,
                "short_name": short_name,
                "person": source_name,
                "department": source_dept,
                "display_time": display_time,
                "third_line": third_line,
                "stage": event.get("stage", "unknown"),
                "chronological_order": event.get("chronological_order"),
                "is_key": False  # 稍后统一设置
            }
            nodes.append(node)

    # 按时间排序
    nodes.sort(key=lambda x: x.get("chronological_order", 0))
    edges.sort(key=lambda x: x.get("chronological_order", 0))

    # 标记关键节点：前三个和后五个
    for i, node in enumerate(nodes):
        if i < 3 or i >= len(nodes) - 5:
            node["is_key"] = True
        else:
            node["is_key"] = False

    return nodes, edges


def generate_html(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], output_path: Path) -> None:
    """生成HTML可视化"""

    nodes_json = json.dumps(nodes, ensure_ascii=False)
    edges_json = json.dumps(edges, ensure_ascii=False)
    departments_json = json.dumps(list(DEPARTMENT_COLORS.keys()), ensure_ascii=False)
    colors_json = json.dumps(DEPARTMENT_COLORS, ensure_ascii=False)

    # 统计信息
    total_nodes = len(nodes)
    total_edges = len(edges)
    key_nodes = sum(1 for n in nodes if n.get("is_key"))
    post_check_nodes = sum(1 for n in nodes if n.get("short_name") == "saidit_post_check")
    max_node_size = 150  # 统一节点尺寸（增大）
    nodes_per_row = 7   # 一行7个节点

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Q1 · SwiftWren Event Chain</title>
<style>
  :root {{
    --bg:#15100c; --paper:#fff8ed; --ink:#2e241d; --muted:#7d6b5d; --line:#dcc6ae;
    --key:#dc3f32; --gold:#d3912c;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:radial-gradient(circle at 12% 0%, #5a331f, transparent 34rem), linear-gradient(135deg,#1d140e,#0f0b08); color:var(--paper); font-family:Georgia, 'Times New Roman', serif; padding:32px; }}
  main {{ max-width:2200px; margin:0 auto; }}
  header {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-start; margin-bottom:22px; }}
  h1 {{ margin:0; font-size:42px; line-height:.96; letter-spacing:-.045em; }}
  .subtitle {{ margin:10px 0 0; color:#d9c4af; max-width:900px; line-height:1.45; }}
  .stats {{ display:grid; grid-template-columns:repeat(5,120px); gap:10px; }}
  .stat {{ background:#fff8ed; color:var(--ink); border:1px solid #e7d3bd; border-radius:18px; padding:14px; text-align:center; }}
  .stat b {{ display:block; font-size:28px; color:#d97745; }}
  .stat span {{ font:11px ui-monospace, Consolas, monospace; color:var(--muted); }}

  .toolbar {{ background:rgba(255,248,237,.94); color:var(--ink); border:1px solid #e4ccb3; border-radius:24px; padding:14px; display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:14px; }}
  button, select, input {{ border:1px solid #ceb59c; background:#fff; color:var(--ink); border-radius:999px; padding:9px 12px; font:12px ui-monospace, Consolas, monospace; cursor:pointer; }}
  button.active {{ background:#2e241d; color:#fff8ed; }}
  .legend {{ display:flex; gap:8px; flex-wrap:wrap; margin-left:auto; }}
  .legend span {{ display:inline-flex; align-items:center; gap:6px; font:11px ui-monospace, Consolas, monospace; color:var(--muted); }}
  .legend i {{ width:11px; height:11px; border-radius:50%; display:inline-block; }}

  .viz-shell {{ background:var(--paper); color:var(--ink); border:1px solid #e4ccb3; border-radius:30px; padding:24px; box-shadow:0 28px 80px rgba(0,0,0,.35); }}
  #chain {{ position:relative; padding:20px; }}

  /* 节点样式 - 统一大小，增大尺寸 */
  .node {{ position:relative; border:2px solid var(--dept-color, #ccc); background:#fff; border-radius:12px; padding:14px; width:150px; height:110px; box-shadow:0 6px 16px rgba(70,48,30,.06); transition:all 0.2s; cursor:pointer; display:inline-flex; flex-direction:column; justify-content:center; align-items:center; margin:0 20px 0 8px; text-align:center; flex-shrink:0; overflow:visible; }}
  .node:hover {{ transform:translateY(-2px); box-shadow:0 10px 24px rgba(70,48,30,.12); }}
  .node.key {{ border-width:4px; border-color:var(--dept-color); background:radial-gradient(circle at center, rgba(220,63,50,.15), transparent 70%), #fff; box-shadow:0 0 20px rgba(220,63,50,.4),0 0 40px rgba(220,63,50,.2), inset 0 0 30px rgba(220,63,50,.1); transform:scale(1.05); z-index:10; }}

  /* 时间在右上角 */
  .node-time {{ position:absolute; top:-8px; right:-8px; background:var(--dept-color, #ccc); color:#fff; padding:2px 6px; border-radius:8px; font:9px ui-monospace, Consolas, monospace; white-space:nowrap; }}

  /* 节点内容三行 */
  .node-name {{ font-weight:700; font-size:11px; letter-spacing:0.05em; text-transform:uppercase; color:var(--ink); margin-bottom:4px; }}
  .node-short {{ font:9px ui-monospace, Consolas, monospace; color:#64748b; margin-bottom:4px; text-transform:lowercase; }}
  .node-detail {{ font:10px; color:var(--muted); line-height:1.1; word-break:break-all; overflow:hidden; }}

  /* 有向箭头边 */
  .edge {{ position:relative; display:inline-block; vertical-align:middle; margin:0 4px; }}
  .edge-arrow {{ height:2px; background:#9b8978; position:relative; width:40px; }}
  .edge-arrow:after {{ content:''; position:absolute; right:-4px; top:-3px; width:0; height:0; border-left:6px solid #9b8978; border-top:4px solid transparent; border-bottom:4px solid transparent; }}
  .edge-label {{ position:absolute; top:-12px; left:50%; transform:translateX(-50%); background:#fff; border:1px solid #e3d0bd; border-radius:999px; padding:1px 6px; font:9px ui-monospace, Consolas, monospace; color:var(--muted); white-space:nowrap; font-weight:600; }}

  /* 链路容器 - 增加箭头空间 */
  .chain-row {{ display:flex; align-items:center; flex-wrap:nowrap; margin-bottom:60px; justify-content:flex-start; gap:0; }}
  .chain-row::-webkit-scrollbar {{ height:8px; }}
  .chain-row::-webkit-scrollbar-thumb {{ background:#dcc6ae; border-radius:4px; }}
  .collapse-marker {{ text-align:left; padding:8px 0; background:transparent; color:var(--muted); font:13px ui-monospace, Consolas, monospace; letter-spacing:.06em; margin:-20px 0 60px 0; display:block; }}

  .details {{ margin-top:20px; display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }}
  .panel {{ background:#fff8ed; color:var(--ink); border:1px solid #e4ccb3; border-radius:22px; padding:16px; }}
  .panel h3 {{ margin:0 0 10px; font-size:14px; }}

  .stage-stats {{ display:grid; gap:8px; }}
  .stage-row {{ display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid #e7d3bd; font:11px ui-monospace, Consolas, monospace; }}
</style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Q1 · SwiftWren Event Chain</h1>
      <p class="subtitle">Complete chain from Emma Harbor creating SwiftWren.txt to John Windward's anomalous SaidIT post. Nodes show key events; arrows show queue delegation.</p>
    </div>
    <div class="stats">
      <div class="stat"><b>{total_nodes}</b><span>events</span></div>
      <div class="stat"><b>{total_edges}</b><span>queues</span></div>
      <div class="stat"><b>{key_nodes}</b><span>key events</span></div>
      <div class="stat"><b>{len(set(n.get('department') for n in nodes))}</b><span>departments</span></div>
      <div class="stat"><b>{post_check_nodes}</b><span>post checks</span></div>
    </div>
  </header>

  <section class="toolbar">
    <button id="showDefault" class="active">First 7 + Last 7</button>
    <button id="showAll">Show all</button>
    <button id="showKey">Key events</button>
    <input id="search" placeholder="Search..." style="width:150px" />
    <select id="department"><option value="">All departments</option></select>
    <select id="eventType"></select>
    <select id="personFilter"></select>
    <div class="legend" id="legend"></div>
  </section>

  <section class="viz-shell">
    <div id="chain"></div>
  </section>

  <section class="details">
    <div class="panel">
      <h3>Event Type Distribution</h3>
      <div id="eventTypeStats" class="stage-stats"></div>
    </div>
    <div class="panel">
      <h3>About</h3>
      <p style="color:var(--muted);font-size:11px;line-height:1.4">Nodes: Personnel events with department info. Edges: Queue delegation. Timeline in MST (UTC-7). Third line shows task details based on event type.</p>
    </div>
  </section>
</main>
<script>
const NODES = {nodes_json};
const EDGES = {edges_json};
const DEPARTMENTS = {departments_json};
const COLORS = {colors_json};

let showMode = 'default';
let searchQuery = '';
let departmentFilter = '';
let eventTypeFilter = '';
let personFilter = '';

const chain = document.getElementById('chain');
const deptSelect = document.getElementById('department');
const eventSelect = document.getElementById('eventType');
const personSelect = document.getElementById('personFilter');

// Populate department dropdown
DEPARTMENTS.forEach(d => {{
  const opt = document.createElement('option');
  opt.value = d;
  opt.textContent = d;
  deptSelect.appendChild(opt);
}});

// Populate event type dropdown with 4 filter options
const eventFilterOptions = [
  {{value: '', label: 'All event types'}},
  {{value: 'no_postcheck', label: 'No post checks'}},
  {{value: 'no_queue', label: 'No queue'}},
  {{value: 'no_post_queue', label: 'No post & queue'}}
];

eventFilterOptions.forEach(opt => {{
  const option = document.createElement('option');
  option.value = opt.value;
  option.textContent = opt.label;
  eventSelect.appendChild(option);
}});

// Populate person filter dropdown with all unique persons
const uniquePersons = [...new Set(NODES.map(n => n.person).filter(Boolean))].sort();
// Add "All people" option first
const allPeopleOpt = document.createElement('option');
allPeopleOpt.value = '';
allPeopleOpt.textContent = 'All people';
personSelect.appendChild(allPeopleOpt);
uniquePersons.forEach(person => {{
  const opt = document.createElement('option');
  opt.value = person;
  opt.textContent = person;
  personSelect.appendChild(opt);
}});

// Create legend
document.getElementById('legend').innerHTML = DEPARTMENTS.map(d =>
  `<span><i style="background:${{COLORS[d]?.border||'#ccc'}}"></i>${{d}}</span>`
).join('');

// Button handlers
document.getElementById('showAll').onclick = () => {{ showMode = 'all'; render(); }};
document.getElementById('showDefault').onclick = () => {{ showMode = 'default'; render(); }};
document.getElementById('showAll').onclick = () => {{ showMode = 'all'; render(); }};
document.getElementById('showKey').onclick = () => {{ showMode = 'key'; render(); }};
document.getElementById('search').oninput = (e) => {{ searchQuery = e.target.value.toLowerCase(); render(); }};
deptSelect.onchange = (e) => {{ departmentFilter = e.target.value; render(); }};
eventSelect.onchange = (e) => {{ eventTypeFilter = e.target.value; render(); }};
personSelect.onchange = (e) => {{ personFilter = e.target.value; render(); }};

function shouldShowNode(node) {{
  // Department filter
  if (departmentFilter && node.department !== departmentFilter) return false;

  // Search filter
  if (searchQuery) {{
    const haystack = `${{node.person}} ${{node.short_name}} ${{node.third_line}} ${{node.department}}`.toLowerCase();
    if (!haystack.includes(searchQuery)) return false;
  }}

  // Person filter
  if (personFilter && node.person !== personFilter) return false;

  // Event type filter
  if (eventTypeFilter === 'no_postcheck') {{
    if (node.short_name === 'saidit_post_check') return false;
  }} else if (eventTypeFilter === 'no_queue') {{
    if (node.short_name === 'queue_subordinate_task') return false;
  }} else if (eventTypeFilter === 'no_post_queue') {{
    if (node.short_name === 'saidit_post_check' || node.short_name === 'queue_subordinate_task') return false;
  }}

  return true;
}}

function getVisibleNodes() {{
  return NODES.filter(node => shouldShowNode(node));
}}

function renderNode(node) {{
  const color = COLORS[node.department] || COLORS['Unknown'];
  const keyClass = node.is_key ? ' key' : '';
  const name = node.person || 'Unknown';
  const short = node.short_name || '';
  const detail = node.third_line || '';
  const time = node.display_time || '';

  return `<div class="node${{keyClass}}" style="--dept-color:${{color.border}}" data-node-id="${{node.node_id}}">
    <div class="node-time">${{time}}</div>
    <div class="node-name">${{name}}</div>
    <div class="node-short">${{short}}</div>
    <div class="node-detail">${{detail}}</div>
  </div>`;
}}

function renderEdge(edge, showLabel) {{
  const labelHtml = showLabel ? `<div class="edge-label">queue</div>` : '';
  return `<div class="edge">
    ${{labelHtml}}
    <div class="edge-arrow"></div>
  </div>`;
}}

function render() {{
  const visibleNodes = getVisibleNodes();
  let displayNodes = [];

  if (showMode === 'all') {{
    displayNodes = visibleNodes;
  }} else if (showMode === 'key') {{
    displayNodes = visibleNodes.filter(n => n.is_key);
  }} else {{ // default: first 7 + last 7
    const n = visibleNodes.length;
    if (n <= 14) {{
      displayNodes = visibleNodes;
    }} else {{
      displayNodes = [...visibleNodes.slice(0, 7), ...visibleNodes.slice(-7)];
    }}
  }}

  // Update button states
  document.querySelectorAll('.toolbar button').forEach(btn => btn.classList.remove('active'));
  if (showMode === 'all') document.getElementById('showAll').classList.add('active');
  else if (showMode === 'key') document.getElementById('showKey').classList.add('active');
  else document.getElementById('showDefault').classList.add('active');

  // Render chain with edges
  let html = '<div class="chain-row">';

  for (let i = 0; i < displayNodes.length; i++) {{
    const node = displayNodes[i];

    // 添加节点
    html += renderNode(node);

    // 所有节点之间都有边，但只有show all模式且无部门筛选时queue节点才显示"queue"标签
    // 检查当前节点是否是queue_subordinate_task
    if (i < displayNodes.length - 1) {{
      // 在原始节点中查找是否是queue事件，且只有在show all模式且无部门筛选时才显示标签
      const originalNode = NODES.find(n => n.node_id === node.node_id);
      const showQueueLabel = showMode === 'all' && !departmentFilter && originalNode && originalNode.short_name === 'queue_subordinate_task';
      html += renderEdge({{label: 'queue'}}, showQueueLabel);
    }}

    // 每7个节点换行
    if ((i + 1) % 7 === 0 && i < displayNodes.length - 1) {{
      html += '</div><div class="chain-row">';
    }}
  }}

  html += '</div>';

  // 添加折叠标记（如果适用）：第一行7个节点 + 中间文字 + 最后一行7个节点
  if (showMode === 'default' && visibleNodes.length > 14) {{
    const middleCount = visibleNodes.length - 14;
    const collapseHtml = `<div class="collapse-marker">${{middleCount}} events collapsed...</div>`;

    // 重新构建为三行：前7个节点 + 折叠标记 + 后7个节点
    let firstRowHtml = '<div class="chain-row">';
    let lastRowHtml = '<div class="chain-row">';

    // 前行7个节点
    for (let i = 0; i < 7; i++) {{
      const node = displayNodes[i];
      firstRowHtml += renderNode(node);
      firstRowHtml += renderEdge({{label: 'queue'}}, false);  // 默认模式不显示queue标签
    }}
    firstRowHtml += '</div>';

    // 后7个节点
    for (let i = displayNodes.length - 7; i < displayNodes.length; i++) {{
      const node = displayNodes[i];
      lastRowHtml += renderNode(node);
      if (i < displayNodes.length - 1) {{
        lastRowHtml += renderEdge({{label: 'queue'}}, false);  // 默认模式不显示queue标签
      }}
    }}
    lastRowHtml += '</div>';

    html = firstRowHtml + collapseHtml + lastRowHtml;
  }}

  chain.innerHTML = html;

  // Update event type stats
  const eventTypes = {{}};
  displayNodes.forEach(n => {{
    const key = n.short_name;
    eventTypes[key] = (eventTypes[key] || 0) + 1;
  }});
  document.getElementById('eventTypeStats').innerHTML = Object.entries(eventTypes)
    .sort((a, b) => b[1] - a[1])
    .map(([type, count]) => `<div class="stage-row"><span>${{type}}</span><span>${{count}}</span></div>`)
    .join('');
}}

// Initial render
render();
</script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")
    print(f"Generated: {output_path}")


def main():
    """主函数"""
    print("=" * 60)
    print("Generating Q1 Chain Visualization (Event Nodes)")
    print("=" * 60)

    # 加载增强数据（使用191条链路 + 64个检查事件的合并数据）
    print("\n1. Loading enriched data...")
    with open('result/complete_swiftwren_chain_with_checks.json', encoding='utf-8') as f:
        chain_data = json.load(f)

    # 转换数据
    print("\n2. Transforming data...")
    nodes, edges = transform_enhanced_data(chain_data)
    print(f"   Created {len(nodes)} event nodes and {len(edges)} queue edges")

    # 显示节点样本
    print("\n   Sample event nodes:")
    for node in nodes[:5]:
        print(f"     {node['node_id']}: {node['person']} ({node['department']})")
        print(f"       {node['short_name']} | {node['third_line']}")

    # 生成HTML
    print("\n3. Generating HTML visualization...")
    output_path = Path('VAST_Challenge_2026_MC2/report_question_visualizations/q1_complete_chain.html')
    generate_html(nodes, edges, output_path)

    print("\n" + "=" * 60)
    print("Complete!")
    print("=" * 60)
    print(f"\nOutput: {output_path}")

    # 统计事件类型
    event_types = {}
    for node in nodes:
        event_type = node.get("short_name")
        event_types[event_type] = event_types.get(event_type, 0) + 1

    print(f"\nEvent type distribution:")
    for event_type, count in sorted(event_types.items(), key=lambda x: -x[1]):
        print(f"  {event_type}: {count}")


if __name__ == '__main__':
    main()
