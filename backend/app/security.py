"""口令哈希、无状态会话 Cookie、登录限流。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request

COOKIE_NAME = "vocab_session"

# scrypt 参数：约 50ms/次，适合单用户登录
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
DKLEN = 64

LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 8


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=DKLEN
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    try:
        expected = bytes.fromhex(digest_hex)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(digest, expected)


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(secret: str, payload: str) -> str:
    return _b64encode(hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest())


def make_session(secret: str, ttl_days: int, now: float | None = None) -> str:
    issued = int(now if now is not None else time.time())
    body = {"sub": "owner", "iat": issued, "exp": issued + ttl_days * 86400}
    payload = _b64encode(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    return f"{payload}.{_sign(secret, payload)}"


def verify_session(secret: str, token: str, now: float | None = None) -> dict | None:
    if not secret or not token or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    expected = _sign(secret, payload)
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        body = json.loads(_b64decode(payload))
    except Exception:
        return None
    if not isinstance(body, dict) or body.get("sub") != "owner":
        return None
    current = now if now is not None else time.time()
    if int(body.get("exp", 0)) < current:
        return None
    return body


class LoginLimiter:
    """内存滑动窗口限流；进程重启即清零（单用户场景够用）。"""

    def __init__(self, window_seconds: int = LOGIN_WINDOW_SECONDS, max_failures: int = LOGIN_MAX_FAILURES):
        self.window = window_seconds
        self.max_failures = max_failures
        self._failures: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> list[float]:
        hits = [t for t in self._failures.get(key, []) if now - t < self.window]
        self._failures[key] = hits
        return hits

    def allowed(self, key: str, now: float | None = None) -> bool:
        current = now if now is not None else time.time()
        with self._lock:
            return len(self._prune(key, current)) < self.max_failures

    def record_failure(self, key: str, now: float | None = None) -> None:
        current = now if now is not None else time.time()
        with self._lock:
            self._prune(key, current).append(current)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def require_auth(request: Request) -> dict:
    settings = request.app.state.settings
    token = request.cookies.get(COOKIE_NAME, "")
    body = verify_session(settings.session_secret, token)
    if body is None:
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "message": "请先登录"})
    return body
