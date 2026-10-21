"""In-memory live state shared by the executor and the /ws/telemetry hub."""
import time
from collections import deque
from typing import Dict


class ProgressTracker:
    def __init__(self, window: int = 50):
        self.window = window
        self.nodes: Dict[str, dict] = {}
        self.jobs: Dict[str, dict] = {}

    def _node(self, node_id: str) -> dict:
        return self.nodes.setdefault(node_id, {
            "ttft": deque(maxlen=self.window), "ok": deque(maxlen=self.window),
            "active": 0, "status": "ACTIVE"})

    def record(self, node_id: str, ttft_ms: float | None, ok: bool) -> None:
        n = self._node(node_id)
        n["ok"].append(ok)
        if ok and ttft_ms is not None:
            n["ttft"].append(ttft_ms)

    def inflight(self, node_id: str, delta: int) -> None:
        self._node(node_id)["active"] += delta

    def set_status(self, node_id: str, status: str) -> None:
        self._node(node_id)["status"] = status

    def start_job(self, job_id: str, total: int) -> None:
        self.jobs[job_id] = {"total": total, "done": 0, "failovers": 0}

    def advance(self, job_id: str, failover: bool = False) -> None:
        j = self.jobs.get(job_id)
        if j:
            if failover:
                j["failovers"] += 1
            else:
                j["done"] += 1

    def snapshot(self) -> dict:
        nodes = []
        for nid, n in self.nodes.items():
            t = sorted(n["ttft"])
            err = (1 - sum(n["ok"]) / len(n["ok"])) if n["ok"] else 0.0
            nodes.append({
                "node_id": nid, "status": n["status"], "active_requests": n["active"],
                "p50_ttft_ms": t[len(t) // 2] if t else 0.0,
                "p95_ttft_ms": t[min(len(t) - 1, int(len(t) * 0.95))] if t else 0.0,
                "error_rate": round(err, 4)})
        return {"ts": time.time(), "nodes": nodes, "jobs": self.jobs}


tracker = ProgressTracker()
