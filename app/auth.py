import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import ALGORITHM, COOKIE_NAME, SECRET_KEY
from app.database import db_session, row_to_dict

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict[str, Any], expires_hours: int = 72) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_user_by_email(email: str) -> dict | None:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM collaborators WHERE email = ? AND revoked = 0",
            (email,),
        ).fetchone()
        return row_to_dict(row)


def get_user_by_id(user_id: int) -> dict | None:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM collaborators WHERE id = ? AND revoked = 0",
            (user_id,),
        ).fetchone()
        return row_to_dict(row)


def authenticate_user(identifier: str, password: str) -> dict | None:
    """按邮箱或登录名(username)校验身份，二者解耦、皆可登录。"""
    identifier = (identifier or "").strip()
    with db_session() as conn:
        try:
            row = conn.execute(
                "SELECT * FROM collaborators WHERE (email = ? OR username = ?) AND revoked = 0",
                (identifier, identifier),
            ).fetchone()
        except sqlite3.OperationalError:
            # 旧库尚未迁移 username 列：降级为仅按邮箱校验，避免 500 死锁
            row = conn.execute(
                "SELECT * FROM collaborators WHERE email = ? AND revoked = 0",
                (identifier,),
            ).fetchone()
        user = row_to_dict(row)
    if not user or not verify_password(password, user["password_hash"]):
        return None
    if user.get("expires_at"):
        expires = datetime.fromisoformat(user["expires_at"])
        if expires < datetime.now():
            return None
    return user


def get_current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效令牌")
    user = get_user_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已撤销")
    return user


def get_optional_user(request: Request) -> dict | None:
    try:
        return get_current_user(request)
    except HTTPException:
        return None


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def user_can_access_project(user: dict, project_id: int) -> bool:
    if user["role"] == "admin":
        return True
    allowed = json.loads(user.get("project_ids") or "[]")
    return project_id in allowed


def require_project_access(project_id: int, user: dict = Depends(get_current_user)) -> dict:
    if not user_can_access_project(user, project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问此项目")
    return user


def log_audit(actor_id: int, action: str, target_type: str, target_id: int, detail: str = "") -> None:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (actor_id, action, target_type, target_id, detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            (actor_id, action, target_type, target_id, detail),
        )


def get_accessible_project_ids(user: dict) -> list[int] | None:
    """Return None for admin (all), else list of ids."""
    if user["role"] == "admin":
        return None
    return json.loads(user.get("project_ids") or "[]")
