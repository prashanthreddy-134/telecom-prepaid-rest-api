
from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core import get_db, settings
from app.models import User


# bcrypt_sha256 avoids bcrypt's 72-byte password limitation.
# Legacy bcrypt hashes remain supported for existing accounts.
pwd = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)

oauth = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token"
)

ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60


def hash_pw(password: str) -> str:
    return pwd.hash(password)


def verify_pw(password: str, password_hash: str) -> bool:
    try:
        return pwd.verify(password, password_hash)
    except (ValueError, TypeError):
        return False


def make_token(user: User) -> str:
    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    )

    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def current_user(
    token: str = Depends(oauth),
    db: Session = Depends(get_db),
):
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
    token,
    settings.secret_key,
    algorithms=[ALGORITHM],
    options={
        "require_exp": True,
        "require_sub": True,
    },
)

        subject = payload.get("sub")

        if not subject:
            raise credentials_error

        user_id = int(subject)

    except (JWTError, ValueError, TypeError, KeyError):
        raise credentials_error

    user = db.get(User, user_id)

    if user is None or not user.is_active:
        raise credentials_error

    return user


def roles(*allowed_roles: str):
    def check_role(
        user: User = Depends(current_user),
    ):
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return user

    return check_role
