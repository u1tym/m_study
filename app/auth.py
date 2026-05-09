from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from psycopg import Connection

from app.config import Settings, get_settings
from app.db import get_db


def _decode_jwt(token: str, settings: Settings) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
        ) from exc
    return payload


def get_current_aid(
    request: Request,
    db: Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> int:
    token = request.cookies.get(settings.jwt_cookie_name)

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication cookie is missing.",
        )

    payload = _decode_jwt(token, settings)
    username = payload.get("username")
    if not isinstance(username, str) or not username.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not include valid username.",
        )

    cur = db.cursor()
    cur.execute("select id from accounts where username = %s", (username.strip(),))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found.",
        )
    aid = int(row["id"])
    request.state.aid = aid
    return aid
