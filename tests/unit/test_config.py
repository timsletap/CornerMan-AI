"""PLT-04: Settings refuses insecure values when APP_ENV is production."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.config import DEFAULT_SECRET_KEY, Settings

STRONG_SECRET = "x" * 32


def make_settings(**overrides: Any) -> Settings:
    # _env_file=None so a developer's local backend/.env cannot affect the result
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_production_with_default_secret_raises() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY must be changed"):
        make_settings(APP_ENV="production", SECRET_KEY=DEFAULT_SECRET_KEY, DEBUG=False)


def test_production_with_short_secret_raises() -> None:
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        make_settings(APP_ENV="production", SECRET_KEY="x" * 31, DEBUG=False)


def test_production_with_debug_raises() -> None:
    with pytest.raises(ValidationError, match="DEBUG must be false"):
        make_settings(APP_ENV="production", SECRET_KEY=STRONG_SECRET, DEBUG=True)


def test_production_with_32_byte_secret_and_debug_off_passes() -> None:
    s = make_settings(APP_ENV="production", SECRET_KEY=STRONG_SECRET, DEBUG=False)
    assert s.APP_ENV == "production"


def test_development_with_default_secret_passes() -> None:
    s = make_settings(APP_ENV="development", SECRET_KEY=DEFAULT_SECRET_KEY, DEBUG=True)
    assert s.SECRET_KEY == DEFAULT_SECRET_KEY
