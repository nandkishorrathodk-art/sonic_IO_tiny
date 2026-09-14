"""Authoritative runtime stop state for execution safety."""
from __future__ import annotations
from threading import RLock

class RuntimeStopState:
    """Process-local, tenant-aware emergency stop latch."""
    def __init__(self) -> None:
        self._stopped: dict[str, str] = {}
        self._lock = RLock()
    def is_stopped(self, tenant_id: str = "default") -> bool:
        with self._lock:
            return "*" in self._stopped or tenant_id in self._stopped
    def reason(self, tenant_id: str = "default") -> str:
        with self._lock:
            return self._stopped.get(tenant_id) or self._stopped.get("*") or "runtime stop asserted"
    def stop(self, tenant_id: str = "default", reason: str = "operator emergency stop") -> None:
        with self._lock:
            self._stopped[tenant_id] = reason
    def resume(self, tenant_id: str = "default") -> None:
        with self._lock:
            self._stopped.pop(tenant_id, None)
    def stop_all(self, reason: str = "global emergency stop") -> None:
        with self._lock:
            self._stopped["*"] = reason
    def clear(self) -> None:
        with self._lock:
            self._stopped.clear()

_runtime_stop_state = RuntimeStopState()
def get_runtime_stop_state() -> RuntimeStopState:
    return _runtime_stop_state
