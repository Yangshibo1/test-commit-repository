"""Build provenance-preserving tables for the six VAST MC2 report charts.

The tables are intentionally derived from the compact investigation outputs rather
than re-reading the large raw event export.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


_COMPACT_FILES = {
    "trace": "node_04_source_trace.json",
    "posts": "node_12_john_all_posts_analysis.json",
    "content": "node_20_content_and_creator_verification.json",
    "summary": "node_25_final_investigation_summary.json",
}


def _load(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _src_dir(challenge_dir: Path | str) -> Path:
    path = Path(challenge_dir)
    return path if (path / _COMPACT_FILES["trace"]).is_file() else path / "src"


def _actor(event: Mapping[str, Any]) -> str:
    parties = event.get("parties") or []
    return str(parties[0]) if parties else "unknown"


def _event_row(event: Mapping[str, Any], sequence: int) -> dict[str, Any]:
    details = dict(event.get("details") or {})
    row = {
        "sequence": sequence,
        "event_id": event["id"],
        "event_type": event.get("short_name", "event"),
        "datetime": event.get("datetime"),
        "actor": _actor(event),
        "parties": list(event.get("parties") or []),
        "source_event_ids": [event["id"]],
    }
    row.update(details)
    return row


def build_chart_tables(challenge_dir: Path | str) -> dict[str, list[dict[str, Any]]]:
    """Return chart-ready ``q1`` through ``q6`` tables with event provenance.

    ``challenge_dir`` may point to ``VAST_Challenge_2026_MC2`` or directly to
    its ``src`` directory. Every returned row contains non-empty
    ``source_event_ids`` identifying the observations supporting that row.
    """

    src = _src_dir(challenge_dir)
    data = {name: _load(src / filename) for name, filename in _COMPACT_FILES.items()}
    trace, posts, content, summary = (
        data["trace"],
        data["posts"],
        data["content"],
        data["summary"],
    )

    created = list(trace.get("file_lifecycle", {}).get("created") or [])
    chain = list(trace.get("task_chain_near_post") or [])
    target = trace.get("target_post") or {}
    abnormal_posts = list(posts.get("john_saidit_activity", {}).get("abnormal_post_details") or [])
    content_posts = list(
        content.get("investigation", {}).get("q1_post_content_analysis", {}).get("posts") or []
    )
    content_by_id = {item.get("post_id"): item for item in content_posts}

    q1_events = [*created, *chain]
    q1 = []
    for sequence, event in enumerate(q1_events, 1):
        row = _event_row(event, sequence)
        row["content_source"] = trace.get("content_source")
        row["target_post_id"] = target.get("id")
        q1.append(row)

    q2 = [_event_row(event, sequence) for sequence, event in enumerate(q1_events, 1)]

    all_post_ids = [post["id"] for post in abnormal_posts]
    target_chain_ids = [event["id"] for event in q1_events]
    activity = posts.get("john_saidit_activity", {})
    identity = posts.get("john_windward_identity", {})
    q3 = [
        {
            "component": "John Windward SaidIT activity",
            "metric": "total_posts",
            "value": activity.get("total_posts", 0),
            "source_event_ids": all_post_ids,
        },
        {
            "component": "John Windward SaidIT activity",
            "metric": "abnormal_posts",
            "value": activity.get("abnormal_posts", 0),
            "source_event_ids": all_post_ids,
        },
        {
            "component": "Target cross-system chain",
            "metric": "observed_events",
            "value": len(q1_events),
            "source_event_ids": target_chain_ids,
        },
        {
            "component": identity.get("department", "Customer Support"),
            "metric": "direct_subordinates",
            "value": len(identity.get("direct_subordinates") or []),
            "source_event_ids": all_post_ids,
        },
    ]

    creator_ids = [event["id"] for event in created]
    q4 = []
    for observed in content_posts:
        post_id = observed["post_id"]
        source = observed.get("content_source")
        provenance = [post_id]
        if source == trace.get("content_source"):
            provenance.extend(creator_ids)
        q4.append(
            {
                "post_id": post_id,
                "content_source": source,
                "content_length": observed.get("content_length", 0),
                "is_empty": observed.get("content_length", 0) == 0,
                "is_gibberish": observed.get("is_gibberish", False),
                "creator": _actor(created[0]) if source == trace.get("content_source") and created else None,
                "source_event_ids": provenance,
            }
        )

    q5 = []
    for post in abnormal_posts:
        observed = content_by_id.get(post.get("id"), {})
        q5.append(
            {
                "post_id": post["id"],
                "datetime": post.get("datetime"),
                "event_type": post.get("short_name"),
                "poster": _actor(post),
                "forum": post.get("forum") or post.get("details", {}).get("forum"),
                "content_source": post.get("content_source"),
                "content_length": observed.get("content_length", 0),
                "is_empty": observed.get("content_length", 0) == 0,
                "source_event_ids": [post["id"]],
            }
        )

    recommendation = summary.get("intervention_recommended", {})
    q6 = [
        {
            "intervention": recommendation.get("name"),
            "location": recommendation.get("location"),
            "rule": "content_source present and content empty",
            "action": recommendation.get("intervention_description"),
            "known_cases": len(abnormal_posts),
            "preventable_cases": len(abnormal_posts),
            "source_event_ids": all_post_ids,
        }
    ]

    return {"q1": q1, "q2": q2, "q3": q3, "q4": q4, "q5": q5, "q6": q6}
