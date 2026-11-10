
import json
import logging
import time
from typing import Literal

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core import get_db, settings
from app.cache import (
    get_plan_cache_generation,
    get_json,
    set_json,
    invalidate_plan_cache,
    build_plan_list_cache_key,
    build_plan_detail_cache_key,
)
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
    Register,
    UserOut,
    Token,
    CircleIn,
    CircleOut,
    CircleListOut,
    PlanIn,
    PlanOut,
    PlanListOut,
    SubscriberIn,
    SubscriberOut,
    SubscriberListOut,
    RechargeIn,
    RechargeOut,
    RechargeListOut,
    ComplaintIn,
    ComplaintOut,
    ComplaintListOut,
    UsageIn,
    UsageOut,
    UsageListOut,
)
from app.security import (
    hash_pw,
    verify_pw,
    make_token,
    current_user,
    roles,
)
from app.repositories import page, save
from app.services import (
    add_subscriber,
    add_recharge,
    add_usage,
    add_complaint,
)


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="Telecom Prepaid REST API",
    version="1.0.0",
    description=(
        "Prepaid plans, subscriber lifecycle, recharge, "
        "complaint and usage API."
    ),
)


# ============================================================
# RATE LIMITING
# ============================================================

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit],
)

app.state.limiter = limiter

app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)


# ============================================================
# REQUEST LOGGING
# ============================================================

logger = logging.getLogger(__name__)


@app.middleware("http")
async def log_request(request: Request, call_next):
    start = time.perf_counter()

    response = await call_next(request)

    logger.info(
        json.dumps(
            {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(
                    (time.perf_counter() - start) * 1000,
                    2,
                ),
            }
        )
    )

    return response


# ============================================================
# GLOBAL EXCEPTION HANDLER
# ============================================================

@app.exception_handler(Exception)
async def safe_error(request: Request, exc: Exception):
    logger.exception("Unhandled API error")

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ============================================================
# HEALTH AND READINESS
# ============================================================

@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(select(1))
        return {"status": "ready", "database": "connected"}

    except SQLAlchemyError:
        logger.exception("Database readiness check failed")

        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "unavailable",
            },
        )


# ============================================================
# AUTHENTICATION
# ============================================================

@app.post(
    "/api/v1/auth/register",
    response_model=UserOut,
    status_code=201,
    tags=["auth"],
)
def register(
    d: Register,
    db: Session = Depends(get_db),
):
    existing_user = db.query(User).filter_by(
        email=d.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email exists",
        )

    user = User(
        email=d.email,
        password_hash=hash_pw(d.password),
        role="user",
    )

    return save(db, user)


@app.post(
    "/api/v1/auth/token",
    response_model=Token,
    tags=["auth"],
)
@limiter.limit("10/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter_by(
            email=form_data.username.strip().lower()
        )
        .first()
    )

    if (
        not user
        or not user.is_active
        or not verify_pw(
            form_data.password,
            user.password_hash,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect credentials or inactive account",
        )

    return {
        "access_token": make_token(user),
        "token_type": "bearer",
    }


@app.get(
    "/api/v1/auth/me",
    response_model=UserOut,
    tags=["auth"],
)
def me(
    u=Depends(current_user),
):
    return u


# ============================================================
# PLANS
# Public: list and view.
# Admin: create, update and deactivate.
# Redis cache: list and detail endpoints.
# ============================================================

@app.get(
    "/api/v1/plans",
    response_model=PlanListOut,
    tags=["plans"],
)
@limiter.limit("200/minute")
def plans(
    request: Request,
    q: str | None = None,
    max_price_paise: int | None = Query(
        default=None,
        ge=1,
    ),
    min_data_mb: int | None = Query(
        default=None,
        ge=0,
    ),
    page_num: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    normalized_q = q.strip() if q and q.strip() else None

    generation = get_plan_cache_generation()
    cache_key = None

    if generation is not None:
        cache_key = build_plan_list_cache_key(
            generation,
            normalized_q,
            max_price_paise,
            min_data_mb,
            page_num,
            size,
        )

        cached = get_json(cache_key)

        if cached is not None:
            return cached

    filters = [Plan.is_active.is_(True)]

    if normalized_q:
        filters.append(
            Plan.name.ilike(f"%{normalized_q}%")
        )

    if max_price_paise is not None:
        filters.append(
            Plan.price_paise <= max_price_paise
        )

    if min_data_mb is not None:
        filters.append(
            Plan.data_mb >= min_data_mb
        )

    result = page(
        db,
        Plan,
        page_num,
        size,
        filters,
    )

    response = PlanListOut.model_validate(
        result
    ).model_dump(mode="json")

    if cache_key is not None:
        set_json(cache_key, response)

    return response


@app.get(
    "/api/v1/plans/{id}",
    response_model=PlanOut,
    tags=["plans"],
)
def plan(
    id: int,
    db: Session = Depends(get_db),
):
    generation = get_plan_cache_generation()
    cache_key = None

    if generation is not None:
        cache_key = build_plan_detail_cache_key(
            generation,
            id,
        )

        cached = get_json(cache_key)

        if cached is not None:
            return cached

    record = db.get(Plan, id)

    if not record or not record.is_active:
        raise HTTPException(
            status_code=404,
            detail="Plan not found",
        )

    response = PlanOut.model_validate(
        record
    ).model_dump(mode="json")

    if cache_key is not None:
        set_json(cache_key, response)

    return response


@app.post(
    "/api/v1/plans",
    response_model=PlanOut,
    status_code=201,
    tags=["plans"],
)
def plan_create(
    d: PlanIn,
    db: Session = Depends(get_db),
    u=Depends(roles("admin")),
):
    record = save(
        db,
        Plan(**d.model_dump()),
    )

    # Invalidate cached plan responses after successful creation.
    invalidate_plan_cache()

    return record


@app.put(
    "/api/v1/plans/{id}",
    response_model=PlanOut,
    tags=["plans"],
)
def plan_update(
    id: int,
    d: PlanIn,
    db: Session = Depends(get_db),
    u=Depends(roles("admin")),
):
    record = db.get(Plan, id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Plan not found",
        )

    for key, value in d.model_dump().items():
        setattr(record, key, value)

    try:
        db.commit()
        db.refresh(record)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Plan update conflicts with existing data",
        )

    # Invalidate only after the database update succeeds.
    invalidate_plan_cache()

    return record


@app.delete(
    "/api/v1/plans/{id}",
    status_code=204,
    tags=["plans"],
)
def plan_delete(
    id: int,
    db: Session = Depends(get_db),
    u=Depends(roles("admin")),
):
    record = db.get(Plan, id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Plan not found",
        )

    record.is_active = False

    try:
        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to deactivate plan",
        )

    # Invalidate cached list and detail responses.
    invalidate_plan_cache()


# ============================================================
# CIRCLES
# ============================================================

@app.get(
    "/api/v1/circles",
    response_model=CircleListOut,
    tags=["circles"],
)
def circles(
    q: str | None = None,
    page_num: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    filters = []

    if q and q.strip():
        search = f"%{q.strip()}%"

        filters.append(
            or_(
                Circle.name.ilike(search),
                Circle.state.ilike(search),
            )
        )

    return page(
        db,
        Circle,
        page_num,
        size,
        filters,
    )


@app.get(
    "/api/v1/circles/{id}",
    response_model=CircleOut,
    tags=["circles"],
)
def circle(
    id: int,
    db: Session = Depends(get_db),
):
    record = db.get(Circle, id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Circle not found",
        )

    return record


@app.post(
    "/api/v1/circles",
    response_model=CircleOut,
    status_code=201,
    tags=["circles"],
)
def circle_create(
    d: CircleIn,
    db: Session = Depends(get_db),
    u=Depends(roles("admin")),
):
    return save(
        db,
        Circle(**d.model_dump()),
    )


@app.put(
    "/api/v1/circles/{id}",
    response_model=CircleOut,
    tags=["circles"],
)
def circle_update(
    id: int,
    d: CircleIn,
    db: Session = Depends(get_db),
    u=Depends(roles("admin")),
):
    record = db.get(Circle, id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Circle not found",
        )

    for key, value in d.model_dump().items():
        setattr(record, key, value)

    try:
        db.commit()
        db.refresh(record)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Circle update conflicts with existing data",
        )

    return record


@app.delete(
    "/api/v1/circles/{id}",
    status_code=204,
    tags=["circles"],
)
def circle_delete(
    id: int,
    db: Session = Depends(get_db),
    u=Depends(roles("admin")),
):
    record = db.get(Circle, id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Circle not found",
        )

    existing_subscriber = (
        db.query(Subscriber)
        .filter_by(circle_id=id)
        .first()
    )

    if existing_subscriber:
        raise HTTPException(
            status_code=409,
            detail="Circle has subscribers",
        )

    db.delete(record)

    try:
        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to delete circle",
        )


# ============================================================
# SUBSCRIBERS
# Admin/staff can manage subscriber records.
# ============================================================

@app.get(
    "/api/v1/subscribers",
    response_model=SubscriberListOut,
    tags=["subscribers"],
)
def subscribers(
    q: str | None = None,
    status: Literal[
        "active",
        "suspended",
        "ported_out",
        "closed",
    ] | None = None,
    circle_id: int | None = Query(
        default=None,
        gt=0,
    ),
    page_num: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    u=Depends(roles("admin", "staff")),
):
    filters = []

    if q and q.strip():
        search = f"%{q.strip()}%"

        filters.append(
            or_(
                Subscriber.phone.ilike(search),
                Subscriber.full_name.ilike(search),
            )
        )

    if status is not None:
        filters.append(
            Subscriber.status == status
        )

    if circle_id is not None:
        filters.append(
            Subscriber.circle_id == circle_id
        )

    return page(
        db,
        Subscriber,
        page_num,
        size,
        filters,
    )


@app.get(
    "/api/v1/subscribers/{id}",
    response_model=SubscriberOut,
    tags=["subscribers"],
)
def subscriber(
    id: int,
    db: Session = Depends(get_db),
    u=Depends(roles("admin", "staff")),
):
    record = db.get(Subscriber, id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Subscriber not found",
        )

    return record


@app.post(
    "/api/v1/subscribers",
    response_model=SubscriberOut,
    status_code=201,
    tags=["subscribers"],
)
def subscriber_create(
    d: SubscriberIn,
    db: Session = Depends(get_db),
    u=Depends(roles("admin", "staff")),
):
    return add_subscriber(db, d, u)


@app.put(
    "/api/v1/subscribers/{id}",
    response_model=SubscriberOut,
    tags=["subscribers"],
)
def subscriber_update(
    id: int,
    d: SubscriberIn,
    db: Session = Depends(get_db),
    u=Depends(roles("admin", "staff")),
):
    record = db.get(Subscriber, id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Subscriber not found",
        )

    if not db.get(Circle, d.circle_id):
        raise HTTPException(
            status_code=404,
            detail="Circle not found",
        )

    if d.current_plan_id is not None:
        selected_plan = db.get(
            Plan,
            d.current_plan_id,
        )

        if not selected_plan:
            raise HTTPException(
                status_code=404,
                detail="Plan not found",
            )

        if not selected_plan.is_active:
            raise HTTPException(
                status_code=409,
                detail="Plan is inactive",
            )

    update_data = d.model_dump(
        exclude={"user_id"}
    )

    for key, value in update_data.items():
        setattr(record, key, value)

    try:
        db.commit()
        db.refresh(record)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Subscriber update conflicts with existing data",
        )

    return record


@app.delete(
    "/api/v1/subscribers/{id}",
    status_code=204,
    tags=["subscribers"],
)
def subscriber_close(
    id: int,
    db: Session = Depends(get_db),
    u=Depends(roles("admin")),
):
    record = db.get(Subscriber, id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Subscriber not found",
        )

    record.status = "closed"

    try:
        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to close subscriber",
        )


# ============================================================
# RECHARGES
# ============================================================

@app.get(
    "/api/v1/recharges",
    response_model=RechargeListOut,
    tags=["recharges"],
)
def recharges(
    subscriber_id: int | None = Query(
        default=None,
        gt=0,
    ),
    page_num: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    u=Depends(roles("admin", "staff")),
):
    filters = []

    if subscriber_id is not None:
        filters.append(
            Recharge.subscriber_id == subscriber_id
        )

    return page(
        db,
        Recharge,
        page_num,
        size,
        filters,
    )


@app.post(
    "/api/v1/recharges",
    response_model=RechargeOut,
    status_code=201,
    tags=["recharges"],
)
def recharge_create(
    d: RechargeIn,
    db: Session = Depends(get_db),
    u=Depends(roles("admin", "staff", "user")),
):
    return add_recharge(db, d, u)


# ============================================================
# COMPLAINTS
# ============================================================

@app.get(
    "/api/v1/complaints",
    response_model=ComplaintListOut,
    tags=["complaints"],
)
def complaints(
    status: Literal[
        "open",
        "in_progress",
        "resolved",
        "rejected",
    ] | None = None,
    subscriber_id: int | None = Query(
        default=None,
        gt=0,
    ),
    page_num: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    u=Depends(roles("admin", "staff")),
):
    filters = []

    if status is not None:
        filters.append(
            Complaint.status == status
        )

    if subscriber_id is not None:
        filters.append(
            Complaint.subscriber_id == subscriber_id
        )

    return page(
        db,
        Complaint,
        page_num,
        size,
        filters,
    )


@app.post(
    "/api/v1/complaints",
    response_model=ComplaintOut,
    status_code=201,
    tags=["complaints"],
)
def complaint_create(
    d: ComplaintIn,
    db: Session = Depends(get_db),
    u=Depends(roles("admin", "staff", "user")),
):
    return add_complaint(db, d, u)


@app.patch(
    "/api/v1/complaints/{id}/status",
    response_model=ComplaintOut,
    tags=["complaints"],
)
def complaint_status(
    id: int,
    status: Literal[
        "open",
        "in_progress",
        "resolved",
        "rejected",
    ],
    db: Session = Depends(get_db),
    u=Depends(roles("admin", "staff")),
):
    record = db.get(Complaint, id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Complaint not found",
        )

    record.status = status

    try:
        db.commit()
        db.refresh(record)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to update complaint status",
        )

    return record


# ============================================================
# USAGE
# ============================================================

@app.get(
    "/api/v1/usage",
    response_model=UsageListOut,
    tags=["usage"],
)
def usage(
    subscriber_id: int | None = Query(
        default=None,
        gt=0,
    ),
    page_num: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    u=Depends(roles("admin", "staff")),
):
    filters = []

    if subscriber_id is not None:
        filters.append(
            UsageRecord.subscriber_id == subscriber_id
        )

    return page(
        db,
        UsageRecord,
        page_num,
        size,
        filters,
    )


@app.post(
    "/api/v1/usage",
    response_model=UsageOut,
    status_code=201,
    tags=["usage"],
)
def usage_create(
    d: UsageIn,
    db: Session = Depends(get_db),
    u=Depends(roles("admin", "staff")),
):
    return add_usage(db, d)


# ============================================================
# ANALYTICS
# ============================================================

@app.get(
    "/api/v1/analytics/summary",
    tags=["analytics"],
)
def analytics(
    db: Session = Depends(get_db),
    u=Depends(roles("admin", "staff")),
):
    return {
        "subscribers": (
            db.query(Subscriber).count()
        ),
        "active_subscribers": (
            db.query(Subscriber)
            .filter_by(status="active")
            .count()
        ),
        "active_plans": (
            db.query(Plan)
            .filter_by(is_active=True)
            .count()
        ),
        "recharges": (
            db.query(Recharge).count()
        ),
        "open_complaints": (
            db.query(Complaint)
            .filter_by(status="open")
            .count()
        ),
    }
