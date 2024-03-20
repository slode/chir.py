import jwt
import json
from typing import Any, Optional

from datetime import datetime, timedelta


# openssl rand -hex 32
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 3000000


class TokenValidationException(Exception): ...


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except (jwt.DecodeError, jwt.exceptions.ExpiredSignatureError) as e:
        raise TokenValidationException() from e
    return payload


def create_token(payload: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    iat = datetime.utcnow()
    expire = iat + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = payload | {
        "exp": expire,
        "iat": iat,
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
