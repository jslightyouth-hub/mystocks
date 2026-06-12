import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from auth_watchlist_service import (
    add_stock_to_groups,
    create_group,
    delete_group,
    ensure_tables,
    get_current_user_from_authorization,
    get_stock_watchlist_state,
    list_groups,
    list_watchlist_stocks,
    login_user,
    register_user,
    remove_stock_from_watchlist,
    rename_group,
    replace_stock_groups,
)
from research_service import (
    create_research_log,
    create_research_stock,
    ensure_research_tables,
    get_research_dashboard,
    get_research_stock_detail,
    list_research_stocks,
    update_research_log,
    update_research_stock,
)
from industry_tag_service import (
    ensure_industry_financial_tags_table,
    get_industry_tags_for_stock,
    get_l3_industry_tag_overview,
    list_industry_tag_industries,
    list_industry_tag_periods,
    list_industry_tags,
)

from stock_service import (
    get_concept_detail,
    get_concept_movers_rankings,
    get_concept_stock_movers,
    get_concept_stocks,
    get_daily_stock,
    get_industry_detail,
    get_industry_financial_summary,
    get_industry_list,
    get_industry_market,
    get_industry_movers_rankings,
    get_industry_stock_movers,
    get_industry_stocks,
    get_l2_industry_children,
    get_previous_day_bottom_movers,
    get_previous_day_top_movers,
    search_stocks,
    get_today,
    get_volume_movers,
)


app = FastAPI()


BASE_DIR = Path(__file__).resolve().parent
ADMIN_LOG_DIR = BASE_DIR / "admin_logs"
SCRIPT_RUNS = {}


class CredentialsPayload(BaseModel):
    username: str
    password: str


class WatchlistGroupPayload(BaseModel):
    name: str


class WatchlistStockPayload(BaseModel):
    group_ids: list[int]


class ResearchScorePayload(BaseModel):
    industry_trend: int = 3
    competitive_advantage: int = 3
    financial_quality: int = 3
    management: int = 3
    valuation: int = 3


class ResearchStockCreatePayload(BaseModel):
    ts_code: str
    status: str = "watchlist"
    priority: str = "medium"
    tags: list[str] = []
    thesis: str = ""
    trigger_condition: str = ""
    risk: str = ""
    exit_condition: str = ""
    score: ResearchScorePayload = ResearchScorePayload()


class ResearchStockUpdatePayload(BaseModel):
    status: str = "watchlist"
    priority: str = "medium"
    tags: list[str] = []
    thesis: str = ""
    trigger_condition: str = ""
    risk: str = ""
    exit_condition: str = ""
    score: ResearchScorePayload = ResearchScorePayload()


class ResearchLogPayload(BaseModel):
    date: str
    type: str
    content: str


def _tail_text(path: Path, max_chars: int = 12000):
    if not path.exists():
        return ""

    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def _get_daily_update_run():
    run = SCRIPT_RUNS.get("daily_market_update")
    if not run:
        return {
            "id": "daily_market_update",
            "title": "每日行情数据更新",
            "running": False,
            "status": "idle",
            "started_at": None,
            "finished_at": None,
            "return_code": None,
            "pid": None,
            "log": "",
        }

    process = run.get("process")
    return_code = process.poll() if process else run.get("return_code")
    running = return_code is None

    if not running and run.get("finished_at") is None:
        run["finished_at"] = datetime.now().isoformat(timespec="seconds")
        run["return_code"] = return_code

    status = "running" if running else ("success" if return_code == 0 else "failed")

    return {
        "id": "daily_market_update",
        "title": "每日行情数据更新",
        "running": running,
        "status": status,
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "return_code": return_code,
        "pid": process.pid if process else run.get("pid"),
        "log": _tail_text(run["log_path"]),
    }


def _get_industry_tags_run():
    run = SCRIPT_RUNS.get("industry_financial_tags")
    if not run:
        return {
            "id": "industry_financial_tags",
            "title": "三级行业财务标签生成",
            "running": False,
            "status": "idle",
            "started_at": None,
            "finished_at": None,
            "return_code": None,
            "pid": None,
            "log": "",
        }

    process = run.get("process")
    return_code = process.poll() if process else run.get("return_code")
    running = return_code is None

    if not running and run.get("finished_at") is None:
        run["finished_at"] = datetime.now().isoformat(timespec="seconds")
        run["return_code"] = return_code

    status = "running" if running else ("success" if return_code == 0 else "failed")

    return {
        "id": "industry_financial_tags",
        "title": "三级行业财务标签生成",
        "running": running,
        "status": status,
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "return_code": return_code,
        "pid": process.pid if process else run.get("pid"),
        "log": _tail_text(run["log_path"]),
    }


@app.on_event("startup")
def startup():
    ensure_tables()
    ensure_research_tables()
    ensure_industry_financial_tags_table()


def get_current_user(authorization: str | None = Header(default=None)):
    return get_current_user_from_authorization(authorization)


# Allow the Vite frontend on port 5173 to request this API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/stock/{ts_code}")
def get_stock(ts_code: str):
    # Keep the route thin: date and Tushare querying live in stock_service.py.
    today = get_today()
    stock = get_daily_stock(ts_code, today)

    if stock is None:
        raise HTTPException(status_code=404, detail=f"No stock data found for {today}")

    return stock


@app.get("/stocks/top-movers")
def get_top_movers(page: int = 1, page_size: int = 50):
    return get_previous_day_top_movers(page, page_size)


@app.get("/stocks/bottom-movers")
def get_bottom_movers(page: int = 1, page_size: int = 50):
    return get_previous_day_bottom_movers(page, page_size)


@app.get("/stocks/volume-movers")
def get_stock_volume_movers(page: int = 1, page_size: int = 50, sort: str = "vol_ratio_20_desc"):
    return get_volume_movers(page, page_size, sort)


@app.get("/api/v1/stocks/search")
def search_stock_list(q: str = "", limit: int = 10):
    return {"items": search_stocks(q, limit)}


@app.post("/api/v1/auth/register")
def register(payload: CredentialsPayload):
    return register_user(payload.username, payload.password)


@app.post("/api/v1/auth/login")
def login(payload: CredentialsPayload):
    return login_user(payload.username, payload.password)


@app.get("/api/v1/auth/me")
def get_me(user=Depends(get_current_user)):
    return {"user": user}


@app.post("/api/v1/auth/logout")
def logout():
    return {"success": True}


@app.get("/api/v1/watchlist/groups")
def get_watchlist_groups(user=Depends(get_current_user)):
    return {"items": list_groups(int(user["id"]))}


@app.post("/api/v1/watchlist/groups")
def post_watchlist_group(payload: WatchlistGroupPayload, user=Depends(get_current_user)):
    return create_group(int(user["id"]), payload.name)


@app.patch("/api/v1/watchlist/groups/{group_id}")
def patch_watchlist_group(group_id: int, payload: WatchlistGroupPayload, user=Depends(get_current_user)):
    return rename_group(int(user["id"]), group_id, payload.name)


@app.delete("/api/v1/watchlist/groups/{group_id}")
def remove_watchlist_group(group_id: int, user=Depends(get_current_user)):
    return delete_group(int(user["id"]), group_id)


@app.get("/api/v1/watchlist/stocks")
def get_watchlist(user=Depends(get_current_user)):
    return {"items": list_watchlist_stocks(int(user["id"]))}


@app.get("/api/v1/watchlist/stocks/{ts_code}")
def get_watchlist_stock(ts_code: str, user=Depends(get_current_user)):
    return get_stock_watchlist_state(int(user["id"]), ts_code)


@app.post("/api/v1/watchlist/stocks/{ts_code}")
def add_watchlist_stock(ts_code: str, payload: WatchlistStockPayload, user=Depends(get_current_user)):
    return add_stock_to_groups(int(user["id"]), ts_code, payload.group_ids)


@app.put("/api/v1/watchlist/stocks/{ts_code}")
def put_watchlist_stock(ts_code: str, payload: WatchlistStockPayload, user=Depends(get_current_user)):
    return replace_stock_groups(int(user["id"]), ts_code, payload.group_ids)


@app.delete("/api/v1/watchlist/stocks/{ts_code}")
def delete_watchlist_stock(ts_code: str, user=Depends(get_current_user)):
    return remove_stock_from_watchlist(int(user["id"]), ts_code)


@app.get("/api/v1/research/dashboard")
def get_research_dashboard_route(user=Depends(get_current_user)):
    return get_research_dashboard(int(user["id"]))


@app.get("/api/v1/research/stocks")
def get_research_stocks(
    status: str | None = None,
    priority: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    user=Depends(get_current_user),
):
    return {
        "items": list_research_stocks(
            int(user["id"]),
            status=status,
            priority=priority,
            tag=tag,
            q=q,
        )
    }


@app.post("/api/v1/research/stocks")
def post_research_stock(payload: ResearchStockCreatePayload, user=Depends(get_current_user)):
    return create_research_stock(int(user["id"]), payload.model_dump())


@app.get("/api/v1/research/stocks/{ts_code}")
def get_research_stock(ts_code: str, user=Depends(get_current_user)):
    return get_research_stock_detail(int(user["id"]), ts_code)


@app.put("/api/v1/research/stocks/{ts_code}")
def put_research_stock(ts_code: str, payload: ResearchStockUpdatePayload, user=Depends(get_current_user)):
    return update_research_stock(int(user["id"]), ts_code, payload.model_dump())


@app.post("/api/v1/research/stocks/{ts_code}/logs")
def post_research_log(ts_code: str, payload: ResearchLogPayload, user=Depends(get_current_user)):
    return create_research_log(int(user["id"]), ts_code, payload.model_dump())


@app.put("/api/v1/research/stocks/{ts_code}/logs/{log_id}")
def put_research_log(ts_code: str, log_id: int, payload: ResearchLogPayload, user=Depends(get_current_user)):
    return update_research_log(int(user["id"]), ts_code, log_id, payload.model_dump())


@app.get("/api/v1/admin/scripts/daily-market-update")
def get_daily_market_update_status():
    return _get_daily_update_run()


@app.post("/api/v1/admin/scripts/daily-market-update/run")
def run_daily_market_update():
    current = _get_daily_update_run()
    if current["running"]:
        raise HTTPException(status_code=409, detail="每日行情数据更新正在运行")

    ADMIN_LOG_DIR.mkdir(exist_ok=True)
    started_at = datetime.now().isoformat(timespec="seconds")
    log_path = ADMIN_LOG_DIR / f"daily_market_update_{started_at.replace(':', '').replace('-', '')}.log"

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")

    log_file = log_path.open("w", encoding="utf-8", errors="replace")
    process = subprocess.Popen(
        [sys.executable, "update_all_market_data.py"],
        cwd=str(BASE_DIR),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
    )
    log_file.close()

    SCRIPT_RUNS["daily_market_update"] = {
        "process": process,
        "pid": process.pid,
        "started_at": started_at,
        "finished_at": None,
        "return_code": None,
        "log_path": log_path,
    }

    return _get_daily_update_run()


@app.get("/api/v1/admin/scripts/industry-tags")
def get_industry_tags_script_status():
    return _get_industry_tags_run()


@app.post("/api/v1/admin/scripts/industry-tags/run")
def run_industry_tags_script():
    current = _get_industry_tags_run()
    if current["running"]:
        raise HTTPException(status_code=409, detail="三级行业财务标签生成正在运行")

    ADMIN_LOG_DIR.mkdir(exist_ok=True)
    started_at = datetime.now().isoformat(timespec="seconds")
    log_path = ADMIN_LOG_DIR / f"industry_financial_tags_{started_at.replace(':', '').replace('-', '')}.log"

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")

    log_file = log_path.open("w", encoding="utf-8", errors="replace")
    process = subprocess.Popen(
        [sys.executable, "sync_industry_financial_tags.py"],
        cwd=str(BASE_DIR),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
    )
    log_file.close()

    SCRIPT_RUNS["industry_financial_tags"] = {
        "process": process,
        "pid": process.pid,
        "started_at": started_at,
        "finished_at": None,
        "return_code": None,
        "log_path": log_path,
    }

    return _get_industry_tags_run()


@app.get("/api/v1/industry-tags/periods")
def get_industry_tag_periods():
    return list_industry_tag_periods()


@app.get("/api/v1/industry-tags/industries")
def get_industry_tag_industries(period: str = "latest"):
    return list_industry_tag_industries(period)


@app.get("/api/v1/industry-tags/stocks/{ts_code}")
def get_industry_stock_tags(ts_code: str, period: str | None = None, tag_category: str | None = None):
    return get_industry_tags_for_stock(ts_code, period=period, tag_category=tag_category)


@app.get("/api/v1/industry-tags/l3/{sw_l3_code}")
def get_l3_industry_tags(sw_l3_code: str, period: str = "latest"):
    return get_l3_industry_tag_overview(sw_l3_code, period=period)


@app.get("/api/v1/industry-tags")
def get_industry_tags(
    period: str = "latest",
    sw_l3_code: str | None = None,
    tag_category: str | None = None,
    tag_code: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    return list_industry_tags(
        period=period,
        sw_l3_code=sw_l3_code,
        tag_category=tag_category,
        tag_code=tag_code,
        page=page,
        page_size=page_size,
    )


@app.get("/api/v1/industries/l2")
def list_l2_industries():
    return get_industry_list("l2")


@app.get("/api/v1/industries/l1")
def list_l1_industries():
    return get_industry_list("l1")


@app.get("/api/v1/industries/l2/movers")
def get_l2_industry_movers(exclude_high: int = 1, exclude_low: int = 1):
    return get_industry_movers_rankings(exclude_high, exclude_low)


@app.get("/api/v1/industries/l1/movers")
def get_l1_industry_movers(exclude_high: int = 1, exclude_low: int = 1):
    return get_industry_movers_rankings(exclude_high, exclude_low, level="l1")


@app.get("/api/v1/industries/l3/movers")
def get_l3_industry_movers(exclude_high: int = 1, exclude_low: int = 1):
    return get_industry_movers_rankings(exclude_high, exclude_low, level="l3")


@app.get("/api/v1/concepts/movers")
def get_concept_movers():
    return get_concept_movers_rankings()


@app.get("/api/v1/concepts/{concept_code}")
def get_concept(concept_code: str):
    concept = get_concept_detail(concept_code)
    if concept is None:
        raise HTTPException(status_code=404, detail=f"No concept found: {concept_code}")
    return concept


@app.get("/api/v1/concepts/{concept_code}/movers")
def get_concept_movers_detail(
    concept_code: str,
    page: int = 1,
    page_size: int = 10,
    direction: str = "top",
):
    movers = get_concept_stock_movers(concept_code, page, page_size, direction)
    if movers is None:
        raise HTTPException(status_code=404, detail=f"No concept found: {concept_code}")
    return movers


@app.get("/api/v1/concepts/{concept_code}/stocks")
def get_concept_stock_list(
    concept_code: str,
    page: int = 1,
    page_size: int = 50,
    sort: str = "pct_chg_desc",
):
    stocks = get_concept_stocks(concept_code, page, page_size, sort)
    if stocks is None:
        raise HTTPException(status_code=404, detail=f"No concept found: {concept_code}")
    return stocks


@app.get("/api/v1/industries/l1/{l1_code}")
def get_l1_industry(l1_code: str):
    industry = get_industry_detail("l1", l1_code)
    if industry is None:
        raise HTTPException(status_code=404, detail=f"No L1 industry found: {l1_code}")
    return industry


@app.get("/api/v1/industries/l1/{l1_code}/stocks")
def get_l1_industry_stocks(
    l1_code: str,
    page: int = 1,
    page_size: int = 50,
    sort: str = "pct_chg_desc",
):
    return get_industry_stocks("l1", l1_code, page, page_size, sort)


@app.get("/api/v1/industries/l1/{l1_code}/market")
def get_l1_industry_market(l1_code: str):
    market = get_industry_market("l1", l1_code)
    if market is None:
        raise HTTPException(status_code=404, detail=f"No L1 industry market found: {l1_code}")
    return market


@app.get("/api/v1/industries/l1/{l1_code}/movers")
def get_l1_industry_stock_movers(l1_code: str, limit: int = 10):
    return get_industry_stock_movers("l1", l1_code, limit)


@app.get("/api/v1/industries/l1/{l1_code}/financials/summary")
def get_l1_financial_summary(l1_code: str):
    summary = get_industry_financial_summary("l1", l1_code)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"No L1 industry financials found: {l1_code}")
    return summary


@app.get("/api/v1/industries/l2/{l2_code}")
def get_l2_industry(l2_code: str):
    industry = get_industry_detail("l2", l2_code)
    if industry is None:
        raise HTTPException(status_code=404, detail=f"No L2 industry found: {l2_code}")
    return industry


@app.get("/api/v1/industries/l2/{l2_code}/children")
def get_l2_children(l2_code: str):
    return get_l2_industry_children(l2_code)


@app.get("/api/v1/industries/l2/{l2_code}/stocks")
def get_l2_industry_stocks(
    l2_code: str,
    page: int = 1,
    page_size: int = 50,
    sort: str = "pct_chg_desc",
):
    return get_industry_stocks("l2", l2_code, page, page_size, sort)


@app.get("/api/v1/industries/l2/{l2_code}/market")
def get_l2_industry_market(l2_code: str):
    market = get_industry_market("l2", l2_code)
    if market is None:
        raise HTTPException(status_code=404, detail=f"No L2 industry market found: {l2_code}")
    return market


@app.get("/api/v1/industries/l2/{l2_code}/movers")
def get_l2_industry_stock_movers(l2_code: str, limit: int = 10):
    return get_industry_stock_movers("l2", l2_code, limit)


@app.get("/api/v1/industries/l2/{l2_code}/financials/summary")
def get_l2_financial_summary(l2_code: str):
    summary = get_industry_financial_summary("l2", l2_code)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"No L2 industry financials found: {l2_code}")
    return summary


@app.get("/api/v1/industries/l3/{l3_code}")
def get_l3_industry(l3_code: str):
    industry = get_industry_detail("l3", l3_code)
    if industry is None:
        raise HTTPException(status_code=404, detail=f"No L3 industry found: {l3_code}")
    return industry


@app.get("/api/v1/industries/l3/{l3_code}/stocks")
def get_l3_industry_stocks(
    l3_code: str,
    page: int = 1,
    page_size: int = 50,
    sort: str = "pct_chg_desc",
):
    return get_industry_stocks("l3", l3_code, page, page_size, sort)


@app.get("/api/v1/industries/l3/{l3_code}/market")
def get_l3_industry_market(l3_code: str):
    market = get_industry_market("l3", l3_code)
    if market is None:
        raise HTTPException(status_code=404, detail=f"No L3 industry market found: {l3_code}")
    return market


@app.get("/api/v1/industries/l3/{l3_code}/movers")
def get_l3_industry_stock_movers(l3_code: str, limit: int = 10):
    return get_industry_stock_movers("l3", l3_code, limit)


@app.get("/api/v1/industries/l3/{l3_code}/financials/summary")
def get_l3_financial_summary(l3_code: str):
    summary = get_industry_financial_summary("l3", l3_code)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"No L3 industry financials found: {l3_code}")
    return summary
