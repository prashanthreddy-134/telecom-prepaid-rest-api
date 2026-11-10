
from app.core import Base, engine, SessionLocal
from app.models import (
    User,
    Circle,
    Plan,
    Subscriber,
    Recharge,
    Complaint,
    UsageRecord,
)
from app.security import hash_pw


def seed():
    Base.metadata.create_all(engine)

    db = SessionLocal()

    try:
        # Prevent accidental duplicate seed records.
        existing_admin = db.query(User).filter_by(
            email="admin@demo.local"
        ).first()

        if existing_admin:
            print("Seed data already exists.")
            return

        # 1. Create users first.
        admin = User(
            email="admin@demo.local",
            password_hash=hash_pw("AdminPass123!"),
            role="admin",
        )

        staff = User(
            email="staff@demo.local",
            password_hash=hash_pw("StaffPass123!"),
            role="staff",
        )

        normal_user = User(
            email="user@demo.local",
            password_hash=hash_pw("UserPass123!"),
            role="user",
        )

        db.add_all([admin, staff, normal_user])
        db.flush()

        # 2. Create telecom circles.
        circles = [
            Circle(
                code="GJ",
                name="Gujarat",
                state="Gujarat",
            ),
            Circle(
                code="MH",
                name="Maharashtra",
                state="Maharashtra",
            ),
            Circle(
                code="DL",
                name="Delhi",
                state="Delhi",
            ),
        ]

        db.add_all(circles)
        db.flush()

        # 3. Create prepaid plans.
        plans = [
            Plan(
                name="Starter 28",
                price_paise=19900,
                validity_days=28,
                data_mb=20480,
                voice_minutes=1000,
                sms_count=100,
                description="Starter prepaid plan",
            ),
            Plan(
                name="Value 56",
                price_paise=39900,
                validity_days=56,
                data_mb=61440,
                voice_minutes=2000,
                sms_count=200,
                description="Value prepaid plan",
            ),
            Plan(
                name="Power 84",
                price_paise=59900,
                validity_days=84,
                data_mb=102400,
                voice_minutes=3000,
                sms_count=300,
                description="Power prepaid plan",
            ),
        ]

        db.add_all(plans)
        db.flush()

        # 4. Create subscribers.
        # All three demo subscribers belong to the normal demo user.
        subscribers = [
            Subscriber(
                user_id=normal_user.id,
                phone="9876500001",
                full_name="Aarav Shah",
                circle_id=circles[0].id,
                status="active",
                current_plan_id=plans[0].id,
            ),
            Subscriber(
                user_id=normal_user.id,
                phone="9876500002",
                full_name="Mira Patel",
                circle_id=circles[0].id,
                status="ported_out",
                current_plan_id=plans[1].id,
            ),
            Subscriber(
                user_id=normal_user.id,
                phone="9876500003",
                full_name="Kabir Desai",
                circle_id=circles[1].id,
                status="suspended",
                current_plan_id=None,
            ),
        ]

        db.add_all(subscribers)
        db.flush()

        # 5. Create recharge history.
        recharges = [
            Recharge(
                subscriber_id=subscribers[0].id,
                plan_id=plans[0].id,
                amount_paise=19900,
                reference="SEED-RECHARGE-001",
                status="success",
            ),
        ]

        db.add_all(recharges)

        # 6. Create complaints.
        complaints = [
            Complaint(
                subscriber_id=subscribers[0].id,
                category="network",
                description="Dropped calls",
                source="app",
                external_ref="APP-001",
                status="open",
            ),
            Complaint(
                subscriber_id=subscribers[0].id,
                category="network",
                description="Dropped calls",
                source="call_centre",
                external_ref="CC-001",
                status="open",
            ),
        ]

        db.add_all(complaints)

        # 7. Create usage records.
        usage_records = [
            UsageRecord(
                subscriber_id=subscribers[0].id,
                usage_mb=1536,
                source_unit="MB",
            ),
            UsageRecord(
                subscriber_id=subscribers[0].id,
                usage_mb=2048,
                source_unit="GB",
            ),
        ]

        db.add_all(usage_records)

        # Save everything together.
        db.commit()

        print("Database seeded successfully.")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed()
