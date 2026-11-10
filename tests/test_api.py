
import pytest
import app.main as main_module

from fastapi import HTTPException
from fastapi.testclient import TestClient

from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core import Base, get_db
from app.models import (
    User,
    Circle,
    Plan,
    Subscriber,
    Recharge,
    Complaint,
    UsageRecord,
)
from app.schemas import (
    SubscriberIn,
    RechargeIn,
    UsageIn,
    ComplaintIn,
)
from app.security import hash_pw, make_token
from app.services import (
    commit_record,
    check_subscriber_access,
    add_subscriber,
    add_recharge,
    add_usage,
    add_complaint,
)


# ==================================================
# DATABASE FIXTURE
# ==================================================

@pytest.fixture()
def database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    db = TestingSessionLocal()

    password_hash = hash_pw("AdminPass123!")

    admin = User(
        email="admin@demo.local",
        password_hash=password_hash,
        role="admin",
        is_active=True,
    )

    staff = User(
        email="staff@demo.local",
        password_hash=password_hash,
        role="staff",
        is_active=True,
    )

    user = User(
        email="user@demo.local",
        password_hash=password_hash,
        role="user",
        is_active=True,
    )

    inactive_user = User(
        email="inactive@demo.local",
        password_hash=password_hash,
        role="user",
        is_active=False,
    )

    db.add_all([
        admin,
        staff,
        user,
        inactive_user,
    ])
    db.flush()

    circle = Circle(
        code="AP",
        name="Andhra Pradesh",
        state="Andhra Pradesh",
    )

    db.add(circle)
    db.flush()

    plan = Plan(
        name="Test Unlimited",
        price_paise=29900,
        validity_days=28,
        data_mb=20480,
        voice_minutes=1000,
        sms_count=100,
        description="Test plan",
        is_active=True,
    )

    db.add(plan)
    db.flush()

    subscriber_user = Subscriber(
        user_id=user.id,
        phone="9876543210",
        full_name="Test User",
        circle_id=circle.id,
        status="active",
        current_plan_id=None,
    )

    subscriber_staff = Subscriber(
        user_id=staff.id,
        phone="9876543211",
        full_name="Staff Subscriber",
        circle_id=circle.id,
        status="active",
        current_plan_id=None,
    )

    db.add_all([
        subscriber_user,
        subscriber_staff,
    ])

    db.commit()
    db.close()

    def override_get_db():
        session = TestingSessionLocal()

        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    yield TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# ==================================================
# CLIENT FIXTURE
# ==================================================

@pytest.fixture()
def client(database):
    with TestClient(app) as test_client:
        yield test_client


# ==================================================
# ISOLATED PLAN CACHE FIXTURE
# ==================================================

@pytest.fixture()
def isolated_plan_cache(monkeypatch):
    """
    In-memory fake cache for API tests.

    Tests do not require Docker or a running Redis server.
    Tracks cache reads and actual cache hits.
    """

    store = {}

    state = {
        "generation": 0,
        "cache_reads": 0,
        "cache_hits": 0,
    }

    def fake_get_generation():
        return state["generation"]

    def fake_get_json(key):
        state["cache_reads"] += 1

        if key in store:
            state["cache_hits"] += 1
            return store[key]

        return None

    def fake_set_json(key, value):
        store[key] = value
        return True

    def fake_invalidate():
        state["generation"] += 1
        return True

    monkeypatch.setattr(
        main_module,
        "get_plan_cache_generation",
        fake_get_generation,
    )

    monkeypatch.setattr(
        main_module,
        "get_json",
        fake_get_json,
    )

    monkeypatch.setattr(
        main_module,
        "set_json",
        fake_set_json,
    )

    monkeypatch.setattr(
        main_module,
        "invalidate_plan_cache",
        fake_invalidate,
    )

    return {
        "store": store,
        "state": state,
    }


# ==================================================
# AUTHENTICATION HELPERS
# ==================================================

def auth_headers(database, email):
    with database() as db:
        user = db.query(User).filter_by(email=email).first()
        assert user is not None

        token = make_token(user)

    return {
        "Authorization": f"Bearer {token}"
    }


def admin_headers(database):
    return auth_headers(database, "admin@demo.local")


def staff_headers(database):
    return auth_headers(database, "staff@demo.local")


def user_headers(database):
    return auth_headers(database, "user@demo.local")


def get_test_user(db, email):
    user = db.query(User).filter_by(email=email).first()
    assert user is not None
    return user


# ==================================================
# REQUEST PAYLOAD HELPERS
# ==================================================

def recharge_payload(
    subscriber_id=1,
    reference="RECHARGE-TEST-001",
):
    return {
        "subscriber_id": subscriber_id,
        "plan_id": 1,
        "reference": reference,
    }


def complaint_payload(
    subscriber_id=1,
    external_ref="COMPLAINT-001",
):
    return {
        "subscriber_id": subscriber_id,
        "category": "Network",
        "description": "Network connectivity is not working",
        "source": "app",
        "external_ref": external_ref,
    }


def plan_payload():
    return {
        "name": "New Test Plan",
        "price_paise": 19900,
        "validity_days": 28,
        "data_mb": 10240,
        "voice_minutes": 500,
        "sms_count": 100,
        "description": "Created during API testing",
        "is_active": True,
    }


# ==================================================
# AUTHENTICATION TESTS
# ==================================================

def test_login_success(client):
    response = client.post(
        "/api/v1/auth/token",
        data={
            "username": "admin@demo.local",
            "password": "AdminPass123!",
        },
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"


def test_invalid_login_rejected(client):
    response = client.post(
        "/api/v1/auth/token",
        data={
            "username": "admin@demo.local",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401


def test_current_user_endpoint(client, database):
    response = client.get(
        "/api/v1/auth/me",
        headers=admin_headers(database),
    )

    assert response.status_code == 200
    assert response.json()["email"] == "admin@demo.local"
    assert response.json()["role"] == "admin"


def test_missing_token_rejected(client):
    response = client.post(
        "/api/v1/plans",
        json=plan_payload(),
    )

    assert response.status_code == 401


def test_invalid_token_rejected(client):
    response = client.post(
        "/api/v1/plans",
        json=plan_payload(),
        headers={
            "Authorization": "Bearer invalid.token.value"
        },
    )

    assert response.status_code == 401


def test_inactive_user_token_rejected(client, database):
    headers = auth_headers(
        database,
        "inactive@demo.local",
    )

    response = client.get(
        "/api/v1/auth/me",
        headers=headers,
    )

    assert response.status_code == 401


# ==================================================
# ROLE-BASED ACCESS CONTROL TESTS
# ==================================================

def test_admin_can_create_plan(client, database):
    response = client.post(
        "/api/v1/plans",
        json=plan_payload(),
        headers=admin_headers(database),
    )

    assert response.status_code == 201
    assert response.json()["name"] == "New Test Plan"


def test_staff_cannot_create_plan(client, database):
    response = client.post(
        "/api/v1/plans",
        json=plan_payload(),
        headers=staff_headers(database),
    )

    assert response.status_code == 403


def test_user_cannot_create_plan(client, database):
    response = client.post(
        "/api/v1/plans",
        json=plan_payload(),
        headers=user_headers(database),
    )

    assert response.status_code == 403


def test_admin_can_access_analytics(client, database):
    response = client.get(
        "/api/v1/analytics/summary",
        headers=admin_headers(database),
    )

    assert response.status_code == 200
    assert response.json()["subscribers"] == 2


def test_staff_can_access_analytics(client, database):
    response = client.get(
        "/api/v1/analytics/summary",
        headers=staff_headers(database),
    )

    assert response.status_code == 200


def test_user_cannot_access_analytics(client, database):
    response = client.get(
        "/api/v1/analytics/summary",
        headers=user_headers(database),
    )

    assert response.status_code == 403


# ==================================================
# PLAN TESTS
# ==================================================

def test_public_plan_listing(client):
    response = client.get("/api/v1/plans")

    assert response.status_code == 200

    data = response.json()

    assert len(data["items"]) >= 1
    assert data["total"] >= 1


def test_plan_detail(client):
    response = client.get("/api/v1/plans/1")

    assert response.status_code == 200
    assert response.json()["name"] == "Test Unlimited"


def test_plan_not_found(client):
    response = client.get("/api/v1/plans/999")

    assert response.status_code == 404


# ==================================================
# PLAN CACHE TESTS
# ==================================================

def test_plan_list_cache_hit(client, isolated_plan_cache):
    first = client.get("/api/v1/plans")
    second = client.get("/api/v1/plans")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    assert len(isolated_plan_cache["store"]) == 1
    assert isolated_plan_cache["state"]["cache_reads"] == 2
    assert isolated_plan_cache["state"]["cache_hits"] == 1


def test_plan_detail_cache_hit(client, isolated_plan_cache):
    first = client.get("/api/v1/plans/1")
    second = client.get("/api/v1/plans/1")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    assert len(isolated_plan_cache["store"]) == 1
    assert isolated_plan_cache["state"]["cache_reads"] == 2
    assert isolated_plan_cache["state"]["cache_hits"] == 1


def test_plan_cache_keys_include_filters(
    client,
    isolated_plan_cache,
):
    first = client.get("/api/v1/plans")

    second = client.get(
        "/api/v1/plans?q=Test"
    )

    third = client.get(
        "/api/v1/plans?max_price_paise=30000"
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200

    assert len(isolated_plan_cache["store"]) == 3


def test_plan_create_invalidates_list_cache(
    client,
    database,
    isolated_plan_cache,
):
    first = client.get("/api/v1/plans")

    assert first.status_code == 200
    assert len(first.json()["items"]) == 1

    response = client.post(
        "/api/v1/plans",
        json=plan_payload(),
        headers=admin_headers(database),
    )

    assert response.status_code == 201
    assert isolated_plan_cache["state"]["generation"] == 1

    second = client.get("/api/v1/plans")

    assert second.status_code == 200
    assert len(second.json()["items"]) == 2

    names = [
        item["name"]
        for item in second.json()["items"]
    ]

    assert "New Test Plan" in names


def test_plan_update_invalidates_cached_responses(
    client,
    database,
    isolated_plan_cache,
):
    first = client.get("/api/v1/plans/1")

    assert first.status_code == 200
    assert first.json()["name"] == "Test Unlimited"

    updated_payload = plan_payload()
    updated_payload["name"] = "Updated Unlimited Plan"

    response = client.put(
        "/api/v1/plans/1",
        json=updated_payload,
        headers=admin_headers(database),
    )

    assert response.status_code == 200
    assert isolated_plan_cache["state"]["generation"] == 1

    second = client.get("/api/v1/plans/1")

    assert second.status_code == 200
    assert second.json()["name"] == "Updated Unlimited Plan"

    listing = client.get("/api/v1/plans")

    assert listing.status_code == 200

    names = [
        item["name"]
        for item in listing.json()["items"]
    ]

    assert "Updated Unlimited Plan" in names


def test_plan_deactivation_invalidates_cached_responses(
    client,
    database,
    isolated_plan_cache,
):
    first = client.get("/api/v1/plans/1")

    assert first.status_code == 200

    response = client.delete(
        "/api/v1/plans/1",
        headers=admin_headers(database),
    )

    assert response.status_code == 204
    assert isolated_plan_cache["state"]["generation"] == 1

    detail = client.get("/api/v1/plans/1")

    assert detail.status_code == 404

    listing = client.get("/api/v1/plans")

    assert listing.status_code == 200

    names = [
        item["name"]
        for item in listing.json()["items"]
    ]

    assert "Test Unlimited" not in names


def test_plan_listing_falls_back_when_redis_unavailable(
    client,
    monkeypatch,
):
    def unavailable_generation():
        return None

    def unexpected_cache_access(*args, **kwargs):
        raise AssertionError(
            "Cache should not be accessed when Redis is unavailable"
        )

    monkeypatch.setattr(
        main_module,
        "get_plan_cache_generation",
        unavailable_generation,
    )

    monkeypatch.setattr(
        main_module,
        "get_json",
        unexpected_cache_access,
    )

    monkeypatch.setattr(
        main_module,
        "set_json",
        unexpected_cache_access,
    )

    response = client.get("/api/v1/plans")

    assert response.status_code == 200
    assert len(response.json()["items"]) >= 1


def test_plan_detail_falls_back_when_redis_unavailable(
    client,
    monkeypatch,
):
    def unavailable_generation():
        return None

    def unexpected_cache_access(*args, **kwargs):
        raise AssertionError(
            "Cache should not be accessed when Redis is unavailable"
        )

    monkeypatch.setattr(
        main_module,
        "get_plan_cache_generation",
        unavailable_generation,
    )

    monkeypatch.setattr(
        main_module,
        "get_json",
        unexpected_cache_access,
    )

    monkeypatch.setattr(
        main_module,
        "set_json",
        unexpected_cache_access,
    )

    response = client.get("/api/v1/plans/1")

    assert response.status_code == 200
    assert response.json()["name"] == "Test Unlimited"


# ==================================================
# SUBSCRIBER TESTS
# ==================================================

def test_admin_can_list_subscribers(client, database):
    response = client.get(
        "/api/v1/subscribers",
        headers=admin_headers(database),
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data["items"]) == 2
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["size"] == 20


def test_user_cannot_list_all_subscribers(client, database):
    response = client.get(
        "/api/v1/subscribers",
        headers=user_headers(database),
    )

    assert response.status_code == 403


# ==================================================
# RECHARGE API TESTS
# ==================================================

def test_user_can_recharge_own_subscriber(client, database):
    response = client.post(
        "/api/v1/recharges",
        json=recharge_payload(subscriber_id=1),
        headers=user_headers(database),
    )

    assert response.status_code == 201
    assert response.json()["subscriber_id"] == 1
    assert response.json()["amount_paise"] == 29900
    assert response.json()["status"] == "success"


def test_user_cannot_recharge_another_users_subscriber(
    client,
    database,
):
    response = client.post(
        "/api/v1/recharges",
        json=recharge_payload(
            subscriber_id=2,
            reference="RECHARGE-OTHER-001",
        ),
        headers=user_headers(database),
    )

    assert response.status_code == 404


def test_recharge_duplicate_reference_rejected(client, database):
    headers = user_headers(database)

    first = client.post(
        "/api/v1/recharges",
        json=recharge_payload(
            reference="DUPLICATE-REF-001"
        ),
        headers=headers,
    )

    second = client.post(
        "/api/v1/recharges",
        json=recharge_payload(
            reference="DUPLICATE-REF-001"
        ),
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_recharge_invalid_subscriber_rejected(client, database):
    response = client.post(
        "/api/v1/recharges",
        json=recharge_payload(subscriber_id=999),
        headers=user_headers(database),
    )

    assert response.status_code == 404


# ==================================================
# COMPLAINT API TESTS
# ==================================================

def test_user_can_create_own_complaint(client, database):
    response = client.post(
        "/api/v1/complaints",
        json=complaint_payload(subscriber_id=1),
        headers=user_headers(database),
    )

    assert response.status_code == 201
    assert response.json()["subscriber_id"] == 1
    assert response.json()["status"] == "open"


def test_user_cannot_complain_for_another_users_subscriber(
    client,
    database,
):
    response = client.post(
        "/api/v1/complaints",
        json=complaint_payload(
            subscriber_id=2,
            external_ref="OTHER-USER-COMPLAINT-001",
        ),
        headers=user_headers(database),
    )

    assert response.status_code == 404


def test_complaint_duplicate_reference_rejected(client, database):
    headers = user_headers(database)

    first = client.post(
        "/api/v1/complaints",
        json=complaint_payload(
            external_ref="DUPLICATE-COMPLAINT-001"
        ),
        headers=headers,
    )

    second = client.post(
        "/api/v1/complaints",
        json=complaint_payload(
            external_ref="DUPLICATE-COMPLAINT-001"
        ),
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409


# ==================================================
# USAGE API TESTS
# ==================================================

def test_usage_normalization(client, database):
    response = client.post(
        "/api/v1/usage",
        json={
            "subscriber_id": 1,
            "amount": 2,
            "unit": "GB",
        },
        headers=admin_headers(database),
    )

    assert response.status_code == 201
    assert response.json()["usage_mb"] == 2048
    assert response.json()["source_unit"] == "GB"


def test_user_cannot_create_usage(client, database):
    response = client.post(
        "/api/v1/usage",
        json={
            "subscriber_id": 1,
            "amount": 100,
            "unit": "MB",
        },
        headers=user_headers(database),
    )

    assert response.status_code == 403


# ==================================================
# SERVICE TESTS: COMMIT RECORD
# ==================================================

def test_commit_record_success():
    class FakeDB:
        def __init__(self):
            self.added = None
            self.committed = False
            self.refreshed = False

        def add(self, record):
            self.added = record

        def commit(self):
            self.committed = True

        def refresh(self, record):
            self.refreshed = True

    db = FakeDB()
    record = object()

    result = commit_record(db, record)

    assert result is record
    assert db.added is record
    assert db.committed is True
    assert db.refreshed is True


def test_commit_record_integrity_error_rolls_back():
    class FakeDB:
        def __init__(self):
            self.rolled_back = False

        def add(self, record):
            pass

        def commit(self):
            raise IntegrityError(
                "statement",
                {},
                Exception("integrity failure"),
            )

        def rollback(self):
            self.rolled_back = True

    db = FakeDB()

    with pytest.raises(HTTPException) as exc:
        commit_record(db, object())

    assert exc.value.status_code == 409
    assert db.rolled_back is True


def test_commit_record_unexpected_error_rolls_back():
    class FakeDB:
        def __init__(self):
            self.rolled_back = False

        def add(self, record):
            pass

        def commit(self):
            raise RuntimeError("Database unavailable")

        def rollback(self):
            self.rolled_back = True

    db = FakeDB()

    with pytest.raises(RuntimeError):
        commit_record(db, object())

    assert db.rolled_back is True


# ==================================================
# SERVICE TESTS: SUBSCRIBER ACCESS
# ==================================================

@pytest.mark.parametrize("role", ["admin", "staff"])
def test_check_subscriber_access_allows_admin_and_staff(
    database,
    role,
):
    with database() as db:
        subscriber = db.query(Subscriber).filter_by(
            phone="9876543210"
        ).first()

        actor = get_test_user(
            db,
            f"{role}@demo.local",
        )

        assert check_subscriber_access(
            subscriber,
            actor,
        ) is None


def test_check_subscriber_access_allows_owner(database):
    with database() as db:
        subscriber = db.query(Subscriber).filter_by(
            phone="9876543210"
        ).first()

        owner = get_test_user(db, "user@demo.local")

        assert check_subscriber_access(
            subscriber,
            owner,
        ) is None


def test_check_subscriber_access_hides_other_users_subscriber(
    database,
):
    with database() as db:
        subscriber = db.query(Subscriber).filter_by(
            phone="9876543210"
        ).first()

        other_user = get_test_user(
            db,
            "inactive@demo.local",
        )

        with pytest.raises(HTTPException) as exc:
            check_subscriber_access(
                subscriber,
                other_user,
            )

        assert exc.value.status_code == 404


# ==================================================
# SERVICE TESTS: ADD SUBSCRIBER
# ==================================================

def test_add_subscriber_success(database):
    with database() as db:
        staff = get_test_user(db, "staff@demo.local")

        data = SubscriberIn(
            phone="9876543222",
            full_name="New Subscriber",
            circle_id=1,
        )

        result = add_subscriber(db, data, staff)

        assert result.id is not None
        assert result.phone == "9876543222"
        assert result.user_id == staff.id


def test_add_subscriber_rejects_regular_user(database):
    with database() as db:
        user = get_test_user(db, "user@demo.local")

        data = SubscriberIn(
            phone="9876543223",
            full_name="Unauthorized Subscriber",
            circle_id=1,
        )

        with pytest.raises(HTTPException) as exc:
            add_subscriber(db, data, user)

        assert exc.value.status_code == 403


def test_add_subscriber_rejects_missing_circle(database):
    with database() as db:
        staff = get_test_user(db, "staff@demo.local")

        data = SubscriberIn(
            phone="9876543224",
            full_name="Missing Circle",
            circle_id=9999,
        )

        with pytest.raises(HTTPException) as exc:
            add_subscriber(db, data, staff)

        assert exc.value.status_code == 404


def test_add_subscriber_rejects_missing_plan(database):
    with database() as db:
        staff = get_test_user(db, "staff@demo.local")

        data = SubscriberIn(
            phone="9876543225",
            full_name="Missing Plan",
            circle_id=1,
            current_plan_id=9999,
        )

        with pytest.raises(HTTPException) as exc:
            add_subscriber(db, data, staff)

        assert exc.value.status_code == 404


def test_add_subscriber_rejects_inactive_plan(database):
    with database() as db:
        staff = get_test_user(db, "staff@demo.local")

        plan = db.get(Plan, 1)
        plan.is_active = False
        db.commit()

        data = SubscriberIn(
            phone="9876543226",
            full_name="Inactive Plan",
            circle_id=1,
            current_plan_id=plan.id,
        )

        with pytest.raises(HTTPException) as exc:
            add_subscriber(db, data, staff)

        assert exc.value.status_code == 409


def test_add_subscriber_rejects_duplicate_phone(database):
    with database() as db:
        staff = get_test_user(db, "staff@demo.local")

        data = SubscriberIn(
            phone="9876543210",
            full_name="Duplicate Phone",
            circle_id=1,
        )

        with pytest.raises(HTTPException) as exc:
            add_subscriber(db, data, staff)

        assert exc.value.status_code == 409


def test_add_subscriber_rejects_missing_owner(database):
    with database() as db:
        staff = get_test_user(db, "staff@demo.local")

        data = SubscriberIn(
            phone="9876543227",
            full_name="Missing Owner",
            circle_id=1,
            user_id=9999,
        )

        with pytest.raises(HTTPException) as exc:
            add_subscriber(db, data, staff)

        assert exc.value.status_code == 404


def test_add_subscriber_rejects_inactive_owner(database):
    with database() as db:
        staff = get_test_user(db, "staff@demo.local")
        inactive_user = get_test_user(
            db,
            "inactive@demo.local",
        )

        data = SubscriberIn(
            phone="9876543228",
            full_name="Inactive Owner",
            circle_id=1,
            user_id=inactive_user.id,
        )

        with pytest.raises(HTTPException) as exc:
            add_subscriber(db, data, staff)

        assert exc.value.status_code == 404


def test_add_subscriber_accepts_existing_plan(database):
    with database() as db:
        staff = get_test_user(db, "staff@demo.local")

        data = SubscriberIn(
            phone="9876543229",
            full_name="Plan Subscriber",
            circle_id=1,
            current_plan_id=1,
        )

        result = add_subscriber(db, data, staff)

        assert result.current_plan_id == 1
        assert result.user_id == staff.id


def test_add_subscriber_admin_can_assign_owner(database):
    with database() as db:
        admin = get_test_user(db, "admin@demo.local")
        owner = get_test_user(db, "user@demo.local")

        data = SubscriberIn(
            phone="9876543230",
            full_name="Assigned Subscriber",
            circle_id=1,
            user_id=owner.id,
        )

        result = add_subscriber(db, data, admin)

        assert result.user_id == owner.id


# ==================================================
# SERVICE TESTS: ADD RECHARGE
# ==================================================

def test_add_recharge_uses_database_plan_price(database):
    with database() as db:
        subscriber = db.query(Subscriber).filter_by(
            phone="9876543210"
        ).first()

        user = get_test_user(db, "user@demo.local")

        data = RechargeIn(
            subscriber_id=subscriber.id,
            plan_id=1,
            reference="TEST-RECHARGE-001",
        )

        result = add_recharge(db, data, user)

        assert result.id is not None
        assert result.amount_paise == 29900
        assert result.status == "success"
        assert result.reference == "TEST-RECHARGE-001"

        db.refresh(subscriber)
        assert subscriber.current_plan_id == 1


def test_add_recharge_rejects_missing_subscriber(database):
    with database() as db:
        user = get_test_user(db, "user@demo.local")

        data = RechargeIn(
            subscriber_id=9999,
            plan_id=1,
            reference="TEST-RECHARGE-002",
        )

        with pytest.raises(HTTPException) as exc:
            add_recharge(db, data, user)

        assert exc.value.status_code == 404


def test_add_recharge_rejects_another_users_subscriber(database):
    with database() as db:
        subscriber = db.query(Subscriber).filter_by(
            phone="9876543211"
        ).first()

        user = get_test_user(db, "user@demo.local")

        data = RechargeIn(
            subscriber_id=subscriber.id,
            plan_id=1,
            reference="TEST-RECHARGE-003",
        )

        with pytest.raises(HTTPException) as exc:
            add_recharge(db, data, user)

        assert exc.value.status_code == 404


def test_add_recharge_rejects_missing_plan(database):
    with database() as db:
        subscriber = db.query(Subscriber).filter_by(
            phone="9876543210"
        ).first()

        user = get_test_user(db, "user@demo.local")

        data = RechargeIn(
            subscriber_id=subscriber.id,
            plan_id=9999,
            reference="TEST-RECHARGE-004",
        )

        with pytest.raises(HTTPException) as exc:
            add_recharge(db, data, user)

        assert exc.value.status_code == 404


def test_add_recharge_rejects_inactive_subscriber(database):
    with database() as db:
        subscriber = db.query(Subscriber).filter_by(
            phone="9876543210"
        ).first()

        subscriber.status = "suspended"
        db.commit()

        user = get_test_user(db, "user@demo.local")

        data = RechargeIn(
            subscriber_id=subscriber.id,
            plan_id=1,
            reference="TEST-RECHARGE-005",
        )

        with pytest.raises(HTTPException) as exc:
            add_recharge(db, data, user)

        assert exc.value.status_code == 409


def test_add_recharge_rejects_inactive_plan(database):
    with database() as db:
        subscriber = db.query(Subscriber).filter_by(
            phone="9876543210"
        ).first()

        plan = db.get(Plan, 1)
        plan.is_active = False
        db.commit()

        user = get_test_user(db, "user@demo.local")

        data = RechargeIn(
            subscriber_id=subscriber.id,
            plan_id=plan.id,
            reference="TEST-RECHARGE-006",
        )

        with pytest.raises(HTTPException) as exc:
            add_recharge(db, data, user)

        assert exc.value.status_code == 409


def test_add_recharge_rejects_duplicate_reference(database):
    with database() as db:
        subscriber = db.query(Subscriber).filter_by(
            phone="9876543210"
        ).first()

        user = get_test_user(db, "user@demo.local")

        first_data = RechargeIn(
            subscriber_id=subscriber.id,
            plan_id=1,
            reference="TEST-RECHARGE-DUPLICATE",
        )

        add_recharge(db, first_data, user)

        duplicate_data = RechargeIn(
            subscriber_id=subscriber.id,
            plan_id=1,
            reference="TEST-RECHARGE-DUPLICATE",
        )

        with pytest.raises(HTTPException) as exc:
            add_recharge(db, duplicate_data, user)

        assert exc.value.status_code == 409


# ==================================================
# SERVICE TESTS: ADD USAGE
# ==================================================

@pytest.mark.parametrize(
    ("amount", "unit", "expected_mb"),
    [
        ("1.5", "GB", 1536.0),
        ("500", "MB", 500.0),
        ("2", "GB", 2048.0),
    ],
)
def test_add_usage_converts_units(
    database,
    amount,
    unit,
    expected_mb,
):
    with database() as db:
        subscriber = db.query(Subscriber).filter_by(
            phone="9876543210"
        ).first()

        data = UsageIn(
            subscriber_id=subscriber.id,
            amount=amount,
            unit=unit,
        )

        result = add_usage(db, data)

        assert result.id is not None
        assert result.usage_mb == expected_mb
        assert result.source_unit == unit


def test_add_usage_rejects_missing_subscriber(database):
    with database() as db:
        data = UsageIn(
            subscriber_id=9999,
            amount="100",
            unit="MB",
        )

        with pytest.raises(HTTPException) as exc:
            add_usage(db, data)

        assert exc.value.status_code == 404


def test_add_usage_rejects_inactive_subscriber(database):
    with database() as db:
        subscriber = db.query(Subscriber).filter_by(
            phone="9876543210"
        ).first()

        subscriber.status = "suspended"
        db.commit()

        data = UsageIn(
            subscriber_id=subscriber.id,
            amount="100",
            unit="MB",
        )

        with pytest.raises(HTTPException) as exc:
            add_usage(db, data)

        assert exc.value.status_code == 409


# ==================================================
# SERVICE TESTS: ADD COMPLAINT
# ==================================================

def test_add_complaint_success(database):
    with database() as db:
        subscriber = db.query(Subscriber).filter_by(
            phone="9876543210"
        ).first()

        user = get_test_user(db, "user@demo.local")

        data = ComplaintIn(
            subscriber_id=subscriber.id,
            category="Network",
            description="Network connection is unavailable",
            source="app",
            external_ref="TEST-COMPLAINT-001",
        )

        result = add_complaint(db, data, user)

        assert result.id is not None
        assert result.external_ref == "TEST-COMPLAINT-001"
        assert result.subscriber_id == subscriber.id


def test_add_complaint_rejects_missing_subscriber(database):
    with database() as db:
        user = get_test_user(db, "user@demo.local")

        data = ComplaintIn(
            subscriber_id=9999,
            category="Network",
            description="Network connection is unavailable",
            source="app",
            external_ref="TEST-COMPLAINT-002",
        )

        with pytest.raises(HTTPException) as exc:
            add_complaint(db, data, user)

        assert exc.value.status_code == 404


def test_add_complaint_rejects_another_users_subscriber(database):
    with database() as db:
        subscriber = db.query(Subscriber).filter_by(
            phone="9876543211"
        ).first()

        user = get_test_user(db, "user@demo.local")

        data = ComplaintIn(
            subscriber_id=subscriber.id,
            category="Network",
            description="Network connection is unavailable",
            source="app",
            external_ref="TEST-COMPLAINT-003",
        )

        with pytest.raises(HTTPException) as exc:
            add_complaint(db, data, user)

        assert exc.value.status_code == 404


def test_add_complaint_rejects_duplicate_reference(database):
    with database() as db:
        subscriber = db.query(Subscriber).filter_by(
            phone="9876543210"
        ).first()

        user = get_test_user(db, "user@demo.local")

        data = ComplaintIn(
            subscriber_id=subscriber.id,
            category="Network",
            description="Network connection is unavailable",
            source="app",
            external_ref="TEST-COMPLAINT-DUPLICATE",
        )

        add_complaint(db, data, user)

        duplicate = ComplaintIn(
            subscriber_id=subscriber.id,
            category="Network",
            description="Another network complaint",
            source="app",
            external_ref="TEST-COMPLAINT-DUPLICATE",
        )

        with pytest.raises(HTTPException) as exc:
            add_complaint(db, duplicate, user)

        assert exc.value.status_code == 409
 
# ==================================================
# SYSTEM ENDPOINT TESTS
# ==================================================

def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_endpoint(client):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "connected",
    }


def test_readiness_database_failure(client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    class BrokenDB:
        def execute(self, statement):
            raise OperationalError(
                "SELECT 1",
                {},
                Exception("Database unavailable"),
            )

        def close(self):
            pass

    def override_broken_db():
        yield BrokenDB()

    app.dependency_overrides[get_db] = override_broken_db

    try:
        response = client.get("/ready")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"


# ==================================================
# REGISTRATION TESTS
# ==================================================

def test_register_success(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@demo.local",
            "password": "NewUserPass123!",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "newuser@demo.local"
    assert response.json()["role"] == "user"
    assert response.json()["is_active"] is True


def test_register_duplicate_email_rejected(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@demo.local",
            "password": "NewUserPass123!",
        },
    )

    assert response.status_code == 409


def test_register_normalizes_email(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "  NEWUSER@DEMO.LOCAL  ",
            "password": "NewUserPass123!",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "newuser@demo.local"


def test_register_rejects_invalid_email(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "invalid-email",
            "password": "NewUserPass123!",
        },
    )

    assert response.status_code == 422


def test_register_rejects_short_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "shortpass@demo.local",
            "password": "short",
        },
    )

    assert response.status_code == 422


# ==================================================
# CIRCLE API TESTS
# ==================================================

def circle_payload(
    code="KA",
    name="Karnataka",
    state="Karnataka",
):
    return {
        "code": code,
        "name": name,
        "state": state,
    }


def test_public_circle_listing(client):
    response = client.get("/api/v1/circles")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert len(response.json()["items"]) == 1


def test_circle_search(client):
    response = client.get(
        "/api/v1/circles?q=Andhra"
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_circle_search_without_match(client):
    response = client.get(
        "/api/v1/circles?q=Nonexistent"
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_circle_detail(client):
    response = client.get("/api/v1/circles/1")

    assert response.status_code == 200
    assert response.json()["code"] == "AP"


def test_circle_not_found(client):
    response = client.get("/api/v1/circles/999")

    assert response.status_code == 404


def test_admin_can_create_circle(client, database):
    response = client.post(
        "/api/v1/circles",
        json=circle_payload(),
        headers=admin_headers(database),
    )

    assert response.status_code == 201
    assert response.json()["code"] == "KA"


def test_staff_cannot_create_circle(client, database):
    response = client.post(
        "/api/v1/circles",
        json=circle_payload(),
        headers=staff_headers(database),
    )

    assert response.status_code == 403


def test_user_cannot_create_circle(client, database):
    response = client.post(
        "/api/v1/circles",
        json=circle_payload(),
        headers=user_headers(database),
    )

    assert response.status_code == 403


def test_circle_create_duplicate_code_rejected(
    client,
    database,
):
    response = client.post(
        "/api/v1/circles",
        json=circle_payload(
            code="AP",
            name="Another Andhra",
            state="Andhra",
        ),
        headers=admin_headers(database),
    )

    assert response.status_code == 409


def test_admin_can_update_circle(client, database):
    response = client.put(
        "/api/v1/circles/1",
        json=circle_payload(
            code="AP",
            name="Updated Andhra Pradesh",
            state="Andhra Pradesh",
        ),
        headers=admin_headers(database),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Andhra Pradesh"


def test_circle_update_not_found(client, database):
    response = client.put(
        "/api/v1/circles/999",
        json=circle_payload(),
        headers=admin_headers(database),
    )

    assert response.status_code == 404


def test_circle_update_duplicate_code_rejected(
    client,
    database,
):
    with database() as db:
        db.add(
            Circle(
                code="KA",
                name="Karnataka",
                state="Karnataka",
            )
        )
        db.commit()

    response = client.put(
        "/api/v1/circles/1",
        json=circle_payload(
            code="KA",
            name="Andhra Updated",
            state="Andhra Pradesh",
        ),
        headers=admin_headers(database),
    )

    assert response.status_code == 409


def test_circle_delete_rejects_circle_with_subscribers(
    client,
    database,
):
    response = client.delete(
        "/api/v1/circles/1",
        headers=admin_headers(database),
    )

    assert response.status_code == 409


def test_circle_delete_success(client, database):
    create_response = client.post(
        "/api/v1/circles",
        json=circle_payload(
            code="TN",
            name="Tamil Nadu",
            state="Tamil Nadu",
        ),
        headers=admin_headers(database),
    )

    assert create_response.status_code == 201

    circle_id = create_response.json()["id"]

    response = client.delete(
        f"/api/v1/circles/{circle_id}",
        headers=admin_headers(database),
    )

    assert response.status_code == 204

    detail = client.get(
        f"/api/v1/circles/{circle_id}"
    )

    assert detail.status_code == 404


def test_circle_delete_not_found(client, database):
    response = client.delete(
        "/api/v1/circles/999",
        headers=admin_headers(database),
    )

    assert response.status_code == 404


# ==================================================
# ADDITIONAL PLAN TESTS
# ==================================================

def test_plan_update_not_found(client, database):
    response = client.put(
        "/api/v1/plans/999",
        json=plan_payload(),
        headers=admin_headers(database),
    )

    assert response.status_code == 404


def test_plan_delete_not_found(client, database):
    response = client.delete(
        "/api/v1/plans/999",
        headers=admin_headers(database),
    )

    assert response.status_code == 404


def test_staff_cannot_update_plan(client, database):
    response = client.put(
        "/api/v1/plans/1",
        json=plan_payload(),
        headers=staff_headers(database),
    )

    assert response.status_code == 403


def test_staff_cannot_delete_plan(client, database):
    response = client.delete(
        "/api/v1/plans/1",
        headers=staff_headers(database),
    )

    assert response.status_code == 403


def test_plan_list_supports_all_filters(client):
    response = client.get(
        "/api/v1/plans"
        "?q=Test"
        "&max_price_paise=30000"
        "&min_data_mb=10000"
        "&page_num=1"
        "&size=10"
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_plan_list_rejects_invalid_pagination(client):
    response = client.get(
        "/api/v1/plans?page_num=0"
    )

    assert response.status_code == 422


def test_plan_list_rejects_invalid_size(client):
    response = client.get(
        "/api/v1/plans?size=101"
    )

    assert response.status_code == 422


def test_plan_list_rejects_invalid_price_filter(client):
    response = client.get(
        "/api/v1/plans?max_price_paise=0"
    )

    assert response.status_code == 422


# ==================================================
# ADDITIONAL SUBSCRIBER TESTS
# ==================================================

def test_subscriber_detail(client, database):
    response = client.get(
        "/api/v1/subscribers/1",
        headers=admin_headers(database),
    )

    assert response.status_code == 200
    assert response.json()["phone"] == "9876543210"


def test_subscriber_detail_not_found(client, database):
    response = client.get(
        "/api/v1/subscribers/999",
        headers=admin_headers(database),
    )

    assert response.status_code == 404


def test_admin_can_create_subscriber(client, database):
    response = client.post(
        "/api/v1/subscribers",
        json={
            "phone": "9876543231",
            "full_name": "New API Subscriber",
            "circle_id": 1,
        },
        headers=admin_headers(database),
    )

    assert response.status_code == 201
    assert response.json()["phone"] == "9876543231"


def test_admin_can_filter_subscribers(client, database):
    response = client.get(
        "/api/v1/subscribers?q=Test&status=active&circle_id=1",
        headers=admin_headers(database),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_subscriber_update_success(client, database):
    response = client.put(
        "/api/v1/subscribers/1",
        json={
            "phone": "9876543210",
            "full_name": "Updated Test User",
            "circle_id": 1,
            "status": "suspended",
            "current_plan_id": 1,
            "user_id": 3,
        },
        headers=admin_headers(database),
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated Test User"
    assert response.json()["status"] == "suspended"

    with database() as db:
        subscriber = db.get(Subscriber, 1)
        assert subscriber.user_id == 3


def test_subscriber_update_not_found(client, database):
    response = client.put(
        "/api/v1/subscribers/999",
        json={
            "phone": "9876543232",
            "full_name": "Missing Subscriber",
            "circle_id": 1,
        },
        headers=admin_headers(database),
    )

    assert response.status_code == 404


def test_subscriber_update_missing_circle(client, database):
    response = client.put(
        "/api/v1/subscribers/1",
        json={
            "phone": "9876543210",
            "full_name": "Updated User",
            "circle_id": 999,
        },
        headers=admin_headers(database),
    )

    assert response.status_code == 404


def test_subscriber_update_missing_plan(client, database):
    response = client.put(
        "/api/v1/subscribers/1",
        json={
            "phone": "9876543210",
            "full_name": "Updated User",
            "circle_id": 1,
            "current_plan_id": 999,
        },
        headers=admin_headers(database),
    )

    assert response.status_code == 404


def test_subscriber_update_inactive_plan(client, database):
    with database() as db:
        plan = db.get(Plan, 1)
        plan.is_active = False
        db.commit()

    response = client.put(
        "/api/v1/subscribers/1",
        json={
            "phone": "9876543210",
            "full_name": "Updated User",
            "circle_id": 1,
            "current_plan_id": 1,
        },
        headers=admin_headers(database),
    )

    assert response.status_code == 409


def test_admin_can_close_subscriber(client, database):
    response = client.delete(
        "/api/v1/subscribers/1",
        headers=admin_headers(database),
    )

    assert response.status_code == 204

    with database() as db:
        subscriber = db.get(Subscriber, 1)
        assert subscriber.status == "closed"


def test_subscriber_close_not_found(client, database):
    response = client.delete(
        "/api/v1/subscribers/999",
        headers=admin_headers(database),
    )

    assert response.status_code == 404


def test_staff_cannot_close_subscriber(client, database):
    response = client.delete(
        "/api/v1/subscribers/1",
        headers=staff_headers(database),
    )

    assert response.status_code == 403


# ==================================================
# RECHARGE LIST TESTS
# ==================================================

def test_admin_can_list_recharges(client, database):
    response = client.get(
        "/api/v1/recharges",
        headers=admin_headers(database),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_staff_can_filter_recharges(client, database):
    headers = admin_headers(database)

    created = client.post(
        "/api/v1/recharges",
        json=recharge_payload(
            reference="FILTER-RECHARGE-001"
        ),
        headers=headers,
    )

    assert created.status_code == 201

    response = client.get(
        "/api/v1/recharges?subscriber_id=1",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_user_cannot_list_recharges(client, database):
    response = client.get(
        "/api/v1/recharges",
        headers=user_headers(database),
    )

    assert response.status_code == 403


# ==================================================
# COMPLAINT LIST AND STATUS TESTS
# ==================================================

def test_admin_can_list_complaints(client, database):
    response = client.get(
        "/api/v1/complaints",
        headers=admin_headers(database),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_complaint_listing_with_filters(client, database):
    headers = user_headers(database)

    created = client.post(
        "/api/v1/complaints",
        json=complaint_payload(
            external_ref="FILTER-COMPLAINT-001"
        ),
        headers=headers,
    )

    assert created.status_code == 201

    response = client.get(
        "/api/v1/complaints?status=open&subscriber_id=1",
        headers=admin_headers(database),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_user_cannot_list_complaints(client, database):
    response = client.get(
        "/api/v1/complaints",
        headers=user_headers(database),
    )

    assert response.status_code == 403


def test_admin_can_update_complaint_status(client, database):
    created = client.post(
        "/api/v1/complaints",
        json=complaint_payload(
            external_ref="STATUS-COMPLAINT-001"
        ),
        headers=user_headers(database),
    )

    assert created.status_code == 201

    complaint_id = created.json()["id"]

    response = client.patch(
        f"/api/v1/complaints/{complaint_id}/status"
        "?status=resolved",
        headers=admin_headers(database),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "resolved"


def test_complaint_status_update_not_found(client, database):
    response = client.patch(
        "/api/v1/complaints/999/status?status=resolved",
        headers=admin_headers(database),
    )

    assert response.status_code == 404


def test_user_cannot_update_complaint_status(client, database):
    response = client.patch(
        "/api/v1/complaints/1/status?status=resolved",
        headers=user_headers(database),
    )

    assert response.status_code == 403


def test_complaint_status_rejects_invalid_value(
    client,
    database,
):
    response = client.patch(
        "/api/v1/complaints/1/status?status=invalid",
        headers=admin_headers(database),
    )

    assert response.status_code == 422


# ==================================================
# USAGE LIST TESTS
# ==================================================

def test_admin_can_list_usage(client, database):
    response = client.get(
        "/api/v1/usage",
        headers=admin_headers(database),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_usage_listing_with_subscriber_filter(
    client,
    database,
):
    created = client.post(
        "/api/v1/usage",
        json={
            "subscriber_id": 1,
            "amount": 500,
            "unit": "MB",
        },
        headers=admin_headers(database),
    )

    assert created.status_code == 201

    response = client.get(
        "/api/v1/usage?subscriber_id=1",
        headers=admin_headers(database),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_user_cannot_list_usage(client, database):
    response = client.get(
        "/api/v1/usage",
        headers=user_headers(database),
    )

    assert response.status_code == 403
