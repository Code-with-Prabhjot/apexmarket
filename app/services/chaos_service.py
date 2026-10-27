"""
ApexMarket: Chaos Service & Drift Injection Manager
Maintains in-memory simulation state for spot node quantization drift and fault injection.
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
import logging

logger = logging.getLogger("apexmarket.chaos")

_DRIFT_STATE: Dict[str, bool] = {
    "runpod-h100-spot-01": False,
}

_QUARANTINE_STATE: Dict[str, datetime] = {}


def set_node_drift(node_id: str, degraded: bool) -> None:
    """Sets or clears the simulated quantization drift flag for a given compute node."""
    _DRIFT_STATE[node_id] = degraded
    logger.info("Node '%s' drift set to: %s", node_id, degraded)


def is_node_drifted(node_id: str) -> bool:
    """Returns True if the compute node currently has quantization drift injected."""
    return _DRIFT_STATE.get(node_id, False)


def get_drift_state() -> Dict[str, bool]:
    """Returns a snapshot of all node drift states."""
    return dict(_DRIFT_STATE)


def reset_drift() -> None:
    """Restores all nodes to honest state."""
    for k in _DRIFT_STATE:
        _DRIFT_STATE[k] = False


def quarantine_node(node_id: str, duration_minutes: int = 30) -> datetime:
    """Quarantines a compute node until datetime.now(timezone.utc) + duration_minutes."""
    until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
    _QUARANTINE_STATE[node_id] = until
    logger.warning("Node '%s' quarantined until %s", node_id, until.isoformat())
    return until


def is_node_quarantined(node_id: str) -> bool:
    """Returns True if the compute node is currently under active quarantine."""
    until = _QUARANTINE_STATE.get(node_id)
    if not until:
        return False
    if datetime.now(timezone.utc) >= until:
        _QUARANTINE_STATE.pop(node_id, None)
        return False
    return True


def get_quarantined_nodes() -> Dict[str, str]:
    """Returns a mapping of quarantined node IDs to their expiration timestamps."""
    now = datetime.now(timezone.utc)
    active = {}
    for nid, until in list(_QUARANTINE_STATE.items()):
        if now < until:
            active[nid] = until.isoformat()
        else:
            _QUARANTINE_STATE.pop(nid, None)
    return active


def reset_quarantine() -> None:
    """Clears all active node quarantines."""
    _QUARANTINE_STATE.clear()
