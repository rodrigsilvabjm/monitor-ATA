from app.config import get_settings
from app.services.auth import (
    create_session_token,
    validate_session_token,
    verify_credentials,
)


def test_auth_token_roundtrip() -> None:
    settings = get_settings()
    token = create_session_token(settings.admin_username, settings)
    payload = validate_session_token(token, settings)

    assert payload is not None
    assert payload["sub"] == settings.admin_username


def test_verify_credentials() -> None:
    settings = get_settings()

    assert verify_credentials(settings.admin_username, settings.admin_password, settings)
    assert not verify_credentials(settings.admin_username, "wrong", settings)
