
from types import SimpleNamespace

import pytest

import app.seed as seed_module

from app.models import (
    User,
    Circle,
    Plan,
    Subscriber,
    Recharge,
    Complaint,
    UsageRecord,
)


class FakeQuery:
    def __init__(self, existing_admin=None):
        self.existing_admin = existing_admin

    def filter_by(self, **kwargs):
        return self

    def first(self):
        return self.existing_admin


class FakeDB:
    def __init__(self, existing_admin=None):
        self.existing_admin = existing_admin
        self.records = []
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.flush_count = 0
        self.add_all_calls = []

    def query(self, model):
        assert model is User
        return FakeQuery(self.existing_admin)

    def add(self, record):
        self.records.append(record)

    def add_all(self, records):
        records = list(records)
        self.add_all_calls.append(records)
        self.records.extend(records)

    def flush(self):
        self.flush_count += 1

        for index, record in enumerate(self.records, start=1):
            if getattr(record, "id", None) is None:
                record.id = index

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.fixture
def fake_seed_environment(monkeypatch):
    db = FakeDB()

    monkeypatch.setattr(
        seed_module.Base.metadata,
        "create_all",
        lambda engine: None,
    )

    monkeypatch.setattr(
        seed_module,
        "engine",
        object(),
    )

    monkeypatch.setattr(
        seed_module,
        "SessionLocal",
        lambda: db,
    )

    monkeypatch.setattr(
        seed_module,
        "hash_pw",
        lambda password: f"hashed:{password}",
    )

    return db


def test_seed_creates_demo_data(
    fake_seed_environment,
    capsys,
):
    db = fake_seed_environment

    seed_module.seed()

    assert db.committed is True
    assert db.rolled_back is False
    assert db.closed is True

    assert db.flush_count == 4

    assert "Database seeded successfully." in capsys.readouterr().out

    assert len([
        record for record in db.records
        if isinstance(record, User)
    ]) == 3

    assert len([
        record for record in db.records
        if isinstance(record, Circle)
    ]) == 3

    assert len([
        record for record in db.records
        if isinstance(record, Plan)
    ]) == 3

    assert len([
        record for record in db.records
        if isinstance(record, Subscriber)
    ]) == 3

    assert len([
        record for record in db.records
        if isinstance(record, Recharge)
    ]) == 1

    assert len([
        record for record in db.records
        if isinstance(record, Complaint)
    ]) == 2

    assert len([
        record for record in db.records
        if isinstance(record, UsageRecord)
    ]) == 2


def test_seed_skips_existing_admin(
    monkeypatch,
    capsys,
):
    existing_admin = SimpleNamespace(
        id=1,
        email="admin@demo.local",
    )

    db = FakeDB(existing_admin=existing_admin)

    monkeypatch.setattr(
        seed_module.Base.metadata,
        "create_all",
        lambda engine: None,
    )

    monkeypatch.setattr(
        seed_module,
        "engine",
        object(),
    )

    monkeypatch.setattr(
        seed_module,
        "SessionLocal",
        lambda: db,
    )

    seed_module.seed()

    assert db.committed is False
    assert db.rolled_back is False
    assert db.closed is True
    assert db.records == []

    assert "Seed data already exists." in capsys.readouterr().out


def test_seed_rolls_back_when_commit_fails(
    monkeypatch,
):
    db = FakeDB()

    def failing_commit():
        raise RuntimeError("Simulated database failure")

    db.commit = failing_commit

    monkeypatch.setattr(
        seed_module.Base.metadata,
        "create_all",
        lambda engine: None,
    )

    monkeypatch.setattr(
        seed_module,
        "engine",
        object(),
    )

    monkeypatch.setattr(
        seed_module,
        "SessionLocal",
        lambda: db,
    )

    monkeypatch.setattr(
        seed_module,
        "hash_pw",
        lambda password: f"hashed:{password}",
    )

    with pytest.raises(RuntimeError):
        seed_module.seed()

    assert db.rolled_back is True
    assert db.closed is True
    assert db.committed is False


def test_seed_closes_session_when_initialization_fails(
    monkeypatch,
):
    db = FakeDB()

    def failing_create_all(engine):
        raise RuntimeError("Schema initialization failed")

    monkeypatch.setattr(
        seed_module.Base.metadata,
        "create_all",
        failing_create_all,
    )

    monkeypatch.setattr(
        seed_module,
        "engine",
        object(),
    )

    monkeypatch.setattr(
        seed_module,
        "SessionLocal",
        lambda: db,
    )

    with pytest.raises(RuntimeError):
        seed_module.seed()

    # Session is created after create_all, so it is not opened.
    assert db.closed is False

