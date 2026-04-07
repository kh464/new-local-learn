from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
import jwt
from fastapi import HTTPException, Request, status

from app.core.audit import emit_audit_event
from app.core.config import Settings
from app.storage.task_store import RedisTaskStore

_FULL_ACCESS_SCOPES = frozenset(
    {
        "analyze:create",
        "tasks:read",
        "tasks:write",
        "artifacts:read",
        "metrics:read",
        "audit:read",
    }
)


@dataclass(frozen=True)
class AuthPrincipal:
    subject: str
    scopes: frozenset[str]
    source: str


_OIDC_JWKS_CACHE: dict[str, tuple[float, dict[str, object]]] = {}


def _parse_api_key_record(record: str) -> tuple[str, str, tuple[str, ...]]:
    try:
        subject, key, scopes_part = record.split(":", 2)
    except ValueError as exc:
        raise ValueError(f"Invalid API key record: {record}") from exc

    scopes = tuple(scope.strip() for scope in scopes_part.split("|") if scope.strip())
    return subject.strip(), key.strip(), scopes


def _resolve_api_key_principal(settings: Settings, provided: str | None) -> AuthPrincipal | None:
    if not provided:
        return None

    for record in tuple(getattr(settings, "api_key_records", ())):
        subject, key, scopes = _parse_api_key_record(record)
        if provided == key:
            return AuthPrincipal(subject=subject, scopes=frozenset(scopes), source="scoped_api_key")

    for index, key in enumerate(tuple(getattr(settings, "api_keys", ()))):
        if provided == key:
            return AuthPrincipal(subject=f"legacy-{index + 1}", scopes=_FULL_ACCESS_SCOPES, source="legacy_api_key")

    return None


def _oidc_enabled(settings: Settings) -> bool:
    return bool(
        getattr(settings, "oidc_issuer_url", None)
        and getattr(settings, "oidc_audience", None)
        and getattr(settings, "oidc_jwks_url", None)
    )


async def fetch_oidc_jwks(url: str, *, ttl_seconds: int = 300) -> dict[str, object]:
    cached = _OIDC_JWKS_CACHE.get(url)
    now = time.time()
    if cached is not None and cached[0] > now:
        return cached[1]

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
        raise ValueError("OIDC JWKS response is invalid.")

    _OIDC_JWKS_CACHE[url] = (now + max(ttl_seconds, 1), payload)
    return payload


def _extract_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "").strip()
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    return token or None


def _extract_scopes_from_claims(payload: dict[str, object], claim_name: str) -> frozenset[str]:
    raw = payload.get(claim_name)
    if isinstance(raw, str):
        scopes = [part.strip() for part in raw.split(" ") if part.strip()]
        return frozenset(scopes)
    if isinstance(raw, (list, tuple, set)):
        scopes = [str(part).strip() for part in raw if str(part).strip()]
        return frozenset(scopes)
    for fallback_name in ("scope", "scp"):
        if fallback_name == claim_name:
            continue
        fallback = payload.get(fallback_name)
        if isinstance(fallback, str):
            return frozenset(part.strip() for part in fallback.split(" ") if part.strip())
        if isinstance(fallback, (list, tuple, set)):
            return frozenset(str(part).strip() for part in fallback if str(part).strip())
    return frozenset()


async def _resolve_oidc_principal(settings: Settings, token: str | None) -> AuthPrincipal | None:
    if not _oidc_enabled(settings) or not token:
        return None

    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    jwks = await fetch_oidc_jwks(
        str(settings.oidc_jwks_url),
        ttl_seconds=int(getattr(settings, "oidc_jwks_cache_seconds", 300)),
    )
    jwk_records = [record for record in jwks.get("keys", []) if isinstance(record, dict)]
    signing_jwk = None
    if kid is not None:
        for record in jwk_records:
            if record.get("kid") == kid:
                signing_jwk = record
                break
    elif len(jwk_records) == 1:
        signing_jwk = jwk_records[0]

    if signing_jwk is None:
        raise ValueError("OIDC signing key was not found.")

    signing_key = jwt.PyJWK.from_dict(signing_jwk).key
    payload = jwt.decode(
        token,
        signing_key,
        algorithms=tuple(getattr(settings, "oidc_algorithms", ("RS256",))),
        audience=str(settings.oidc_audience),
        issuer=str(settings.oidc_issuer_url),
    )
    subject_claim = str(getattr(settings, "oidc_subject_claim", "sub"))
    subject = payload.get(subject_claim) or payload.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("OIDC subject claim is missing.")

    scope_claim = str(getattr(settings, "oidc_scope_claim", "scope"))
    return AuthPrincipal(
        subject=subject.strip(),
        scopes=_extract_scopes_from_claims(payload, scope_claim),
        source="oidc_bearer",
    )


async def _authenticate_service_principal(
    request: Request,
    settings: Settings,
    store: RedisTaskStore | None = None,
) -> AuthPrincipal | None:
    provided = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    principal = _resolve_api_key_principal(settings, provided)
    if principal is not None:
        return principal

    bearer_token = _extract_bearer_token(request)
    if bearer_token is None:
        return None

    try:
        return await _resolve_oidc_principal(settings, bearer_token)
    except Exception as exc:
        if store is not None:
            await store.increment_metric("oidc_auth_failures_total")
        await emit_audit_event(
            request,
            action="oidc_auth",
            outcome="denied",
            store=store,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _service_auth_enabled(settings: Settings) -> bool:
    api_keys = tuple(getattr(settings, "api_keys", ()))
    api_key_records = tuple(getattr(settings, "api_key_records", ()))
    return bool(api_keys or api_key_records or _oidc_enabled(settings))


def _missing_service_credentials_error(settings: Settings) -> HTTPException:
    if _oidc_enabled(settings):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key.",
        headers={"WWW-Authenticate": "ApiKey"},
    )


async def require_api_key(request: Request, settings: Settings, store: RedisTaskStore | None = None) -> AuthPrincipal | None:
    return await require_api_key_scopes(request, settings, required_scopes=(), store=store)


async def require_api_key_scopes(
    request: Request,
    settings: Settings,
    *,
    required_scopes: tuple[str, ...] = (),
    store: RedisTaskStore | None = None,
) -> AuthPrincipal | None:
    if not _service_auth_enabled(settings):
        return None

    principal = await _authenticate_service_principal(request, settings, store)
    if principal is None:
        if store is not None:
            metric_name = "oidc_auth_failures_total" if _oidc_enabled(settings) else "api_auth_failures_total"
            await store.increment_metric(metric_name)
        await emit_audit_event(
            request,
            action="oidc_auth" if _oidc_enabled(settings) else "api_key_auth",
            outcome="denied",
            store=store,
        )
        raise _missing_service_credentials_error(settings)

    if required_scopes and not set(required_scopes).issubset(principal.scopes):
        if store is not None:
            metric_name = "oidc_auth_failures_total" if principal.source == "oidc_bearer" else "api_auth_failures_total"
            await store.increment_metric(metric_name)
        await emit_audit_event(
            request,
            action="oidc_scope" if principal.source == "oidc_bearer" else "api_key_scope",
            outcome="denied",
            subject=principal.subject,
            required_scopes=list(required_scopes),
            store=store,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Bearer token is not authorized for this action."
                if principal.source == "oidc_bearer"
                else "API key is not authorized for this action."
            ),
        )

    return principal


async def require_task_access(
    request: Request,
    task_id: str,
    settings: Settings,
    store: RedisTaskStore,
) -> AuthPrincipal | None:
    return await require_task_access_scopes(
        request,
        task_id,
        settings,
        store,
        required_scopes=("tasks:read",),
    )


async def require_task_access_scopes(
    request: Request,
    task_id: str,
    settings: Settings,
    store: RedisTaskStore,
    *,
    required_scopes: tuple[str, ...],
) -> AuthPrincipal | None:
    if not _service_auth_enabled(settings):
        return None

    principal = await _authenticate_service_principal(request, settings, store)
    if principal is not None:
        if required_scopes and not set(required_scopes).issubset(principal.scopes):
            metric_name = "oidc_auth_failures_total" if principal.source == "oidc_bearer" else "task_auth_failures_total"
            await store.increment_metric(metric_name)
            await emit_audit_event(
                request,
                action="oidc_scope" if principal.source == "oidc_bearer" else "task_access_scope",
                outcome="denied",
                task_id=task_id,
                subject=principal.subject,
                required_scopes=list(required_scopes),
                store=store,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Bearer token is not authorized for this action."
                    if principal.source == "oidc_bearer"
                    else "API key is not authorized for this action."
                ),
            )
        return principal

    task_token = request.headers.get("X-Task-Token") or request.query_params.get("task_token")
    if task_token and await store.has_task_access_token(task_id, task_token):
        return None

    await store.increment_metric("task_auth_failures_total")
    await emit_audit_event(
        request,
        action="oidc_auth" if _oidc_enabled(settings) else "task_access_auth",
        outcome="denied",
        task_id=task_id,
        store=store,
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing bearer token." if _oidc_enabled(settings) else "Invalid or missing task access token.",
        headers={"WWW-Authenticate": "Bearer" if _oidc_enabled(settings) else "ApiKey"},
    )
