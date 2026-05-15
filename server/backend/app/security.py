from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


PASSWORD_ITERATIONS = 260_000


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso() -> str:
    return utc_now().isoformat()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        _b64_encode(salt),
        _b64_encode(digest),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _b64_decode(salt),
            int(iterations),
        )
        return hmac.compare_digest(_b64_encode(computed), digest)
    except (ValueError, TypeError):
        return False


def generate_secret_urlsafe(bytes_count: int = 32) -> str:
    return secrets.token_urlsafe(bytes_count)


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def create_signed_token(
    secret_key: str,
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    payload: Dict[str, Any] = {
        "sub": subject,
        "typ": token_type,
        "exp": int((utc_now() + expires_delta).timestamp()),
        "iat": int(utc_now().timestamp()),
    }
    if extra:
        payload.update(extra)

    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded_payload = _b64_encode(payload_bytes)
    signature = hmac.new(secret_key.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    return "{}.{}".format(encoded_payload, _b64_encode(signature))


def verify_signed_token(secret_key: str, token: str, expected_type: str) -> Dict[str, Any]:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Malformed token") from exc

    expected_signature = hmac.new(
        secret_key.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(_b64_encode(expected_signature), encoded_signature):
        raise ValueError("Invalid token signature")

    payload = json.loads(_b64_decode(encoded_payload).decode("utf-8"))
    if payload.get("typ") != expected_type:
        raise ValueError("Unexpected token type")
    if int(payload.get("exp", 0)) < int(utc_now().timestamp()):
        raise ValueError("Token expired")
    return payload


def _b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)

