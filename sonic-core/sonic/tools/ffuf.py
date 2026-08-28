"""
SONIC-REDA — ffuf Fuzzing Output Parser
==========================================
Parses JSON output from ffuf web fuzzer.
Extracts hidden endpoints, parameters, status codes, and response lengths.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from sonic.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FfufMatch:
    """A single match found during web fuzzing."""
    input_keyword: str
    url: str
    status_code: int
    content_length: int
    words: int
    lines: int
    content_type: str = ""
    redirect_location: str = ""


class FfufParser:
    """Parser for ffuf -json output."""

    @staticmethod
    def parse_json(json_text: str) -> list[FfufMatch]:
        """Parse ffuf JSON output report."""
        matches: list[FfufMatch] = []
        if not json_text.strip():
            return matches

        try:
            data = json.loads(json_text)
            results = data.get("results", [])
            for r in results:
                inputs = r.get("input", {})
                kw = next(iter(inputs.values())) if inputs else ""
                matches.append(
                    FfufMatch(
                        input_keyword=kw,
                        url=r.get("url", ""),
                        status_code=r.get("status", 200),
                        content_length=r.get("length", 0),
                        words=r.get("words", 0),
                        lines=r.get("lines", 0),
                        content_type=r.get("content-type", ""),
                        redirect_location=r.get("redirectlocation", ""),
                    )
                )
        except Exception as e:
            logger.warning("ffuf_parse_failed", error=str(e))

        return matches
