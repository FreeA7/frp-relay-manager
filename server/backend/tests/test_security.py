from datetime import timedelta

import pytest

from app.security import create_signed_token, verify_signed_token


def test_signed_token_roundtrip():
    token = create_signed_token("secret", "client-1", "agent", timedelta(minutes=5))
    payload = verify_signed_token("secret", token, "agent")

    assert payload["sub"] == "client-1"


def test_signed_token_rejects_wrong_secret():
    token = create_signed_token("secret", "client-1", "agent", timedelta(minutes=5))

    with pytest.raises(ValueError):
        verify_signed_token("other-secret", token, "agent")
