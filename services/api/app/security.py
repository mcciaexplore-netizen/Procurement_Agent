"""Small role gate for the bootstrap admin plane.

Production replaces this token mapping with OIDC claims, but the authorization
boundary and role names remain stable for the API.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from enum import IntEnum

from fastapi import Depends, Header, HTTPException


class AdminRole(IntEnum):
    VIEWER = 1
    OPERATOR = 2
    SOURCE_APPROVER = 3


ROLE_NAMES = {
    "viewer": AdminRole.VIEWER,
    "operator": AdminRole.OPERATOR,
    "source_approver": AdminRole.SOURCE_APPROVER,
}


@dataclass(frozen=True, slots=True)
class AdminPrincipal:
    actor: str
    role: AdminRole


def configured_tokens() -> dict[str, AdminRole]:
    """Read `role:token` pairs from ADMIN_API_TOKENS; retain a dev fallback."""
    configured = os.getenv("ADMIN_API_TOKENS", "")
    tokens: dict[str, AdminRole] = {}
    for pair in filter(None, configured.split(",")):
        role_name, separator, token = pair.partition(":")
        if not separator or role_name not in ROLE_NAMES or not token:
            raise RuntimeError("ADMIN_API_TOKENS must contain comma-separated role:token pairs")
        tokens[token] = ROLE_NAMES[role_name]
    legacy_token = os.getenv("ADMIN_API_TOKEN")
    if legacy_token:
        tokens.setdefault(legacy_token, AdminRole.SOURCE_APPROVER)
    return tokens


def authenticate_admin(
    x_admin_token: str | None = Header(default=None),
    x_actor: str | None = Header(default=None),
) -> AdminPrincipal:
    tokens = configured_tokens()
    if not tokens:
        raise HTTPException(status_code=503, detail="admin endpoints are disabled until an admin token is configured")
    if not x_admin_token:
        raise HTTPException(status_code=401, detail="valid X-Admin-Token required")
    role = next((candidate_role for token, candidate_role in tokens.items() if secrets.compare_digest(x_admin_token, token)), None)
    if not role:
        raise HTTPException(status_code=401, detail="valid X-Admin-Token required")
    return AdminPrincipal(actor=x_actor or "admin", role=role)


def require_role(minimum_role: AdminRole):
    def dependency(principal: AdminPrincipal = Depends(authenticate_admin)) -> AdminPrincipal:
        if principal.role < minimum_role:
            raise HTTPException(status_code=403, detail=f"{minimum_role.name.lower()} role required")
        return principal
    return dependency
