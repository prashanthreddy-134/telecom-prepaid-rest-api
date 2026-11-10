
import pytest
from pydantic import ValidationError

import app.core as core


class FakeSession:
    def __init__(self):
        self.rollback_called = False
        self.close_called = False

    def rollback(self):
        self.rollback_called = True

    def close(self):
        self.close_called = True


def test_get_db_closes_session_after_normal_use(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(core, "SessionLocal", lambda: session)

    generator = core.get_db()

    assert next(generator) is session

    with pytest.raises(StopIteration):
        next(generator)

    assert session.rollback_called is False
    assert session.close_called is True


def test_get_db_rolls_back_and_closes_after_exception(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(core, "SessionLocal", lambda: session)

    generator = core.get_db()

    assert next(generator) is session

    with pytest.raises(RuntimeError, match="database failure"):
        generator.throw(RuntimeError("database failure"))

    assert session.rollback_called is True
    assert session.close_called is True


def test_settings_accept_valid_configuration(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("PLAN_CACHE_TTL_SECONDS", raising=False)

    settings = core.Settings(
        _env_file=None,
        secret_key="a" * 32,
        plan_cache_ttl_seconds=120,
    )

    assert settings.secret_key == "a" * 32
    assert settings.plan_cache_ttl_seconds == 120


def test_settings_reject_missing_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(ValidationError):
        core.Settings(_env_file=None)


def test_settings_reject_short_secret_key():
    with pytest.raises(ValidationError):
        core.Settings(
            _env_file=None,
            secret_key="too-short",
        )


@pytest.mark.parametrize("ttl", [0, -1, 3601])
def test_settings_reject_invalid_cache_ttl(ttl):
    with pytest.raises(ValidationError):
        core.Settings(
            _env_file=None,
            secret_key="a" * 32,
            plan_cache_ttl_seconds=ttl,
        )


@pytest.mark.parametrize("ttl", [1, 60, 3600])
def test_settings_accept_cache_ttl_boundaries(ttl):
    settings = core.Settings(
        _env_file=None,
        secret_key="a" * 32,
        plan_cache_ttl_seconds=ttl,
    )

    assert settings.plan_cache_ttl_seconds == ttl


def test_sqlite_engine_enables_foreign_keys():
    if not core.is_sqlite:
        pytest.skip("Application database is not SQLite")

    with core.engine.connect() as connection:
        result = connection.exec_driver_sql(
            "PRAGMA foreign_keys"
        ).scalar_one()

    assert result == 1
