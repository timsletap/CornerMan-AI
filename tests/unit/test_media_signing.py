"""PLT-03: media URL signing primitives."""

import hashlib
import hmac
import time
import uuid

from app.config import settings
from app.core import media_signing

RID = uuid.UUID("12345678-1234-5678-1234-567812345678")


def test_round_trip() -> None:
    sig = media_signing.sign("video", RID, 2_000)
    assert media_signing.verify("video", RID, 2_000, sig, now=1_000)


def test_expiry_boundary() -> None:
    sig = media_signing.sign("video", RID, 2_000)
    assert media_signing.verify("video", RID, 2_000, sig, now=2_000)
    assert not media_signing.verify("video", RID, 2_000, sig, now=2_001)


def test_key_is_derived_not_the_raw_secret() -> None:
    raw = hmac.new(settings.SECRET_KEY.encode(), f"video:{RID}:2000".encode(), hashlib.sha256)
    assert media_signing.sign("video", RID, 2_000) != raw.hexdigest()


def test_signature_binds_type_id_and_exp() -> None:
    sig = media_signing.sign("video", RID, 2_000)
    assert not media_signing.verify("annotated", RID, 2_000, sig, now=0)
    assert not media_signing.verify("video", uuid.uuid4(), 2_000, sig, now=0)
    assert not media_signing.verify("video", RID, 2_001, sig, now=0)
    flipped = sig[:-1] + ("1" if sig[-1] == "0" else "0")
    assert not media_signing.verify("video", RID, 2_000, flipped, now=0)


def test_new_expiry_uses_configured_ttl() -> None:
    exp = media_signing.new_expiry()
    assert 0 < exp - time.time() <= settings.MEDIA_URL_TTL_SECONDS
