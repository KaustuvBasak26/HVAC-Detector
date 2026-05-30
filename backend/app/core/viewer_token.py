from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException

from app.core.config import settings

_TOKEN_PAD = "="
_runtime_secret: str | None = None


def ensure_viewer_token_secret() -> None:
    global _runtime_secret
    if not settings.secure_deployment:
        return
    if settings.viewer_token_secret.strip():
        return
    _runtime_secret = secrets.token_urlsafe(32)


def _secret_bytes() -> bytes:
    secret = settings.viewer_token_secret.strip() or (_runtime_secret or "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail={"code": "SERVER_MISCONFIGURED", "message": "Viewer token secret is not set."},
        )
    return secret.encode()


def create_viewer_token(job_id: str) -> str:
    expiry = int(time.time()) + settings.viewer_token_ttl_seconds
    body = f"{job_id}:{expiry}"
    sig = hmac.new(_secret_bytes(), body.encode(), hashlib.sha256).hexdigest()
    raw = f"{body}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip(_TOKEN_PAD)


def verify_viewer_token(job_id: str, token: str | None) -> None:
    if not settings.secure_deployment:
        return
    if not token:
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Missing viewer token."})
    try:
        padded = token + (_TOKEN_PAD * (-len(token) % 4))
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        body, sig = raw.rsplit(":", 1)
        expected = hmac.new(_secret_bytes(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        token_job_id, expiry_raw = body.split(":", 1)
        if token_job_id != job_id:
            raise ValueError("job mismatch")
        if int(expiry_raw) < int(time.time()):
            raise ValueError("expired")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Invalid or expired viewer token."},
        ) from None
