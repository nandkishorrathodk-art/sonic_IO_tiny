"""Durable, evidence-backed computer skill memory.

This is deliberately generic: skills are learned from observed applications
and successful traces, never from a vendor-specific application map.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ComputerSkillLedger:
    """Persist application capabilities learned from real workstation traces."""

    def __init__(self, tenant_id: str, root: str | None = None) -> None:
        safe_tenant = re.sub(r"[^A-Za-z0-9_.-]", "_", tenant_id or "default")
        base = Path(root or "sonic_data/skills")
        self.path = base / f"{safe_tenant}.json"
        self._data: dict[str, Any] = {"applications": {}, "actions": []}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return
        if isinstance(raw, dict):
            self._data.update(raw)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=True, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def observe_applications(self, applications: list[str]) -> None:
        changed = False
        for app in applications:
            name = str(app).strip()
            if not name:
                continue
            record = self._data["applications"].setdefault(
                name, {"observations": 0, "successful_actions": [], "last_seen": ""}
            )
            record["observations"] = int(record.get("observations", 0)) + 1
            record["last_seen"] = datetime.now(UTC).isoformat()
            changed = True
        if changed:
            self._save()

    def record_success(self, application: str, action: str, evidence: str) -> None:
        app = str(application or "").strip()
        act = str(action or "").strip()
        if not app or not act or not evidence.strip():
            return
        record = self._data["applications"].setdefault(
            app, {"observations": 0, "successful_actions": [], "last_seen": ""}
        )
        actions = record.setdefault("successful_actions", [])
        item = {"action": act[:160], "evidence": evidence[:500]}
        if item not in actions:
            actions.append(item)
            actions[:] = actions[-20:]
            self._save()

    def context(self, limit: int = 20) -> str:
        lines: list[str] = []
        for name, record in list(self._data["applications"].items())[:limit]:
            actions = record.get("successful_actions", [])
            learned = ", ".join(str(item.get("action", "")) for item in actions[-5:])
            lines.append(
                f"- {name}: observed {record.get('observations', 0)} times"
                + (f"; verified actions: {learned}" if learned else "")
            )
        return "\n".join(lines)
