import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cloudsentinel_control.config import Settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Actor:
    name: str
    role: str


def _matches(supplied: str, expected: str) -> bool:
    if not supplied or not expected:
        return False
    return secrets.compare_digest(supplied, expected)


def identify(token: str, settings: Settings) -> Actor | None:
    if _matches(token, settings.admin_token):
        return Actor("admin", "admin")
    if _matches(token, settings.reader_token):
        return Actor("reader", "reader")
    if _matches(token, settings.gateway_token):
        return Actor("gateway", "gateway")
    return None


def require_reader(settings: Settings):
    async def dependency(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Actor:
        actor = _actor(credentials, settings)
        if actor.role not in {"admin", "reader"}:
            raise HTTPException(status_code=403, detail="This token cannot read the control plane.")
        return actor

    return dependency


def require_routing_client(settings: Settings):
    """Readers, admins, and the gateway may see the current route. Nothing else is shared."""

    async def dependency(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Actor:
        actor = _actor(credentials, settings)
        if actor.role not in {"admin", "reader", "gateway"}:
            raise HTTPException(status_code=403, detail="This token cannot read the routing decision.")
        return actor

    return dependency


def require_admin(settings: Settings):
    async def dependency(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Actor:
        actor = _actor(credentials, settings)
        if actor.role != "admin":
            raise HTTPException(status_code=403, detail="This action requires the admin token.")
        return actor

    return dependency


def require_gateway(settings: Settings):
    async def dependency(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Actor:
        actor = _actor(credentials, settings)
        if actor.role not in {"admin", "gateway"}:
            raise HTTPException(status_code=403, detail="This action requires the gateway token.")
        return actor

    return dependency


def _actor(credentials: HTTPAuthorizationCredentials | None, settings: Settings) -> Actor:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="A bearer token is required.")
    actor = identify(credentials.credentials, settings)
    if actor is None:
        raise HTTPException(status_code=401, detail="The bearer token was rejected.")
    return actor
