"""
SONIC-REDA — Multi-Tenant RBAC & Auth Middleware
===================================================
FastAPI dependencies validating JWT tokens, enforcing multi-tenant isolation,
and checking enterprise role hierarchies.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sonic.auth.google_auth import decode_jwt_token
from sonic.auth.models import User, UserRole
from sonic.logger import get_logger

logger = get_logger(__name__)

# Bearer token extractor
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User | None:
    """
    Extract and validate JWT token from Authorization header.
    Returns the User with tenant_id if valid, None if no token provided.
    Raises 401 if token is invalid or expired.
    """
    if credentials is None:
        return None

    token = credentials.credentials
    payload = decode_jwt_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return User(
        email=payload.sub,
        name=payload.name,
        tenant_id=payload.tenant_id,
        workspace_id=payload.workspace_id,
        picture=payload.picture,
        google_id=payload.google_id,
        role=payload.role,
    )


async def require_auth(
    user: User | None = Depends(get_current_user),
) -> User:
    """
    Dependency that REQUIRES valid authentication.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(allowed_roles: list[UserRole]) -> Callable:
    """
    Factory dependency requiring the user to have one of the allowed roles.
    SUPER_ADMIN always passes.
    """
    async def _role_checker(user: User = Depends(require_auth)) -> User:
        if user.role == UserRole.SUPER_ADMIN:
            return user

        if user.role not in allowed_roles:
            logger.warning(
                "rbac_access_denied",
                email=user.email,
                tenant_id=user.tenant_id,
                user_role=user.role,
                required_roles=[r.value for r in allowed_roles],
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: requires one of roles {[r.value for r in allowed_roles]}",
            )
        return user

    return _role_checker


# Specialized role dependencies
require_super_admin = require_role([UserRole.SUPER_ADMIN])
require_tenant_admin = require_role([UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN])
require_operator = require_role([UserRole.SUPER_ADMIN, UserRole.TENANT_ADMIN, UserRole.OPERATOR])
require_admin = require_tenant_admin  # Backward compatibility alias


def verify_ws_token(token: str | None) -> User | None:
    """
    Validate JWT token for WebSocket connections (passed as query param or header).
    Returns User with tenant_id if valid, None if invalid or missing.
    """
    if not token:
        return None

    payload = decode_jwt_token(token)
    if payload is None:
        return None

    return User(
        email=payload.sub,
        name=payload.name,
        tenant_id=payload.tenant_id,
        workspace_id=payload.workspace_id,
        picture=payload.picture,
        google_id=payload.google_id,
        role=payload.role,
    )
