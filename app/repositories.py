
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def page(
    db: Session,
    model,
    p: int = 1,
    size: int = 20,
    filters=(),
):
    if p < 1 or not 1 <= size <= 100:
        raise HTTPException(
            status_code=422,
            detail="page >= 1 and size 1..100 required",
        )

    primary_key = model.__mapper__.primary_key

    if not primary_key:
        raise ValueError(
            "Pagination requires a model primary key"
        )

    stmt = (
        select(model)
        .order_by(*primary_key)
    )

    count_stmt = select(
        func.count()
    ).select_from(model)

    for condition in filters:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    items = db.scalars(
        stmt.offset((p - 1) * size).limit(size)
    ).all()

    total = db.scalar(count_stmt) or 0

    return {
        "items": items,
        "total": total,
        "page": p,
        "size": size,
    }


def save(db: Session, obj):
    try:
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Database conflict: duplicate or invalid record",
        )

    except Exception:
        db.rollback()
        raise
