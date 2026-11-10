
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
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
from app.security import hash_pw, make_token


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

    db.add_all([admin, staff, user, inactive_user])
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

    db.add_all([subscriber_user, subscriber_staff])
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


@pytest.fixture()
def client(database):
    with TestClient(app) as test_client:
        yield test_client


def auth_headers(database, email):
    with database() as db:
        user = db.query(User).filter_by(email=email).first()
        assert user is not None

        token = make_token(user)

    return {"Authorization": f"Bearer {token}"}


def admin_headers(database):
    return auth_headers(database, "admin@demo.local")


def staff_headers(database):
    return auth_headers(database, "staff@demo.local")


def user_headers(database):
    return auth_headers(database, "user@demo.local")


def recharge_payload(subscriber_id=1, reference="RECHARGE-TEST-001"):
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


# --------------------------------------------------
# Authentication
# --------------------------------------------------

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
        headers={"Authorization": "Bearer invalid.token.value"},
    )

    assert response.status_code == 401


def test_inactive_user_token_rejected(client, database):
    headers = auth_headers(database, "inactive@demo.local")

    response = client.get(
        "/api/v1/auth/me",
        headers=headers,
    )

    assert response.status_code == 401


# --------------------------------------------------
# Role-based access control
# --------------------------------------------------

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


# --------------------------------------------------
# Plans
# --------------------------------------------------

def test_public_plan_listing(client):
    response = client.get("/api/v1/plans")

    assert response.status_code == 200
    assert len(response.json()) >= 1


# --------------------------------------------------
# Subscribers
# --------------------------------------------------

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


# --------------------------------------------------
# Recharges
# --------------------------------------------------

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

    # The service intentionally hides another user's subscriber.
    assert response.status_code == 404


def test_recharge_duplicate_reference_rejected(client, database):
    headers = user_headers(database)

    first = client.post(
        "/api/v1/recharges",
        json=recharge_payload(reference="DUPLICATE-REF-001"),
        headers=headers,
    )

    second = client.post(
        "/api/v1/recharges",
        json=recharge_payload(reference="DUPLICATE-REF-001"),
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


# --------------------------------------------------
# Complaints
# --------------------------------------------------

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

    # The service intentionally hides another user's subscriber.
    assert response.status_code == 404


def test_complaint_duplicate_reference_rejected(client, database):
    headers = user_headers(database)

    first = client.post(
        "/api/v1/complaints",
        json=complaint_payload(
            external_ref="DUPLICATE-COMPLAINT-001",
        ),
        headers=headers,
    )

    second = client.post(
        "/api/v1/complaints",
        json=complaint_payload(
            external_ref="DUPLICATE-COMPLAINT-001",
        ),
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409


# --------------------------------------------------
# Usage
# --------------------------------------------------

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
