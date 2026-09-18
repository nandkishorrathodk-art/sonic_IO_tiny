"""Structured intake for pasted security-program scope documents.

The document is context, not an execution objective.  Only assets explicitly
selected by the operator may become an active target.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s,<>\"']+", re.IGNORECASE)
_HOST_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b",
    re.IGNORECASE,
)
_SCOPE_MARKERS = re.compile(r"\b(?:in\s+scope|in-scope|included\s+in\s+scope)\b", re.IGNORECASE)
_EXCLUSION_MARKERS = re.compile(r"\b(?:out\s+of\s+scope|exclusions?|excluded)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ScopeManifest:
    """Evidence-labelled scope context extracted from operator-provided text."""

    program_detected: bool = False
    in_scope_assets: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    reference_links: tuple[str, ...] = ()
    requires_asset_selection: bool = False
    source: str = "operator_text"

    def as_context(self) -> dict[str, object]:
        return {
            "program_detected": self.program_detected,
            "in_scope_assets": list(self.in_scope_assets),
            "exclusions": list(self.exclusions),
            "reference_links": list(self.reference_links),
            "requires_asset_selection": self.requires_asset_selection,
            "source": self.source,
        }


def _canonical_target(value: str) -> str:
    value = value.strip().rstrip(").,;")
    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        return (parsed.hostname or value).lower().rstrip(".")
    return value.lower().rstrip(".")


def parse_scope_document(text: str) -> ScopeManifest:
    """Parse likely program-scope text without promoting every link to a target."""
    if not text or len(text) < 180:
        return ScopeManifest()

    lower = text.lower()
    program_detected = any(
        marker in lower
        for marker in ("bug bounty", "safe harbor", "targets", "vulnerabilities rewarded")
    )
    if not program_detected:
        return ScopeManifest()

    urls = list(dict.fromkeys(_URL_RE.findall(text)))
    hosts = list(dict.fromkeys(_canonical_target(item) for item in urls))
    hosts.extend(
        host.lower().rstrip(".")
        for host in _HOST_RE.findall(text)
    )

    in_scope: list[str] = []
    exclusions: list[str] = []
    references: list[str] = []

    # Flattened browser extraction often removes line boundaries. A nearby
    # scope marker is useful evidence, but never enough to authorize execution.
    for url, host in zip(urls, [_canonical_target(item) for item in urls]):
        position = lower.find(url.lower())
        nearby = lower[max(0, position - 180): position + len(url) + 80]
        if _SCOPE_MARKERS.search(nearby) and not _EXCLUSION_MARKERS.search(nearby):
            if host not in in_scope:
                in_scope.append(host)
        else:
            if url not in references:
                references.append(url)

    for host in hosts:
        if host in in_scope:
            continue
        position = lower.find(host)
        nearby = lower[max(0, position - 180): position + len(host) + 80]
        if _EXCLUSION_MARKERS.search(nearby):
            if host not in exclusions:
                exclusions.append(host)
        elif _SCOPE_MARKERS.search(nearby) and host not in in_scope:
            in_scope.append(host)

    if "third-party services" in lower:
        exclusions.append("third-party services named by the program")
    if "phishing and similar attacks" in lower:
        exclusions.append("phishing/social engineering")

    return ScopeManifest(
        program_detected=True,
        in_scope_assets=tuple(dict.fromkeys(in_scope)),
        exclusions=tuple(dict.fromkeys(exclusions)),
        reference_links=tuple(dict.fromkeys(references)),
        requires_asset_selection=len(in_scope) != 1,
    )
