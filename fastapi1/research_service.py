import json
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import text

from settings import DATABASE_URL
from stock_service import engine, resolve_ts_code, serialize_row


RESEARCH_STATUSES = ("focus", "portfolio", "buy_watch", "watchlist", "risk", "archive")
RESEARCH_PRIORITIES = ("high", "medium", "low")
RESEARCH_LOG_TYPES = ("新增研究", "上调评级", "下调评级", "风险提醒", "复盘")
STALE_RESEARCH_DAYS = 14


def _bad_request(detail: str):
    raise HTTPException(status_code=400, detail=detail)


def _not_found(detail: str):
    raise HTTPException(status_code=404, detail=detail)


def ensure_research_tables(db_engine=engine):
    statements = [
        """
        CREATE TABLE IF NOT EXISTS research_stocks (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            ts_code VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'watchlist',
            priority VARCHAR(16) NOT NULL DEFAULT 'medium',
            tags TEXT NOT NULL,
            thesis TEXT NOT NULL,
            trigger_condition TEXT NOT NULL,
            risk TEXT NOT NULL,
            exit_condition TEXT NOT NULL,
            industry_trend INT NOT NULL DEFAULT 3,
            competitive_advantage INT NOT NULL DEFAULT 3,
            financial_quality INT NOT NULL DEFAULT 3,
            management INT NOT NULL DEFAULT 3,
            valuation INT NOT NULL DEFAULT 3,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_research_stocks_user_stock (user_id, ts_code),
            KEY idx_research_stocks_user_id (user_id),
            KEY idx_research_stocks_status (status),
            KEY idx_research_stocks_priority (priority)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
        """
        CREATE TABLE IF NOT EXISTS research_logs (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            ts_code VARCHAR(32) NOT NULL,
            log_date DATE NOT NULL,
            log_type VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            KEY idx_research_logs_user_stock (user_id, ts_code),
            KEY idx_research_logs_user_date (user_id, log_date)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """,
    ]
    with db_engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def calculate_total_score(score: dict) -> int:
    return sum(
        int(score[key])
        for key in (
            "industry_trend",
            "competitive_advantage",
            "financial_quality",
            "management",
            "valuation",
        )
    )


def build_trigger_mock_state(item: dict) -> dict | None:
    trigger_condition = (item.get("trigger_condition") or "").strip()
    if not trigger_condition:
        return None

    change_percent = item.get("change_percent")
    change_number = float(change_percent) if change_percent is not None else 0.0
    tag_count = len(item.get("tags") or [])
    checksum = sum(ord(char) for char in f"{item.get('ts_code', '')}{trigger_condition}")
    triggered = abs(change_number) >= 3 or (checksum + tag_count) % 3 == 0

    if not triggered:
        return None

    return {
        "ts_code": item["ts_code"],
        "name": item["name"],
        "price": item.get("price"),
        "change_percent": item.get("change_percent"),
        "trigger_condition": trigger_condition,
        "isMock": True,
        "mockReason": "Mock trigger fired from deterministic demo rule.",
    }


def _normalize_status(status: str | None) -> str:
    value = (status or "watchlist").strip().lower()
    if value not in RESEARCH_STATUSES:
        _bad_request(f"status must be one of: {', '.join(RESEARCH_STATUSES)}")
    return value


def _normalize_priority(priority: str | None) -> str:
    value = (priority or "medium").strip().lower()
    if value not in RESEARCH_PRIORITIES:
        _bad_request(f"priority must be one of: {', '.join(RESEARCH_PRIORITIES)}")
    return value


def _normalize_text(value: str | None, field_name: str) -> str:
    return (value or "").strip()


def _normalize_tags(tags) -> list[str]:
    if tags is None:
        return []
    if not isinstance(tags, list):
        _bad_request("tags must be an array of strings")

    normalized = []
    seen = set()
    for tag in tags:
        if not isinstance(tag, str):
            _bad_request("tags must contain only strings")
        value = tag.strip()
        key = value.lower()
        if not value or key in seen:
            continue
        normalized.append(value)
        seen.add(key)
    return normalized


def _normalize_score_value(value, field_name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        _bad_request(f"{field_name} must be an integer")
    if normalized < 1 or normalized > 5:
        _bad_request(f"{field_name} must be between 1 and 5")
    return normalized


def normalize_score_payload(score: dict | None) -> dict:
    source = score or {}
    normalized = {
        "industry_trend": _normalize_score_value(source.get("industry_trend", 3), "industry_trend"),
        "competitive_advantage": _normalize_score_value(source.get("competitive_advantage", 3), "competitive_advantage"),
        "financial_quality": _normalize_score_value(source.get("financial_quality", 3), "financial_quality"),
        "management": _normalize_score_value(source.get("management", 3), "management"),
        "valuation": _normalize_score_value(source.get("valuation", 3), "valuation"),
    }
    normalized["total_score"] = calculate_total_score(normalized)
    return normalized


def _normalize_log_type(log_type: str) -> str:
    value = (log_type or "").strip()
    if value not in RESEARCH_LOG_TYPES:
        _bad_request(f"log type must be one of: {', '.join(RESEARCH_LOG_TYPES)}")
    return value


def _normalize_log_date(log_date: str | None) -> str:
    value = (log_date or "").strip()
    if not value:
        return datetime.now().date().isoformat()
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="date must be ISO formatted") from exc


def _parse_tags(raw_tags) -> list[str]:
    if not raw_tags:
        return []
    try:
        parsed = json.loads(raw_tags)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _serialize_research_row(row: dict) -> dict:
    item = serialize_row(row)
    score = {
        "industry_trend": int(item.get("industry_trend") or 3),
        "competitive_advantage": int(item.get("competitive_advantage") or 3),
        "financial_quality": int(item.get("financial_quality") or 3),
        "management": int(item.get("management") or 3),
        "valuation": int(item.get("valuation") or 3),
    }
    score["total_score"] = calculate_total_score(score)
    return {
        "ts_code": item["ts_code"],
        "ticker": item["ts_code"],
        "name": item.get("name") or item["ts_code"],
        "price": item.get("price"),
        "change_percent": item.get("change_percent"),
        "status": item["status"],
        "priority": item["priority"],
        "tags": _parse_tags(item.get("tags")),
        "thesis": item.get("thesis") or "",
        "trigger_condition": item.get("trigger_condition") or "",
        "risk": item.get("risk") or "",
        "exit_condition": item.get("exit_condition") or "",
        "updated_at": item.get("updated_at"),
        "created_at": item.get("created_at"),
        "score": score,
    }


def _fetch_stock_for_research(conn, ts_code: str) -> dict:
    normalized_code = resolve_ts_code(conn, ts_code)
    row = conn.execute(
        text(
            """
            SELECT ts_code, symbol, name
            FROM stocks
            WHERE ts_code = :ts_code
            LIMIT 1
            """
        ),
        {"ts_code": normalized_code},
    ).mappings().first()
    stock = serialize_row(row)
    if not stock:
        _not_found("Stock not found")
    return stock


def _fetch_research_row(conn, user_id: int, ts_code: str):
    normalized_code = resolve_ts_code(conn, ts_code)
    row = conn.execute(
        text(
            """
            SELECT
                rs.*,
                s.name,
                q.close AS price,
                q.pct_chg AS change_percent
            FROM research_stocks rs
            INNER JOIN stocks s ON s.ts_code = rs.ts_code COLLATE utf8mb4_unicode_ci
            LEFT JOIN daily_quotes q
                ON q.ts_code = rs.ts_code COLLATE utf8mb4_unicode_ci
                AND q.trade_date = (
                    SELECT MAX(dq.trade_date)
                    FROM daily_quotes dq
                    WHERE dq.ts_code = rs.ts_code COLLATE utf8mb4_unicode_ci
                )
            WHERE rs.user_id = :user_id AND rs.ts_code = :ts_code
            LIMIT 1
            """
        ),
        {"user_id": user_id, "ts_code": normalized_code},
    ).mappings().first()
    return row


def _fetch_logs(conn, user_id: int, ts_code: str) -> list[dict]:
    rows = conn.execute(
        text(
            """
            SELECT id, ts_code, log_date, log_type, content, created_at, updated_at
            FROM research_logs
            WHERE user_id = :user_id AND ts_code = :ts_code
            ORDER BY log_date DESC, id DESC
            """
        ),
        {"user_id": user_id, "ts_code": ts_code},
    ).mappings().all()
    items = []
    for row in rows:
        item = serialize_row(row)
        items.append(
            {
                "id": item["id"],
                "ts_code": item["ts_code"],
                "date": item["log_date"],
                "type": item["log_type"],
                "content": item["content"],
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            }
        )
    return items


def list_research_stocks(user_id: int, status: str | None = None, priority: str | None = None, tag: str | None = None, q: str | None = None, db_engine=engine) -> list[dict]:
    with db_engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    rs.*,
                    s.name,
                    q.close AS price,
                    q.pct_chg AS change_percent
                FROM research_stocks rs
                INNER JOIN stocks s ON s.ts_code = rs.ts_code COLLATE utf8mb4_unicode_ci
                LEFT JOIN daily_quotes q
                    ON q.ts_code = rs.ts_code COLLATE utf8mb4_unicode_ci
                    AND q.trade_date = (
                        SELECT MAX(dq.trade_date)
                        FROM daily_quotes dq
                        WHERE dq.ts_code = rs.ts_code COLLATE utf8mb4_unicode_ci
                    )
                WHERE rs.user_id = :user_id
                ORDER BY rs.updated_at DESC, rs.id DESC
                """
            ),
            {"user_id": user_id},
        ).mappings().all()

    items = [_serialize_research_row(row) for row in rows]

    if status:
        normalized_status = _normalize_status(status)
        items = [item for item in items if item["status"] == normalized_status]

    if priority:
        normalized_priority = _normalize_priority(priority)
        items = [item for item in items if item["priority"] == normalized_priority]

    if tag:
        tag_query = tag.strip().lower()
        items = [item for item in items if any(current.lower() == tag_query for current in item["tags"])]

    if q:
        query = q.strip().lower()
        if query:
            items = [
                item
                for item in items
                if query in item["name"].lower()
                or query in item["ts_code"].lower()
                or any(query in current.lower() for current in item["tags"])
            ]

    return items


def create_research_stock(user_id: int, payload: dict, db_engine=engine) -> dict:
    with db_engine.begin() as conn:
        stock = _fetch_stock_for_research(conn, payload.get("ts_code"))
        existing = conn.execute(
            text(
                """
                SELECT id
                FROM research_stocks
                WHERE user_id = :user_id AND ts_code = :ts_code
                LIMIT 1
                """
            ),
            {"user_id": user_id, "ts_code": stock["ts_code"]},
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Research stock already exists")

        score = normalize_score_payload(payload.get("score"))
        conn.execute(
            text(
                """
                INSERT INTO research_stocks (
                    user_id,
                    ts_code,
                    status,
                    priority,
                    tags,
                    thesis,
                    trigger_condition,
                    risk,
                    exit_condition,
                    industry_trend,
                    competitive_advantage,
                    financial_quality,
                    management,
                    valuation
                ) VALUES (
                    :user_id,
                    :ts_code,
                    :status,
                    :priority,
                    :tags,
                    :thesis,
                    :trigger_condition,
                    :risk,
                    :exit_condition,
                    :industry_trend,
                    :competitive_advantage,
                    :financial_quality,
                    :management,
                    :valuation
                )
                """
            ),
            {
                "user_id": user_id,
                "ts_code": stock["ts_code"],
                "status": _normalize_status(payload.get("status")),
                "priority": _normalize_priority(payload.get("priority")),
                "tags": json.dumps(_normalize_tags(payload.get("tags")), ensure_ascii=False),
                "thesis": _normalize_text(payload.get("thesis"), "thesis"),
                "trigger_condition": _normalize_text(payload.get("trigger_condition"), "trigger_condition"),
                "risk": _normalize_text(payload.get("risk"), "risk"),
                "exit_condition": _normalize_text(payload.get("exit_condition"), "exit_condition"),
                "industry_trend": score["industry_trend"],
                "competitive_advantage": score["competitive_advantage"],
                "financial_quality": score["financial_quality"],
                "management": score["management"],
                "valuation": score["valuation"],
            },
        )

    return get_research_stock_detail(user_id, stock["ts_code"], db_engine)


def get_research_stock_detail(user_id: int, ts_code: str, db_engine=engine) -> dict:
    with db_engine.begin() as conn:
        row = _fetch_research_row(conn, user_id, ts_code)
        if not row:
            _not_found("Research stock not found")
        item = _serialize_research_row(row)
        item["research_logs"] = _fetch_logs(conn, user_id, item["ts_code"])
    return item


def update_research_stock(user_id: int, ts_code: str, payload: dict, db_engine=engine) -> dict:
    with db_engine.begin() as conn:
        row = _fetch_research_row(conn, user_id, ts_code)
        if not row:
            _not_found("Research stock not found")

        score = normalize_score_payload(payload.get("score"))
        conn.execute(
            text(
                """
                UPDATE research_stocks
                SET
                    status = :status,
                    priority = :priority,
                    tags = :tags,
                    thesis = :thesis,
                    trigger_condition = :trigger_condition,
                    risk = :risk,
                    exit_condition = :exit_condition,
                    industry_trend = :industry_trend,
                    competitive_advantage = :competitive_advantage,
                    financial_quality = :financial_quality,
                    management = :management,
                    valuation = :valuation
                WHERE user_id = :user_id AND ts_code = :ts_code
                """
            ),
            {
                "user_id": user_id,
                "ts_code": row["ts_code"],
                "status": _normalize_status(payload.get("status")),
                "priority": _normalize_priority(payload.get("priority")),
                "tags": json.dumps(_normalize_tags(payload.get("tags")), ensure_ascii=False),
                "thesis": _normalize_text(payload.get("thesis"), "thesis"),
                "trigger_condition": _normalize_text(payload.get("trigger_condition"), "trigger_condition"),
                "risk": _normalize_text(payload.get("risk"), "risk"),
                "exit_condition": _normalize_text(payload.get("exit_condition"), "exit_condition"),
                "industry_trend": score["industry_trend"],
                "competitive_advantage": score["competitive_advantage"],
                "financial_quality": score["financial_quality"],
                "management": score["management"],
                "valuation": score["valuation"],
            },
        )

    return get_research_stock_detail(user_id, row["ts_code"], db_engine)


def create_research_log(user_id: int, ts_code: str, payload: dict, db_engine=engine) -> dict:
    with db_engine.begin() as conn:
        row = _fetch_research_row(conn, user_id, ts_code)
        if not row:
            _not_found("Research stock not found")

        conn.execute(
            text(
                """
                INSERT INTO research_logs (user_id, ts_code, log_date, log_type, content)
                VALUES (:user_id, :ts_code, :log_date, :log_type, :content)
                """
            ),
            {
                "user_id": user_id,
                "ts_code": row["ts_code"],
                "log_date": _normalize_log_date(payload.get("date")),
                "log_type": _normalize_log_type(payload.get("type")),
                "content": _normalize_text(payload.get("content"), "content"),
            },
        )

        created = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar_one_or_none()
        items = _fetch_logs(conn, user_id, row["ts_code"])

    if created is not None:
        for item in items:
            if int(item["id"]) == int(created):
                return item
    return items[0]


def update_research_log(user_id: int, ts_code: str, log_id: int, payload: dict, db_engine=engine) -> dict:
    with db_engine.begin() as conn:
        row = _fetch_research_row(conn, user_id, ts_code)
        if not row:
            _not_found("Research stock not found")

        existing = conn.execute(
            text(
                """
                SELECT id
                FROM research_logs
                WHERE id = :log_id AND user_id = :user_id AND ts_code = :ts_code
                LIMIT 1
                """
            ),
            {"log_id": log_id, "user_id": user_id, "ts_code": row["ts_code"]},
        ).scalar_one_or_none()
        if not existing:
            _not_found("Research log not found")

        conn.execute(
            text(
                """
                UPDATE research_logs
                SET log_date = :log_date, log_type = :log_type, content = :content
                WHERE id = :log_id AND user_id = :user_id AND ts_code = :ts_code
                """
            ),
            {
                "log_id": log_id,
                "user_id": user_id,
                "ts_code": row["ts_code"],
                "log_date": _normalize_log_date(payload.get("date")),
                "log_type": _normalize_log_type(payload.get("type")),
                "content": _normalize_text(payload.get("content"), "content"),
            },
        )

        items = _fetch_logs(conn, user_id, row["ts_code"])

    return next(item for item in items if int(item["id"]) == int(log_id))


def get_research_dashboard(user_id: int, db_engine=engine) -> dict:
    items = list_research_stocks(user_id, db_engine=db_engine)
    status_counts = {status: 0 for status in RESEARCH_STATUSES}
    for item in items:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1

    today_movers = sorted(
        [item for item in items if item.get("change_percent") is not None and abs(float(item["change_percent"])) >= 5],
        key=lambda current: abs(float(current["change_percent"])),
        reverse=True,
    )[:8]

    triggered_items = []
    for item in items:
        mock_item = build_trigger_mock_state(item)
        if mock_item:
            triggered_items.append(mock_item)
    triggered_items = triggered_items[:8]

    with db_engine.begin() as conn:
        recent_log_rows = conn.execute(
            text(
                """
                SELECT
                    rl.id,
                    rl.ts_code,
                    rl.log_date,
                    rl.log_type,
                    rl.content,
                    rl.updated_at,
                    s.name
                FROM research_logs rl
                INNER JOIN stocks s ON s.ts_code = rl.ts_code COLLATE utf8mb4_unicode_ci
                WHERE rl.user_id = :user_id
                ORDER BY rl.log_date DESC, rl.id DESC
                LIMIT 8
                """
            ),
            {"user_id": user_id},
        ).mappings().all()

    recent_logs = []
    for row in recent_log_rows:
        item = serialize_row(row)
        recent_logs.append(
            {
                "id": item["id"],
                "ts_code": item["ts_code"],
                "name": item["name"],
                "date": item["log_date"],
                "type": item["log_type"],
                "content": item["content"],
                "updated_at": item.get("updated_at"),
            }
        )

    stale_deadline = datetime.now() - timedelta(days=STALE_RESEARCH_DAYS)
    stale_items = []
    for item in items:
        updated_at = item.get("updated_at")
        if not updated_at:
            continue
        try:
            updated_at_value = datetime.fromisoformat(str(updated_at))
        except ValueError:
            continue
        if updated_at_value <= stale_deadline:
            stale_items.append(item)
    stale_items.sort(key=lambda current: current.get("updated_at") or "")

    return {
        "statusCounts": status_counts,
        "todayMovers": today_movers,
        "triggeredItems": triggered_items,
        "recentLogs": recent_logs,
        "staleResearchItems": stale_items[:8],
        "isMock": True,
        "staleAfterDays": STALE_RESEARCH_DAYS,
    }
