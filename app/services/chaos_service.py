"""
ApexMarket: Chaos Service & Drift Injection Manager
Maintains in-memory simulation state for spot node quantization drift and fault injection.
"""
from typing import Dict
import logging

logger = logging.getLogger("apexmarket.chaos")

_DRIFT_STATE: Dict[str, bool] = {
    "runpod-h100-spot-01": False,
}


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
