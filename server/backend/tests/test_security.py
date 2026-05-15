from datetime import timedelta

import pytest

from app.security import create_signed_token, hash_password, verify_password, verify_signed_token


def test_password_hash_roundtrip():
    stored = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", stored)
    assert not verify_password("wrong", stored)


def test_signed_token_roundtrip():
    token = create_signed_token("secret", "admin", "admin", timedelta(minutes=5), {"email": "a@example.com"})
    payload = verify_signed_token("secret", token, "admin")

    assert payload["sub"] == "admin"
    assert payload["email"] == "a@example.com"


def test_signed_token_rejects_wrong_secret():
    token = create_signed_token("secret", "admin", "admin", timedelta(minutes=5))

    with pytest.raises(ValueError):
        verify_signed_token("other-secret", token, "admin")
