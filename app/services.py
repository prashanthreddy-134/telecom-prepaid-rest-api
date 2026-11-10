
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    User,
    Circle,
    Plan,
    Subscriber,
    Recharge,
    Complaint,
    UsageRecord,
)


def commit_record(db: Session, record):
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Database conflict: duplicate or invalid record",
        )

    except Exception:
        db.rollback()
        raise


def check_subscriber_access(
    subscriber: Subscriber,
    user: User,
):
    # Admin and staff can access all subscribers.
    if user.role in ("admin", "staff"):
        return

    # Hide another user's subscriber record.
    if subscriber.user_id != user.id:
        raise HTTPException(
            status_code=404,
            detail="Subscriber not found",
        )


def add_subscriber(
    db: Session,
    d,
    actor: User,
):
    # Defense-in-depth authorization.
    if actor.role not in ("admin", "staff"):
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions",
        )

    circle = db.get(Circle, d.circle_id)

    if not circle:
        raise HTTPException(
            status_code=404,
            detail="Circle not found",
        )

    if d.current_plan_id is not None:
        plan = db.get(Plan, d.current_plan_id)

        if not plan:
            raise HTTPException(
                status_code=404,
                detail="Plan not found",
            )

        if not plan.is_active:
            raise HTTPException(
                status_code=409,
                detail="Plan is inactive",
            )

    existing_subscriber = db.scalar(
        select(Subscriber).where(
            Subscriber.phone == d.phone
        )
    )

    if existing_subscriber:
        raise HTTPException(
            status_code=409,
            detail="Phone already exists",
        )

    # Assign creator as owner if no owner was supplied.
    owner_id = (
        d.user_id
        if d.user_id is not None
        else actor.id
    )

    owner = db.get(User, owner_id)

    if not owner or not owner.is_active:
        raise HTTPException(
            status_code=404,
            detail="Active subscriber owner not found",
        )

    subscriber_data = d.model_dump(
        exclude={"user_id"}
    )

    subscriber = Subscriber(
        **subscriber_data,
        user_id=owner_id,
    )

    return commit_record(db, subscriber)


def add_recharge(
    db: Session,
    d,
    actor: User,
):
    subscriber = db.get(
        Subscriber,
        d.subscriber_id,
    )

    if not subscriber:
        raise HTTPException(
            status_code=404,
            detail="Subscriber not found",
        )

    check_subscriber_access(subscriber, actor)

    plan = db.get(Plan, d.plan_id)

    if not plan:
        raise HTTPException(
            status_code=404,
            detail="Plan not found",
        )

    if subscriber.status != "active":
        raise HTTPException(
            status_code=409,
            detail="Subscriber is not active",
        )

    if not plan.is_active:
        raise HTTPException(
            status_code=409,
            detail="Plan is inactive",
        )

    existing_recharge = db.scalar(
        select(Recharge).where(
            Recharge.reference == d.reference
        )
    )

    if existing_recharge:
        raise HTTPException(
            status_code=409,
            detail="Duplicate recharge reference",
        )

    # Never trust a client-supplied recharge amount.
    # Use the actual plan price from the database.
    recharge = Recharge(
        subscriber_id=subscriber.id,
        plan_id=plan.id,
        amount_paise=plan.price_paise,
        reference=d.reference,
        status="success",
    )

    try:
        db.add(recharge)

        # Update current plan in the same transaction.
        subscriber.current_plan_id = plan.id

        db.commit()
        db.refresh(recharge)

        return recharge

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Recharge reference already exists "
                "or database constraint failed"
            ),
        )

    except Exception:
        db.rollback()
        raise


def add_usage(
    db: Session,
    d,
):
    subscriber = db.get(
        Subscriber,
        d.subscriber_id,
    )

    if not subscriber:
        raise HTTPException(
            status_code=404,
            detail="Subscriber not found",
        )

    if subscriber.status != "active":
        raise HTTPException(
            status_code=409,
            detail="Subscriber is not active",
        )

    # Convert GB to MB using 1 GB = 1024 MB.
    usage_mb = d.amount * (
        1024 if d.unit == "GB" else 1
    )

    record = UsageRecord(
        subscriber_id=subscriber.id,
        usage_mb=float(usage_mb),
        source_unit=d.unit,
    )

    return commit_record(db, record)


def add_complaint(
    db: Session,
    d,
    actor: User,
):
    subscriber = db.get(
        Subscriber,
        d.subscriber_id,
    )

    if not subscriber:
        raise HTTPException(
            status_code=404,
            detail="Subscriber not found",
        )

    check_subscriber_access(subscriber, actor)

    duplicate = db.scalar(
        select(Complaint).where(
            Complaint.source == d.source,
            Complaint.external_ref == d.external_ref,
        )
    )

    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="Duplicate source reference",
        )

    complaint = Complaint(
        **d.model_dump()
    )

    return commit_record(db, complaint)
