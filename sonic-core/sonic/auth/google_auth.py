"""
SONIC-REDA — Google OAuth2 Authentication
============================================
Handles Google login flow, JWT generation, and team allowlist enforcement.

Flow:
    1. User visits /auth/google/login → redirected to Google consent screen
    2. Google redirects back to /auth/google/callback with auth code
    3. We exchange code for tokens, fetch user profile
    4. Check if user email/domain is in allowlist
    5. Issue our own JWT for subsequent API calls
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

try:
    from jose import JWTError, jwt
except ImportError:
    try:
        import jwt
        class JWTError(Exception):
            pass
    except ImportError:
        class JWTError(Exception):
            pass
        class jwt:
            @staticmethod
            def encode(payload: dict, secret: str, algorithm: str = "HS256") -> str:
                header = base64.urlsafe_b64encode(json.dumps({"alg": algorithm, "typ": "JWT"}).encode()).decode().rstrip("=")
                body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
                signature = base64.urlsafe_b64encode(hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
                return f"{header}.{body}.{signature}"

            @staticmethod
            def decode(token: str, secret: str, algorithms: list[str] = None) -> dict:
                parts = token.split(".")
                if len(parts) != 3:
                    raise JWTError("Invalid token format")
                header, body, sig = parts
                expected_sig = base64.urlsafe_b64encode(hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
                if not hmac.compare_digest(sig, expected_sig):
                    raise JWTError("Signature mismatch")
                padded = body + "=" * ((4 - len(body) % 4) % 4)
                return json.loads(base64.urlsafe_b64decode(padded.encode()).decode())

from sonic.auth.models import AuthToken, TokenPayload, User, UserRole
from sonic.config import get_settings
from sonic.logger import get_logger

logger = get_logger(__name__)

# Google OAuth2 endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Scopes we request from Google
GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


def get_google_login_url(state: str = "") -> str:
    """
    Build the Google OAuth2 authorization URL.
    The user's browser should be redirected to this URL.
    """
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "select_account",
    }
    if state:
        params["state"] = state

    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GOOGLE_AUTH_URL}?{query}"


async def exchange_code_for_tokens(code: str) -> dict[str, Any]:
    """
    Exchange the authorization code from Google callback for access + id tokens.
    """
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()


async def fetch_google_user_info(access_token: str) -> dict[str, Any]:
    """
    Fetch user profile from Google using the access token.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()


def is_email_allowed(email: str) -> bool:
    """
    Check if the given email is in the team allowlist.
    Checks both specific emails and allowed domains.
    """
    settings = get_settings()
    allowed_emails = settings.allowed_emails_list
    allowed_domains = settings.allowed_domains_list

    # Check exact email match
    if email.lower() in [e.lower() for e in allowed_emails]:
        return True

    # Check domain match
    domain = email.split("@")[1] if "@" in email else ""
    if domain.lower() in [d.lower() for d in allowed_domains]:
        return True

    # If no allowlist configured at all, deny by default (secure default)
    if not allowed_emails and not allowed_domains:
        logger.warning(
            "no_allowlist_configured",
            email=email,
            msg="No allowed emails or domains configured. Denying all access.",
        )
        return False

    return False


def create_jwt_token(user: User) -> AuthToken:
    """
    Create a JWT token for an authenticated multi-tenant user.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    expiry = now + timedelta(hours=settings.jwt_expiry_hours)

    payload = {
        "sub": user.email,
        "name": user.name,
        "tenant_id": user.tenant_id,
        "workspace_id": user.workspace_id,
        "picture": user.picture,
        "google_id": user.google_id,
        "role": user.role.value,
        "iat": int(now.timestamp()),
        "exp": int(expiry.timestamp()),
    }

    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    return AuthToken(
        access_token=token,
        expires_in=settings.jwt_expiry_hours * 3600,
        user=user,
    )


def decode_jwt_token(token: str) -> TokenPayload | None:
    """
    Decode and validate a JWT token. Returns None if invalid/expired.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return TokenPayload(
            sub=payload["sub"],
            name=payload["name"],
            tenant_id=payload.get("tenant_id", "default"),
            workspace_id=payload.get("workspace_id"),
            picture=payload.get("picture"),
            google_id=payload.get("google_id", ""),
            role=UserRole(payload["role"]),
            exp=payload["exp"],
            iat=payload["iat"],
        )
    except Exception as e:
        logger.warning("jwt_decode_failed", error=str(e))
        return None



async def authenticate_with_google(code: str) -> AuthToken:
    """
    Full authentication flow:
    1. Exchange code for tokens
    2. Fetch Google user profile
    3. Check allowlist
    4. Create and return JWT

    Raises:
        PermissionError: If user is not in the allowlist
        httpx.HTTPStatusError: If Google API calls fail
    """
    # Step 1: Exchange code
    tokens = await exchange_code_for_tokens(code)
    access_token = tokens["access_token"]

    # Step 2: Fetch profile
    google_user = await fetch_google_user_info(access_token)
    email = google_user.get("email", "")
    logger.info("google_auth_attempt", email=email)

    # Step 3: Check allowlist
    if not is_email_allowed(email):
        logger.warning("auth_denied_not_in_allowlist", email=email)
        raise PermissionError(
            f"Access denied: {email} is not in the team allowlist. "
            "Contact an admin to get access."
        )

    # Step 4: Determine role from config (no longer hardcoded OPERATOR for everyone)
    email_lower = email.lower()
    settings = get_settings()
    if email_lower in settings.super_admin_emails_list:
        role = UserRole.SUPER_ADMIN
    elif email_lower in settings.tenant_admin_emails_list:
        role = UserRole.TENANT_ADMIN
    else:
        role = UserRole.OPERATOR

    # Derive tenant_id from email domain (enables multi-tenant isolation by org)
    domain = email.split("@")[1] if "@" in email else "default"
    tenant_id = domain if domain else "default"

    user = User(
        email=email,
        name=google_user.get("name", ""),
        picture=google_user.get("picture"),
        google_id=str(google_user.get("id", "")),
        role=role,
        tenant_id=tenant_id,
        last_login=datetime.now(UTC),
    )

    auth_token = create_jwt_token(user)
    logger.info("auth_success", email=email, role=user.role, tenant_id=user.tenant_id)
    return auth_token
