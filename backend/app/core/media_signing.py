"""Short-lived signed URLs for endpoints the browser loads without headers (PLT-03).

Used by <video src> streams and the EventSource progress stream (PLT-07).

URL params: ``exp`` (unix seconds) and ``sig`` = hex HMAC-SHA256 over
``"{resource_type}:{resource_id}:{exp}"``. The key is derived from SECRET_KEY with HKDF
(info ``"media-url"``) so it is never the same key that signs JWTs.
"""

import hashlib
import hmac
import time
import uuid
from functools import lru_cache
from typing import Literal

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings

MediaResourceType = Literal["video", "annotated", "events"]


@lru_cache(maxsize=4)
def _derive_key(secret_key: str) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"media-url")
    return hkdf.derive(secret_key.encode())


def _media_key() -> bytes:
    return _derive_key(settings.SECRET_KEY)


def sign(resource_type: str, resource_id: uuid.UUID | str, exp: int) -> str:
    """Hex signature for a resource that expires at ``exp`` (unix seconds)."""
    message = f"{resource_type}:{resource_id}:{exp}".encode()
    return hmac.new(_media_key(), message, hashlib.sha256).hexdigest()


def verify(
    resource_type: str,
    resource_id: uuid.UUID | str,
    exp: int,
    sig: str,
    now: float | None = None,
) -> bool:
    """True if ``sig`` is valid for the resource and ``exp`` (unix seconds) has not passed."""
    if exp < (time.time() if now is None else now):
        return False
    return hmac.compare_digest(sign(resource_type, resource_id, exp), sig)


def new_expiry(ttl_seconds: int | None = None) -> int:
    """Expiry timestamp (unix seconds) ``ttl_seconds`` from now; defaults to config."""
    ttl = settings.MEDIA_URL_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    return int(time.time()) + ttl
