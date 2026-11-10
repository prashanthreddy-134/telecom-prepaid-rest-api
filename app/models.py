
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    ForeignKey,
    Float,
    Text,
    DateTime,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core import Base


class User(Base):
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'staff', 'user')",
            name="ck_user_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(20),
        default="user",
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )


class Circle(Base):
    __tablename__ = "circles"

    id: Mapped[int] = mapped_column(primary_key=True)

    code: Mapped[str] = mapped_column(
        String(12),
        unique=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    state: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )


class Plan(Base):
    __tablename__ = "plans"

    __table_args__ = (
        CheckConstraint(
            "price_paise > 0",
            name="ck_plan_price",
        ),
        CheckConstraint(
            "validity_days > 0",
            name="ck_plan_validity",
        ),
        CheckConstraint(
            "data_mb >= 0",
            name="ck_plan_data",
        ),
        CheckConstraint(
            "voice_minutes >= 0",
            name="ck_plan_voice",
        ),
        CheckConstraint(
            "sms_count >= 0",
            name="ck_plan_sms",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(120),
        index=True,
        nullable=False,
    )

    price_paise: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    validity_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    data_mb: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    voice_minutes: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    sms_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )


class Subscriber(Base):
    __tablename__ = "subscribers"

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'ported_out', 'closed')",
            name="ck_subscriber_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    phone: Mapped[str] = mapped_column(
        String(10),
        unique=True,
        index=True,
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    circle_id: Mapped[int] = mapped_column(
        ForeignKey("circles.id"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        index=True,
        nullable=False,
    )

    current_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("plans.id"),
        nullable=True,
    )


class Recharge(Base):
    __tablename__ = "recharges"

    __table_args__ = (
        CheckConstraint(
            "amount_paise > 0",
            name="ck_recharge_amount",
        ),
        CheckConstraint(
            "status IN ('success')",
            name="ck_recharge_status",
        ),
        UniqueConstraint(
            "reference",
            name="uq_recharge_reference",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("subscribers.id"),
        index=True,
        nullable=False,
    )

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id"),
        nullable=False,
    )

    amount_paise: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    reference: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="success",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Complaint(Base):
    __tablename__ = "complaints"

    __table_args__ = (
        CheckConstraint(
            "source IN ('app', 'call_centre', 'web')",
            name="ck_complaint_source",
        ),
        CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved', 'rejected')",
            name="ck_complaint_status",
        ),
        UniqueConstraint(
            "source",
            "external_ref",
            name="uq_complaint_source_ref",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("subscribers.id"),
        index=True,
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    external_ref: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="open",
        nullable=False,
    )


class UsageRecord(Base):
    __tablename__ = "usage_records"

    __table_args__ = (
        CheckConstraint(
            "usage_mb > 0",
            name="ck_usage_positive",
        ),
        CheckConstraint(
            "source_unit IN ('MB', 'GB')",
            name="ck_usage_source_unit",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("subscribers.id"),
        index=True,
        nullable=False,
    )

    usage_mb: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    source_unit: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
