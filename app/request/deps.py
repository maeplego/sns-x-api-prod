from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.core.models import User
from app.request.auth import get_current_user

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "user": [],
    "moderator": [
        "post.hide",
        "user.suspend",
        "label.write",
        "report.read",
        "report.resolve",
    ],
    "admin": [
        "post.hide",
        "user.suspend",
        "label.write",
        "report.read",
        "report.resolve",
        "role.grant",
        "audit.read",
        "user.erase",
    ],
}


def permissions_for_role(role: str) -> set[str]:
    return set(ROLE_PERMISSIONS.get(role, []))


def require_permissions(*perms: str) -> Callable:
    async def _dependency(user: User = Depends(get_current_user)) -> User:
        granted = permissions_for_role(user.role)
        if not all(permission in granted for permission in perms):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _dependency
