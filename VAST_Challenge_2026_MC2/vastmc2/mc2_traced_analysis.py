from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opentrace.mcp_server import get_server
from opentrace.prov_validation import validate_session
from opentrace.prov_visualizer import visualize_prov_dag

DATA_DIR = ROOT / "VAST_Challenge_2026_MC2"
DATA_FILE = DATA_DIR / "MC2 data.json"
ORG_FILE = DATA_DIR / "org_chart.json"


def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def event_summary(event: dict) -> dict:
    details = event.get("details") or {}
    return {
        "id": event.get("id"),
        "short_name": event.get("short_name"),
        "when": event.get("when"),
        "when_iso": iso(event["when"]) if event.get("when") else None,
        "parties": event.get("parties", []),
        "details": {k: details.get(k) for k in sorted(details) if k in {"from", "to", "subject", "message", "content", "url", "platform", "status", "file", "filename", "title", "name"}},
    }


def text_blob(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False).lower()


def record_prov(server, session_id: str, step: str, activity_type: str, description: str, inputs: list[Path], output: Path, attrs: dict | None = None):
    entities = []
    relations = []
    for i, input_path in enumerate(inputs, 1):
        eid = f"{step}_input_{i}"
        entities.append({"id": eid, "entity_type": "dataset", "location": str(input_path), "attributes": {}})
        relations.append((f"{step}_activity", eid, "used"))
        relations.append((f"{step}_output", eid, "wasDerivedFrom"))
    entities.append({"id": f"{step}_output", "entity_type": "dataset", "location": str(output), "attributes": attrs or {}})
    activities = [{"id": f"{step}_activity", "activity_type": activity_type, "description": description, "attributes": {}}]
    agents = [{"id": f"{step}_agent", "agent_type": "python_code", "name": Path(__file__).name, "attributes": {}}]
    relations.extend([
        (f"{step}_output", f"{step}_activity", "wasGeneratedBy"),
        (f"{step}_activity", f"{step}_agent", "wasAssociatedWith"),
    ])
    server.record_prov_relation(session_id, entities, activities, agents, relations)
    server.record_step_details(
        session_id=session_id,
        step_id=step,
        step_name=description,
        description=description,
        code_files=[str(Path(__file__))],
        commands_run=[f"python {Path(__file__)}"],
        input_files=[str(p) for p in inputs],
        output_files=[str(output)],
        parameters=attrs or {},
    )


def main() -> None:
    server = get_server()
    init = server.init_session(
        task_description="VAST Challenge 2026 MC2 traced analysis",
        data_path=str(DATA_FILE),
        data_type="json",
    )
    session_id = init["session_id"]
    session_dir = Path(server.base_dir) / session_id

    data = load_json(DATA_FILE)
    org = load_json(ORG_FILE)
    events = data["events"]

    loaded = {
        "description": data.get("description"),
        "event_count": len(events),
        "org_node_count": len(org.get("nodes", [])),
        "org_edge_count": len(org.get("edges", [])),
        "time_range": {"min": min(e["when"] for e in events), "max": max(e["when"] for e in events)},
        "time_range_iso": {"min": iso(min(e["when"] for e in events)), "max": iso(max(e["when"] for e in events))},
    }
    loaded_path = session_dir / "loaded_data.json"
    dump_json(loaded_path, loaded)
    record_prov(server, session_id, "step1", "load", "加载 MC2 原始事件与组织图谱", [DATA_FILE, ORG_FILE], loaded_path, loaded)

    saidit_events = [e for e in events if "saidit" in text_blob(e)]
    key_candidates = [e for e in saidit_events if "john_windward" in text_blob(e)]
    anomalous = min(key_candidates, key=lambda e: abs(e["when"] - 2410143660.0)) if key_candidates else None
    step2 = {
        "saidit_event_count": len(saidit_events),
        "john_windward_saidit_count": len(key_candidates),
        "key_event": event_summary(anomalous) if anomalous else None,
        "top_saidit_actions": Counter(e.get("short_name") for e in saidit_events).most_common(20),
        "sample_saidit_events": [event_summary(e) for e in saidit_events[:20]],
    }
    step2_path = session_dir / "step2_saidit_key_event.json"
    dump_json(step2_path, step2)
    record_prov(server, session_id, "step2", "filter", "筛选 SaidIT 与 John Windward 异常发布事件", [loaded_path], step2_path, {"saidit_events": len(saidit_events), "john_candidates": len(key_candidates)})

    swift_events = [e for e in events if "swiftwren" in text_blob(e)]
    sorted_swift = sorted(swift_events, key=lambda e: e["when"])
    party_counts = Counter(p for e in swift_events for p in e.get("parties", []))
    action_counts = Counter(e.get("short_name") for e in swift_events)
    first_swift = sorted_swift[0] if sorted_swift else None
    by_party = defaultdict(list)
    for e in sorted_swift:
        for p in e.get("parties", []):
            by_party[p].append(e["id"])
    step3 = {
        "swiftwren_event_count": len(swift_events),
        "first_swiftwren_event": event_summary(first_swift) if first_swift else None,
        "last_swiftwren_event": event_summary(sorted_swift[-1]) if sorted_swift else None,
        "timespan_days": (sorted_swift[-1]["when"] - sorted_swift[0]["when"]) / 86400 if len(sorted_swift) > 1 else 0,
        "top_parties": party_counts.most_common(25),
        "top_actions": action_counts.most_common(25),
        "first_25_events": [event_summary(e) for e in sorted_swift[:25]],
    }
    step3_path = session_dir / "step3_swiftwren_trace.json"
    dump_json(step3_path, step3)
    record_prov(server, session_id, "step3", "trace", "追踪 SwiftWren 相关事件起源与传播", [step2_path, DATA_FILE], step3_path, {"swiftwren_events": len(swift_events)})

    before_key = [e for e in swift_events if anomalous and e["when"] <= anomalous["when"]]
    after_key = [e for e in swift_events if anomalous and e["when"] > anomalous["when"]]
    related_parties = set(p for e in swift_events for p in e.get("parties", []))
    related_events = [e for e in events if related_parties.intersection(e.get("parties", []))]
    step4 = {
        "before_key_swiftwren_events": len(before_key),
        "after_key_swiftwren_events": len(after_key),
        "related_party_count": len(related_parties),
        "related_event_count": len(related_events),
        "most_active_related_parties": Counter(p for e in related_events for p in e.get("parties", []) if p in related_parties).most_common(30),
        "pre_key_sample": [event_summary(e) for e in before_key[-20:]],
        "post_key_sample": [event_summary(e) for e in after_key[:20]],
    }
    step4_path = session_dir / "step4_network_context.json"
    dump_json(step4_path, step4)
    record_prov(server, session_id, "step4", "analyze", "分析异常事件前后相关主体网络上下文", [step3_path, DATA_FILE], step4_path, {"related_parties": len(related_parties), "related_events": len(related_events)})

    suspicious_terms = ["swiftwren", "saidit", "john_windward", "tenant thread", "post"]
    timeline_bins = defaultdict(int)
    for e in swift_events:
        timeline_bins[datetime.fromtimestamp(e["when"], timezone.utc).date().isoformat()] += 1
    final_report = {
        "session_id": session_id,
        "open_trace_base_dir": str(server.base_dir),
        "question_focus": "Identify and trace the anomalous SaidIT posting originating from Tenant Thread in MC2.",
        "findings": {
            "key_event": step2["key_event"],
            "saidit_event_count": len(saidit_events),
            "john_windward_saidit_count": len(key_candidates),
            "swiftwren_event_count": len(swift_events),
            "first_swiftwren_event": step3["first_swiftwren_event"],
            "swiftwren_timespan_days": step3["timespan_days"],
            "top_related_parties": step3["top_parties"][:10],
            "top_actions": step3["top_actions"][:10],
            "daily_swiftwren_timeline": dict(sorted(timeline_bins.items())),
        },
        "interpretation": [
            "The challenge-described anomalous SaidIT posting is recovered by filtering SaidIT events involving John Windward near 2046-05-17T04:21:00Z.",
            "SwiftWren-related events provide the trace set for origin, propagation, and related-agent context.",
            "The OpenTrace session stores all provenance artifacts under the project-root .opentrace directory.",
        ],
        "suspicious_terms_used": suspicious_terms,
        "outputs": [str(loaded_path), str(step2_path), str(step3_path), str(step4_path)],
    }
    final_path = session_dir / "final_report.json"
    dump_json(final_path, final_report)
    record_prov(server, session_id, "step5", "aggregate", "汇总 MC2 分析结论与证据链", [step2_path, step3_path, step4_path], final_path, {"outputs": 4})

    visualization_path = session_dir / "pipeline_visualization.txt"
    visualize_prov_dag(str(session_dir), str(visualization_path))
    valid, errors = validate_session(str(session_dir))
    validation_report = {
        "session_id": session_id,
        "session_dir": str(session_dir),
        "valid": valid,
        "errors": errors,
        "expected_root_storage": str((ROOT / ".opentrace").resolve()),
        "actual_base_dir": str(Path(server.base_dir).resolve()),
        "artifacts": sorted(p.name for p in session_dir.iterdir()),
    }
    dump_json(session_dir / "validation_report.json", validation_report)
    print(json.dumps(validation_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
