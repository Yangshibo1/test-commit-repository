"""Thread-safe, resumable measurements for one semantic inference run."""

import threading
import time
from typing import Any, Dict, Mapping, Optional


class SemanticPerformance:
    def __init__(self, model: Optional[str], concurrency: int, previous: Mapping[str, Any]):
        self.model = model
        self.concurrency = concurrency
        self._lock = threading.RLock()
        self._started = time.monotonic()
        self._elapsed = float(previous.get("elapsed_seconds") or 0)
        self._stages = {item["stage"]: dict(item) for item in previous.get("stage_timings") or []}
        self._stage: Optional[str] = None
        self._stage_started = self._started
        self._stopped: Optional[float] = None

    def transition(self, stage: str) -> None:
        if stage not in {
            "boundaries",
            "semantic_annotation",
            "relations",
            "relation_review",
            "importance",
            "validation",
            "complete",
        }:
            return
        with self._lock:
            if stage == self._stage or self._stopped is not None:
                return
            now = time.monotonic()
            if self._stage:
                self._entry(self._stage)["elapsed_seconds"] += now - self._stage_started
            self._stage = None if stage == "complete" else stage
            self._stage_started = now
            if stage == "complete":
                self._stopped = now

    def _entry(self, stage: str) -> Dict[str, Any]:
        return self._stages.setdefault(
            stage,
            {
                "stage": stage,
                "elapsed_seconds": 0.0,
                "call_count": 0,
                "request_count": 0,
                "input_chars": 0,
            },
        )

    def start_call(self, stage: str, input_chars: int) -> None:
        with self._lock:
            entry = self._entry(self.call_stage(stage))
            entry["call_count"] += 1
            entry["input_chars"] += input_chars

    def finish_call(self, stage: str, requests: int) -> None:
        with self._lock:
            self._entry(self.call_stage(stage))["request_count"] += requests

    @staticmethod
    def call_stage(stage: str) -> str:
        if "relation_review" in stage:
            return "relation_review"
        if "importance" in stage:
            return "importance"
        if "boundaries" in stage:
            return "boundaries"
        if "annotation" in stage:
            return "semantic_annotation"
        return "relations"

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            now = self._stopped or time.monotonic()
            stages = [dict(item) for item in self._stages.values()]
            if self._stage:
                current = next((item for item in stages if item["stage"] == self._stage), None)
                if current is None:
                    current = dict(self._entry(self._stage))
                    stages.append(current)
                current["elapsed_seconds"] += now - self._stage_started
            for item in stages:
                item["elapsed_seconds"] = round(item["elapsed_seconds"], 3)
            return {
                "model": self.model,
                "annotation_concurrency": self.concurrency,
                "elapsed_seconds": round(self._elapsed + now - self._started, 3),
                "call_count": sum(item["call_count"] for item in stages),
                "request_count": sum(item["request_count"] for item in stages),
                "input_chars": sum(item["input_chars"] for item in stages),
                "stage_timings": stages,
            }
