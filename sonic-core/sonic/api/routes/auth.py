"""
SONIC-REDA — Auth Routes
============================
Google OAuth2 login/callback/logout and local session endpoints.

Security note:
    The local ``/login`` and ``/dev-token`` endpoints are DEVELOPMENT-ONLY
    conveniences for bootstrapping dashboard sessions without a configured
    Google OAuth client. They are HARD-GATED to ``app_env == "development"`` and,
    even in development, can never elevate a caller to an administrative role
    (``SUPER_ADMIN`` / ``TENANT_ADMIN``). In any non-development environment
    these routes are disabled and authentication is performed exclusively via
    Google OAuth2.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from sonic.auth.google_auth import (
    authenticate_with_google,
    consume_oauth_state,
    create_oauth_state,
    create_jwt_token,
    get_google_login_url,
)
from sonic.auth.middleware import require_auth
from sonic.auth.models import User, UserRole
from sonic.config import get_settings

router = APIRouter()


from pydantic import BaseModel

# Roles that an unauthenticated local-login endpoint may NEVER issue, even in
# development. Administrative roles must come only from verified OAuth2
# callback flow or out-of-band admin configuration — never from a self-asserted
# request body.
_FORBIDDEN_LOCAL_ROLES = {UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN}

# The maximum role the dev login path can grant.
_DEV_LOCAL_ROLE_CEILING = UserRole.OPERATOR


class LoginRequest(BaseModel):
    email: str = "engineer@company.com"
    name: str = "Lead Engineer"
    role: str = "operator"
    tenant_id: str = "default"


def _enforce_dev_only(action: str) -> None:
    """Disable local/unauthenticated auth endpoints outside development."""
    settings = get_settings()
    if not settings.is_dev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{action} is disabled outside development; use /auth/google/login.",
        )


@router.post("/login")
async def login_user(req: LoginRequest):
    """
    Development-only local login.

    Mints an OPERATOR-scoped JWT for the requested tenant user. The requested
    role is clamped to ``OPERATOR`` (or ``AUDITOR``); administrative roles are
    never issued from this unauthenticated endpoint, which prevents privilege
    escalation. Disabled entirely in non-development environments.
    """
    _enforce_dev_only("/auth/login")

    requested = UserRole.OPERATOR
    try:
        if req.role:
            requested = UserRole(req.role.lower())
    except ValueError:
        requested = UserRole.OPERATOR

    # Clamp: never issue an administrative role from the unauthenticated path.
    if requested in _FORBIDDEN_LOCAL_ROLES:
        requested = _DEV_LOCAL_ROLE_CEILING

    user = User(
        email=req.email,
        name=req.name or req.email.split("@")[0].title(),
        role=requested,
        tenant_id=req.tenant_id or "default",
    )
    auth_token = create_jwt_token(user)
    return {
        "status": "success",
        "access_token": auth_token.access_token,
        "token": auth_token.model_dump(),
        "user": user.model_dump(),
    }


@router.post("/dev-token")
async def get_dev_token(email: str = Query("engineer@company.com")):
    """
    Development-only token bootstrap for the dashboard.

    Issues a cryptographically valid but strictly OPERATOR-scoped JWT. Disabled
    entirely in non-development environments; never grants administrative roles.
    """
    _enforce_dev_only("/auth/dev-token")
    user = User(
        email=email,
        name="Lead Engineer",
        role=UserRole.OPERATOR,
        tenant_id="default",
    )
    auth_token = create_jwt_token(user)
    return {
        "status": "success",
        "access_token": auth_token.access_token,
        "token": auth_token.model_dump(),
    }


@router.get("/google/login")
async def google_login(redirect_url: str = Query(default="")):
    """
    Redirect to Google OAuth2 consent screen.

    After login, Google redirects back to /auth/google/callback
    """
    # Only retain a server-side opaque state token.  Never reflect an
    # operator-controlled redirect URL directly into OAuth state.
    login_url = get_google_login_url(state=create_oauth_state(redirect_url))
    return RedirectResponse(url=login_url)


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(..., min_length=16),
):
    """
    Handle Google OAuth2 callback.
    Exchanges authorization code for JWT token.
    """
    if consume_oauth_state(state) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state",
        )
    try:
        auth_token = await authenticate_with_google(code)
        return {
            "status": "success",
            "message": f"Welcome {auth_token.user.name}!",
            "token": auth_token.model_dump(),
        }
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Authentication failed: {str(e)}",
        )


@router.get("/me")
async def get_current_user(user: User = Depends(require_auth)):
    """Get current authenticated user info."""
    return {
        "authenticated": True,
        "user": user.model_dump(),
    }


@router.post("/logout")
async def logout(user: User = Depends(require_auth)):
    """
    Logout current user.
    (Client should discard the JWT token)
    """
    return {
        "status": "logged_out",
        "message": f"Goodbye {user.name}!",
    }
