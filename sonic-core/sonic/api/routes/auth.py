"""
SONIC-REDA — Auth Routes
============================
Google OAuth2 login/callback/logout endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from sonic.auth.google_auth import (
    authenticate_with_google,
    get_google_login_url,
)
from sonic.auth.middleware import require_auth
from sonic.auth.models import AuthToken, User

router = APIRouter()


@router.get("/google/login")
async def google_login(redirect_url: str = Query(default="")):
    """
    Redirect to Google OAuth2 consent screen.
    
    After login, Google redirects back to /auth/google/callback
    """
    login_url = get_google_login_url(state=redirect_url)
    return RedirectResponse(url=login_url)


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(default=""),
):
    """
    Handle Google OAuth2 callback.
    Exchanges authorization code for JWT token.
    """
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
