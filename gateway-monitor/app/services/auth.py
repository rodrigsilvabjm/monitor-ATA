import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException, Request, status

from app.config import Settings, get_settings


def verify_credentials(username: str, password: str, settings: Settings) -> bool:
    return hmac.compare_digest(username, settings.admin_username) and hmac.compare_digest(
        password,
        settings.admin_password,
    )


def create_session_token(username: str, settings: Settings) -> str:
    expires_at = int(time.time()) + settings.session_duration_minutes * 60
    payload = {"sub": username, "exp": expires_at}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload_bytes).decode("ascii")
    signature = sign_value(encoded_payload, settings.secret_key)
    return f"{encoded_payload}.{signature}"


def validate_session_token(token: str, settings: Settings) -> dict[str, Any] | None:
    try:
        encoded_payload, signature = token.split(".", maxsplit=1)
    except ValueError:
        return None

    expected_signature = sign_value(encoded_payload, settings.secret_key)
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded_payload.encode("ascii")))
    except Exception:
        return None

    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


def sign_value(value: str, secret_key: str) -> str:
    digest = hmac.new(
        secret_key.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


def get_current_user(request: Request) -> str | None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None

    payload = validate_session_token(token, settings)
    if not payload:
        return None
    return str(payload["sub"])


def require_current_user(request: Request) -> str:
    user = get_current_user(request)
    if user:
        return user
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
