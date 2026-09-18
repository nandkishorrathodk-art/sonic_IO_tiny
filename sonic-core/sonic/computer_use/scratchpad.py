"""
SONIC — Hacker Scratchpad (Loot & Token Working Memory)
=======================================================
Working memory scratchpad for penetration testing loot, extracted tokens,
credentials, parameters, discovered endpoints, and strategic observations.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

# High-precision regular expressions
# JWT: Header and payload start with eyJ and are base64url encoded
JWT_REGEX = re.compile(
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\b"
)

# Bearer Token: Authorization: Bearer <token>
BEARER_REGEX = re.compile(
    r"Bearer\s+([A-Za-z0-9_\-\.]{16,})",
    re.IGNORECASE,
)

# URL parameters: ?key=value or &key=value
URL_PARAM_REGEX = re.compile(
    r"[?&]([a-zA-Z0-9_-]+)=([^&\s\"'<>]+)"
)

# Email pattern
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# Credential patterns (e.g. username: admin, password: secret, or api_key = xyz)
CREDENTIAL_PAIR_REGEX = re.compile(
    r"(?i)\b(?:username|user|login)\s*[:=]\s*[\"']?([^\s\"',;]+)[\"']?\s*[,;&\n]\s*(?:password|pass|secret|pwd)\s*[:=]\s*[\"']?([^\s\"',;]+)[\"']?"
)
API_KEY_REGEX = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|secret[_-]?key)\s*[:=]\s*[\"']?([a-zA-Z0-9_\-]{16,})[\"']?"
)

# Discovered endpoints / routes in text
ENDPOINT_REGEX = re.compile(
    r"(?:https?://[^\s\"'<>?#]+|/(?:api|v[0-9]+|login|admin|auth|users?|dashboard|oauth|token|logout|register|webhook)[a-zA-Z0-9_/\.-]*)"
)


class HackerScratchpad(BaseModel):
    """
    Working memory loot tracker for tokens, credentials, parameters,
    discovered endpoints, and strategic observations.
    """

    tokens: dict[str, str] = Field(default_factory=dict)
    credentials: list[dict[str, str]] = Field(default_factory=list)
    parameters: dict[str, list[str]] = Field(default_factory=dict)
    endpoints: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def extract_from_text(self, text: str, source: str = "") -> dict[str, int]:
        """
        Extract high-precision security tokens, credentials, parameters, and endpoints
        from raw text (HTTP responses, terminal output, page contents).
        Returns counts of newly discovered items.
        """
        if not text:
            return {"tokens": 0, "credentials": 0, "parameters": 0, "endpoints": 0}

        new_tokens = 0
        new_creds = 0
        new_params = 0
        new_endpoints = 0

        # 1. JWT Tokens
        for jwt_match in JWT_REGEX.finditer(text):
            jwt_val = jwt_match.group(0)
            if jwt_val not in self.tokens.values():
                idx = len([k for k in self.tokens if "jwt" in k]) + 1
                token_name = f"{source}_jwt_{idx}" if source else f"jwt_{idx}"
                self.tokens[token_name] = jwt_val
                new_tokens += 1

        # 2. Bearer Tokens
        for bearer_match in BEARER_REGEX.finditer(text):
            bearer_val = bearer_match.group(1)
            if bearer_val not in self.tokens.values():
                if "bearer_auth" not in self.tokens and not source:
                    token_name = "bearer_auth"
                else:
                    idx = len([k for k in self.tokens if "bearer" in k]) + 1
                    token_name = f"{source}_bearer_{idx}" if source else f"bearer_{idx}"
                self.tokens[token_name] = bearer_val
                new_tokens += 1

        # 3. URL Query Parameters
        for param_match in URL_PARAM_REGEX.finditer(text):
            param_key = param_match.group(1)
            param_val = param_match.group(2).rstrip("\"',;)>}")
            if param_key not in self.parameters:
                self.parameters[param_key] = []
            if param_val not in self.parameters[param_key]:
                self.parameters[param_key].append(param_val)
                new_params += 1

        # 4. Email / Credentials
        for email_match in EMAIL_REGEX.finditer(text):
            email_val = email_match.group(0)
            if not any(c.get("email") == email_val for c in self.credentials):
                self.credentials.append({"email": email_val})
                new_creds += 1

        for cred_match in CREDENTIAL_PAIR_REGEX.finditer(text):
            username = cred_match.group(1)
            password = cred_match.group(2)
            cred = {"username": username, "password": password}
            if cred not in self.credentials:
                self.credentials.append(cred)
                new_creds += 1

        for api_key_match in API_KEY_REGEX.finditer(text):
            api_key = api_key_match.group(1)
            cred = {"api_key": api_key}
            if cred not in self.credentials:
                self.credentials.append(cred)
                new_creds += 1

        # 5. Discovered Endpoints / Routes
        for ep_match in ENDPOINT_REGEX.finditer(text):
            ep_val = ep_match.group(0).rstrip("\"',;)>}")
            if ep_val.startswith("http://") or ep_val.startswith("https://"):
                try:
                    parsed = urlsplit(ep_val)
                    route = parsed.path or "/"
                except Exception:
                    route = ep_val
            else:
                route = ep_val

            if route and route not in self.endpoints:
                self.endpoints.append(route)
                new_endpoints += 1

        return {
            "tokens": new_tokens,
            "credentials": new_creds,
            "parameters": new_params,
            "endpoints": new_endpoints,
        }

    def add_token(self, name: str, value: str, source: str = "") -> None:
        """Add or update a token in working memory."""
        token_name = name
        if not token_name:
            prefix = f"{source}_token" if source else "token"
            token_name = f"{prefix}_{len(self.tokens) + 1}"
        self.tokens[token_name] = value

    def add_note(self, note: str) -> None:
        """Add a strategic observation or note."""
        cleaned = note.strip()
        if cleaned and cleaned not in self.notes:
            self.notes.append(cleaned)

    def is_empty(self) -> bool:
        """Check whether the scratchpad holds any loot or notes."""
        return not (
            self.tokens
            or self.credentials
            or self.parameters
            or self.endpoints
            or self.notes
        )

    def render_hud_markdown(self) -> str:
        """
        Renders a compact HUD block for LLM prompts.
        Returns empty string if nothing has been discovered yet.
        """
        if self.is_empty():
            return ""

        lines = ["HACKER SCRATCHPAD (Working Loot & Memory):"]

        if self.tokens:
            tok_strs = []
            for k, v in self.tokens.items():
                if v.startswith("eyJ"):
                    preview = f"{v[:10]}... (truncated)"
                elif len(v) > 16:
                    preview = f"{v[:13]}..."
                else:
                    preview = v
                tok_strs.append(f"{k}={preview}")
            lines.append(f"  Tokens: {', '.join(tok_strs)}")

        if self.credentials:
            cred_strs = []
            for c in self.credentials:
                items = [f"{k}={v}" for k, v in c.items()]
                cred_strs.append(f"{{{', '.join(items)}}}")
            lines.append(f"  Credentials: {'; '.join(cred_strs)}")

        if self.parameters:
            param_names = list(self.parameters.keys())
            lines.append(f"  Parameters: {', '.join(param_names)}")

        if self.endpoints:
            lines.append(f"  Discovered Endpoints: {', '.join(self.endpoints[:10])}")

        if self.notes:
            lines.append(f"  Notes: {'; '.join(self.notes[-5:])}")

        return "\n".join(lines)
