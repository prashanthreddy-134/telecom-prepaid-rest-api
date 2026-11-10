
import re
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


# ============================================================
# SHARED SCHEMAS
# ============================================================

class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PaginationOut(BaseModel):
    total: int
    page: int
    size: int


# ============================================================
# AUTHENTICATION
# ============================================================

class Register(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()

        pattern = (
            r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
            r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
        )

        if not re.fullmatch(pattern, value):
            raise ValueError("Invalid email address")

        return value


class UserOut(ORM):
    id: int
    email: str
    role: str
    is_active: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ============================================================
# CIRCLES
# ============================================================

class CircleIn(BaseModel):
    code: str = Field(min_length=2, max_length=12)
    name: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)

    @field_validator("code", "name", "state")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Field cannot be empty")

        return value


class CircleOut(ORM):
    id: int
    code: str
    name: str
    state: str


class CircleListOut(PaginationOut):
    items: list[CircleOut]


# ============================================================
# PLANS
# ============================================================

class PlanIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    price_paise: int = Field(gt=0)
    validity_days: int = Field(gt=0, le=3650)
    data_mb: int = Field(ge=0)
    voice_minutes: int = Field(default=0, ge=0)
    sms_count: int = Field(default=0, ge=0)
    description: str = Field(default="", max_length=2000)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Plan name cannot be empty")

        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return value.strip()


class PlanOut(ORM):
    id: int
    name: str
    price_paise: int
    validity_days: int
    data_mb: int
    voice_minutes: int
    sms_count: int
    description: str
    is_active: bool


class PlanListOut(PaginationOut):
    items: list[PlanOut]


# ============================================================
# SUBSCRIBERS
# ============================================================

class SubscriberIn(BaseModel):
    phone: str
    full_name: str = Field(min_length=2, max_length=120)
    circle_id: int = Field(gt=0)

    # Admin/staff can assign an account owner.
    # If omitted, the service assigns the creator.
    user_id: int | None = Field(default=None, gt=0)

    status: Literal[
        "active",
        "suspended",
        "ported_out",
        "closed",
    ] = "active"

    current_plan_id: int | None = Field(default=None, gt=0)

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, value: str) -> str:
        value = value.strip()

        if not re.fullmatch(r"[6-9][0-9]{9}", value):
            raise ValueError(
                "Expected 10-digit Indian mobile number"
            )

        return value

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Full name cannot be empty")

        return value


class SubscriberOut(ORM):
    id: int
    phone: str
    full_name: str
    circle_id: int
    status: str
    current_plan_id: int | None


class SubscriberListOut(PaginationOut):
    items: list[SubscriberOut]


# ============================================================
# RECHARGES
# ============================================================

class RechargeIn(BaseModel):
    subscriber_id: int = Field(gt=0)
    plan_id: int = Field(gt=0)
    reference: str = Field(min_length=6, max_length=80)

    @field_validator("reference")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Reference cannot be empty")

        return value


class RechargeOut(ORM):
    id: int
    subscriber_id: int
    plan_id: int
    amount_paise: int
    reference: str
    status: str


class RechargeListOut(PaginationOut):
    items: list[RechargeOut]


# ============================================================
# COMPLAINTS
# ============================================================

class ComplaintIn(BaseModel):
    subscriber_id: int = Field(gt=0)
    category: str = Field(min_length=2, max_length=60)
    description: str = Field(min_length=5, max_length=2000)
    source: Literal["app", "call_centre", "web"]
    external_ref: str = Field(min_length=3, max_length=80)

    @field_validator(
        "category",
        "description",
        "external_ref",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Field cannot be empty")

        return value


class ComplaintOut(ORM):
    id: int
    subscriber_id: int
    category: str
    description: str
    source: str
    external_ref: str
    status: str


class ComplaintListOut(PaginationOut):
    items: list[ComplaintOut]


# ============================================================
# USAGE
# ============================================================

class UsageIn(BaseModel):
    subscriber_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    unit: Literal["MB", "GB"]


class UsageOut(ORM):
    id: int
    subscriber_id: int
    usage_mb: float
    source_unit: str


class UsageListOut(PaginationOut):
    items: list[UsageOut]
