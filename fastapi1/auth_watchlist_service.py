import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Iterable

from fastapi import HTTPException
from sqlalchemy import text

from settings import DATABASE_URL
from stock_service import engine, serialize_row


TOKEN_TTL_SECONDS = 60 * 60 * 24 * 14
PASSWORD_ITERATIONS = 260000
TOKEN_SECRET = os.getenv("APP_SECRET", f"stock-app::{DATABASE_URL}")


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _unauthorized(detail: str = "Unauthorized"):
    raise HTTPException(status_code=401, detail=detail)


def _bad_request(detail: str):
    raise HTTPException(status_code=400, detail=detail)


def _not_found(detail: str):
    raise HTTPException(status_code=404, detail=detail)


def _normalize_username(username: str) -> str:
    value = (username or "").strip()
    if not value:
        _bad_request("Username is required")
    return value


def _normalize_password(password: str) -> str:
    value = (password or "").strip()
    if not value:
        _bad_request("Password is required")
    return value


def _normalize_group_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        _bad_request("Group name is required")
    return value


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iteration_text, salt, expected_hex = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iteration_text),
        )
        return hmac.compare_digest(digest.hex(), expected_hex)
    except Exception:
        return False


def create_token(user: dict) -> str:
    payload = {
        "user_id": int(user["id"]),
        "username": user["username"],
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    payload_segment = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        TOKEN_SECRET.encode("utf-8"),
        payload_segment.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{payload_segment}.{_b64url_encode(signature)}"


def parse_token(token: str) -> dict:
    if not token or "." not in token:
        _unauthorized("Invalid token")

    payload_segment, signature_segment = token.split(".", 1)
    expected_signature = hmac.new(
        TOKEN_SECRET.encode("utf-8"),
        payload_segment.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(_b64url_encode(expected_signature), signature_segment):
        _unauthorized("Invalid token")

    try:
        payload = json.loads(_b64url_decode(payload_segment).decode("utf-8"))
    except Exception:
        _unauthorized("Invalid token")

    if int(payload.get("exp") or 0) < int(time.time()):
        _unauthorized("Token expired")

    return payload


def ensure_tables(db_engine=engine):
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_users_username (username)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS watchlist_groups (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_watchlist_groups_user_name (user_id, name),
            KEY idx_watchlist_groups_user_id (user_id)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS watchlist_group_stocks (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            group_id BIGINT NOT NULL,
            ts_code VARCHAR(32) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_watchlist_group_stock (group_id, ts_code),
            KEY idx_watchlist_group_stocks_group_id (group_id),
            KEY idx_watchlist_group_stocks_ts_code (ts_code)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
    ]
    with db_engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def _fetch_user_by_username(conn, username: str):
    row = conn.execute(
        text(
            """
            SELECT id, username, password_hash
            FROM users
            WHERE username = :username
            LIMIT 1
            """
        ),
        {"username": username},
    ).mappings().first()
    return serialize_row(row)


def _fetch_user_by_id(conn, user_id: int):
    row = conn.execute(
        text(
            """
            SELECT id, username
            FROM users
            WHERE id = :user_id
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    ).mappings().first()
    return serialize_row(row)


def _auth_response(user: dict) -> dict:
    public_user = {"id": int(user["id"]), "username": user["username"]}
    return {
        "token": create_token(public_user),
        "user": public_user,
    }


def register_user(username: str, password: str, db_engine=engine) -> dict:
    normalized_username = _normalize_username(username)
    normalized_password = _normalize_password(password)

    with db_engine.begin() as conn:
        existing = _fetch_user_by_username(conn, normalized_username)
        if existing:
            raise HTTPException(status_code=409, detail="Username already exists")

        conn.execute(
            text(
                """
                INSERT INTO users (username, password_hash)
                VALUES (:username, :password_hash)
                """
            ),
            {
                "username": normalized_username,
                "password_hash": hash_password(normalized_password),
            },
        )
        created_user = _fetch_user_by_username(conn, normalized_username)

    return _auth_response(created_user)


def login_user(username: str, password: str, db_engine=engine) -> dict:
    normalized_username = _normalize_username(username)
    normalized_password = _normalize_password(password)

    with db_engine.begin() as conn:
        user = _fetch_user_by_username(conn, normalized_username)

    if not user or not verify_password(normalized_password, user["password_hash"]):
        _unauthorized("Invalid username or password")

    return _auth_response(user)


def get_current_user_from_authorization(authorization: str | None, db_engine=engine) -> dict:
    if not authorization:
        _unauthorized("Missing Authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        _unauthorized("Invalid Authorization header")

    payload = parse_token(token.strip())

    with db_engine.begin() as conn:
        user = _fetch_user_by_id(conn, int(payload["user_id"]))

    if not user:
        _unauthorized("User not found")

    return user


def list_groups(user_id: int, db_engine=engine) -> list[dict]:
    with db_engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    g.id,
                    g.name,
                    COUNT(wgs.id) AS stock_count
                FROM watchlist_groups g
                LEFT JOIN watchlist_group_stocks wgs ON wgs.group_id = g.id
                WHERE g.user_id = :user_id
                GROUP BY g.id, g.name
                ORDER BY g.created_at ASC, g.id ASC
                """
            ),
            {"user_id": user_id},
        ).mappings().all()
    return [serialize_row(row) for row in rows]


def create_group(user_id: int, name: str, db_engine=engine) -> dict:
    normalized_name = _normalize_group_name(name)
    try:
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO watchlist_groups (user_id, name)
                    VALUES (:user_id, :name)
                    """
                ),
                {"user_id": user_id, "name": normalized_name},
            )
    except Exception as exc:
        if "uq_watchlist_groups_user_name" in str(exc) or "Duplicate entry" in str(exc):
            raise HTTPException(status_code=409, detail="Group name already exists") from exc
        raise

    groups = list_groups(user_id, db_engine)
    return next(group for group in groups if group["name"] == normalized_name)


def _fetch_group_for_user(conn, user_id: int, group_id: int):
    row = conn.execute(
        text(
            """
            SELECT id, user_id, name
            FROM watchlist_groups
            WHERE id = :group_id AND user_id = :user_id
            LIMIT 1
            """
        ),
        {"group_id": group_id, "user_id": user_id},
    ).mappings().first()
    return serialize_row(row)


def rename_group(user_id: int, group_id: int, name: str, db_engine=engine) -> dict:
    normalized_name = _normalize_group_name(name)
    try:
        with db_engine.begin() as conn:
            group = _fetch_group_for_user(conn, user_id, group_id)
            if not group:
                _not_found("Group not found")
            conn.execute(
                text(
                    """
                    UPDATE watchlist_groups
                    SET name = :name
                    WHERE id = :group_id AND user_id = :user_id
                    """
                ),
                {"name": normalized_name, "group_id": group_id, "user_id": user_id},
            )
    except Exception as exc:
        if "uq_watchlist_groups_user_name" in str(exc) or "Duplicate entry" in str(exc):
            raise HTTPException(status_code=409, detail="Group name already exists") from exc
        raise

    groups = list_groups(user_id, db_engine)
    return next(group for group in groups if int(group["id"]) == int(group_id))


def delete_group(user_id: int, group_id: int, db_engine=engine) -> dict:
    with db_engine.begin() as conn:
        group = _fetch_group_for_user(conn, user_id, group_id)
        if not group:
            _not_found("Group not found")
        conn.execute(
            text("DELETE FROM watchlist_group_stocks WHERE group_id = :group_id"),
            {"group_id": group_id},
        )
        conn.execute(
            text("DELETE FROM watchlist_groups WHERE id = :group_id AND user_id = :user_id"),
            {"group_id": group_id, "user_id": user_id},
        )
    return {"success": True}


def _normalize_group_ids(group_ids: Iterable[int]) -> list[int]:
    normalized = []
    for group_id in group_ids or []:
        try:
            normalized_id = int(group_id)
        except (TypeError, ValueError):
            _bad_request("group_ids must contain integers")
        if normalized_id not in normalized:
            normalized.append(normalized_id)
    return normalized


def _validate_group_ids_for_user(conn, user_id: int, group_ids: list[int]) -> list[dict]:
    if not group_ids:
        _bad_request("group_ids is required")

    placeholders = ", ".join([f":group_id_{index}" for index in range(len(group_ids))])
    params = {"user_id": user_id}
    params.update({f"group_id_{index}": group_id for index, group_id in enumerate(group_ids)})
    rows = conn.execute(
        text(
            f"""
            SELECT id, name
            FROM watchlist_groups
            WHERE user_id = :user_id AND id IN ({placeholders})
            ORDER BY id ASC
            """
        ),
        params,
    ).mappings().all()
    groups = [serialize_row(row) for row in rows]
    if len(groups) != len(group_ids):
        _bad_request("One or more group_ids are invalid")
    return groups


def _ensure_stock_exists(conn, ts_code: str) -> dict:
    row = conn.execute(
        text(
            """
            SELECT ts_code, name, industry, sw_l2_name
            FROM stocks
            WHERE ts_code = :ts_code
            LIMIT 1
            """
        ),
        {"ts_code": ts_code},
    ).mappings().first()
    stock = serialize_row(row)
    if not stock:
        _not_found("Stock not found")
    return stock


def get_stock_watchlist_state(user_id: int, ts_code: str, db_engine=engine) -> dict:
    with db_engine.begin() as conn:
        _ensure_stock_exists(conn, ts_code)
        rows = conn.execute(
            text(
                """
                SELECT g.id, g.name
                FROM watchlist_groups g
                INNER JOIN watchlist_group_stocks wgs ON wgs.group_id = g.id
                WHERE g.user_id = :user_id AND wgs.ts_code = :ts_code
                ORDER BY g.name ASC, g.id ASC
                """
            ),
            {"user_id": user_id, "ts_code": ts_code},
        ).mappings().all()
    groups = [serialize_row(row) for row in rows]
    return {
        "ts_code": ts_code,
        "in_watchlist": bool(groups),
        "groups": groups,
    }


def add_stock_to_groups(user_id: int, ts_code: str, group_ids: Iterable[int], db_engine=engine) -> dict:
    normalized_group_ids = _normalize_group_ids(group_ids)
    with db_engine.begin() as conn:
        _ensure_stock_exists(conn, ts_code)
        _validate_group_ids_for_user(conn, user_id, normalized_group_ids)
        for group_id in normalized_group_ids:
            conn.execute(
                text(
                    """
                    INSERT INTO watchlist_group_stocks (group_id, ts_code)
                    VALUES (:group_id, :ts_code)
                    ON DUPLICATE KEY UPDATE ts_code = VALUES(ts_code)
                    """
                ),
                {"group_id": group_id, "ts_code": ts_code},
            )
    return get_stock_watchlist_state(user_id, ts_code, db_engine)


def replace_stock_groups(user_id: int, ts_code: str, group_ids: Iterable[int], db_engine=engine) -> dict:
    normalized_group_ids = _normalize_group_ids(group_ids)
    with db_engine.begin() as conn:
        _ensure_stock_exists(conn, ts_code)
        if normalized_group_ids:
            _validate_group_ids_for_user(conn, user_id, normalized_group_ids)

        conn.execute(
            text(
                """
                DELETE wgs
                FROM watchlist_group_stocks wgs
                INNER JOIN watchlist_groups g ON g.id = wgs.group_id
                WHERE g.user_id = :user_id AND wgs.ts_code = :ts_code
                """
            ),
            {"user_id": user_id, "ts_code": ts_code},
        )

        for group_id in normalized_group_ids:
            conn.execute(
                text(
                    """
                    INSERT INTO watchlist_group_stocks (group_id, ts_code)
                    VALUES (:group_id, :ts_code)
                    """
                ),
                {"group_id": group_id, "ts_code": ts_code},
            )
    return get_stock_watchlist_state(user_id, ts_code, db_engine)


def remove_stock_from_watchlist(user_id: int, ts_code: str, db_engine=engine) -> dict:
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                DELETE wgs
                FROM watchlist_group_stocks wgs
                INNER JOIN watchlist_groups g ON g.id = wgs.group_id
                WHERE g.user_id = :user_id AND wgs.ts_code = :ts_code
                """
            ),
            {"user_id": user_id, "ts_code": ts_code},
        )
    return {
        "ts_code": ts_code,
        "in_watchlist": False,
        "groups": [],
    }


def list_watchlist_stocks(user_id: int, db_engine=engine) -> list[dict]:
    with db_engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    s.ts_code,
                    s.name,
                    s.industry,
                    s.sw_l2_name,
                    q.close AS price,
                    q.`change` AS price_change,
                    q.pct_chg AS change_percent,
                    CASE
                        WHEN p.float_share IS NULL OR p.float_share = 0 THEN NULL
                        ELSE q.vol / p.float_share
                    END AS turnover_rate,
                    q.amount,
                    q.trade_date,
                    g.id AS group_id,
                    g.name AS group_name
                FROM watchlist_group_stocks wgs
                INNER JOIN watchlist_groups g ON g.id = wgs.group_id
                INNER JOIN stocks s ON s.ts_code = wgs.ts_code COLLATE utf8mb4_unicode_ci
                LEFT JOIN daily_quotes q
                    ON q.ts_code = s.ts_code COLLATE utf8mb4_unicode_ci
                    AND q.trade_date = (
                        SELECT MAX(dq.trade_date)
                        FROM daily_quotes dq
                        WHERE dq.ts_code = s.ts_code COLLATE utf8mb4_unicode_ci
                    )
                LEFT JOIN stock_premarket p
                    ON p.ts_code = s.ts_code COLLATE utf8mb4_unicode_ci
                    AND p.trade_date = q.trade_date
                WHERE g.user_id = :user_id
                ORDER BY s.ts_code ASC, g.name ASC, g.id ASC
                """
            ),
            {"user_id": user_id},
        ).mappings().all()

    grouped: dict[str, dict] = {}
    for row in rows:
        item = serialize_row(row)
        stock = grouped.setdefault(
            item["ts_code"],
            {
                "ts_code": item["ts_code"],
                "name": item["name"],
                "industry": item.get("industry"),
                "sw_l2_name": item.get("sw_l2_name"),
                "price": item.get("price"),
                "change": item.get("price_change"),
                "change_percent": item.get("change_percent"),
                "turnover_rate": item.get("turnover_rate"),
                "amount": item.get("amount"),
                "trade_date": item.get("trade_date"),
                "groups": [],
            },
        )
        stock["groups"].append(
            {
                "id": item["group_id"],
                "name": item["group_name"],
            }
        )

    return list(grouped.values())
