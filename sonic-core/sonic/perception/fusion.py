"""
SONIC v2 — Perception Fusion Engine
====================================
Combines Vision (Screenshots) + DOM Structure + Accessibility Tree + Network Events
into a coherent StructuredWorldState.
Eliminates sole reliance on fragile raw visual bounding boxes.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from sonic.perception.models import (
    FormElement,
    InteractiveControl,
    NetworkEvent,
    StructuredWorldState,
)


class PerceptionFusion:
    """Fuses multi-modal perception data into a unified structured world state."""

    @staticmethod
    def fuse(
        url: str = "",
        title: str = "",
        screenshot_bytes: bytes | None = None,
        dom_html: str | None = None,
        ax_tree: dict[str, Any] | None = None,
        network_traces: list[dict[str, Any]] | None = None,
    ) -> StructuredWorldState:
        # 1. Screenshot Fingerprinting
        s_hash = ""
        if screenshot_bytes:
            s_hash = hashlib.sha256(screenshot_bytes).hexdigest()

        controls: list[InteractiveControl] = []
        forms: list[FormElement] = []
        visible_text: list[str] = []
        dom_changes: list[str] = []

        # 2. Parse DOM if present
        if dom_html:
            # Simple, deterministic regex extraction of interactive elements
            # Input fields
            inputs = re.findall(r'<input([^>]+)>', dom_html, re.IGNORECASE)
            for idx, raw_input in enumerate(inputs):
                name_match = re.search(r'name=["\']([^"\']+)["\']', raw_input, re.IGNORECASE)
                type_match = re.search(r'type=["\']([^"\']+)["\']', raw_input, re.IGNORECASE)
                val_match = re.search(r'value=["\']([^"\']+)["\']', raw_input, re.IGNORECASE)
                field_name = name_match.group(1) if name_match else f"input_{idx}"
                field_type = type_match.group(1) if type_match else "text"
                controls.append(
                    InteractiveControl(
                        control_id=f"ctrl-input-{idx}",
                        tag="input",
                        role=field_type,
                        label=field_name,
                        selector=f'input[name="{field_name}"]',
                        value=val_match.group(1) if val_match else None,
                    )
                )

            # Buttons
            buttons = re.findall(r'<button([^>]*)>(.*?)</button>', dom_html, re.IGNORECASE | re.DOTALL)
            for idx, (attrs, btn_text) in enumerate(buttons):
                clean_text = re.sub(r'<[^>]+>', '', btn_text).strip()
                controls.append(
                    InteractiveControl(
                        control_id=f"ctrl-btn-{idx}",
                        tag="button",
                        role="button",
                        label=clean_text or f"button_{idx}",
                        selector=f"button:contains('{clean_text}')",
                    )
                )

            # Forms
            form_matches = re.findall(r'<form([^>]*)>(.*?)</form>', dom_html, re.IGNORECASE | re.DOTALL)
            for f_idx, (f_attrs, f_body) in enumerate(form_matches):
                action_match = re.search(r'action=["\']([^"\']+)["\']', f_attrs, re.IGNORECASE)
                method_match = re.search(r'method=["\']([^"\']+)["\']', f_attrs, re.IGNORECASE)
                forms.append(
                    FormElement(
                        form_id=f"form-{f_idx}",
                        action=action_match.group(1) if action_match else "",
                        method=method_match.group(1).upper() if method_match else "POST",
                    )
                )

            # Text snippets
            clean_dom = re.sub(r'<script.*?</script>', '', dom_html, flags=re.DOTALL | re.IGNORECASE)
            clean_dom = re.sub(r'<style.*?</style>', '', clean_dom, flags=re.DOTALL | re.IGNORECASE)
            extracted_text = re.findall(r'>([^<]{3,})<', clean_dom)
            visible_text = [t.strip() for t in extracted_text if t.strip()][:25]

        # 3. Accessibility Tree Integration
        if ax_tree and "children" in ax_tree:
            for node in ax_tree["children"]:
                if node.get("role") in ("button", "link", "textbox"):
                    controls.append(
                        InteractiveControl(
                            control_id=f"ax-{node.get('id', len(controls))}",
                            tag=node.get("tag", "element"),
                            role=node.get("role", ""),
                            label=node.get("name", ""),
                            selector=f"[role='{node.get('role')}']",
                        )
                    )

        # 4. Network Telemetry Integration
        events: list[NetworkEvent] = []
        if network_traces:
            for tr in network_traces:
                events.append(
                    NetworkEvent(
                        method=tr.get("method", "GET"),
                        url=tr.get("url", ""),
                        status_code=tr.get("status_code", 200),
                        response_type=tr.get("response_type", ""),
                        payload_summary=tr.get("payload_summary", ""),
                    )
                )

        # 5. Page State Heuristic
        combined_text = " ".join([c.label for c in controls] + visible_text + [title, url]).lower()
        if "login" in combined_text or "password" in combined_text or "sign in" in combined_text:
            page_state = "login"
        elif "forbidden" in combined_text or "403" in combined_text or "unauthorized" in combined_text:
            page_state = "access_denied"
        elif "admin" in url or "admin" in combined_text:
            page_state = "admin_portal"
        elif "dashboard" in combined_text or "logout" in combined_text or "my account" in combined_text:
            page_state = "authenticated_home"
        else:
            page_state = "content_page"

        return StructuredWorldState(
            url=url,
            title=title,
            page_state=page_state,
            controls=controls,
            forms=forms,
            visible_text=visible_text,
            dom_changes=dom_changes,
            network_events=events,
            screenshot_hash=s_hash,
        )
