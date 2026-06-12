import argparse
import json
import random
import re
import subprocess
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import requests
import websocket
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text

from settings import DATABASE_URL


SOURCE = "THS"
CONCEPT_LIST_URL = "https://q.10jqka.com.cn/gn/"
CONCEPT_DETAIL_URL = "https://q.10jqka.com.cn/gn/detail/code/{concept_code}/"
CONCEPT_PAGE_URL = "https://q.10jqka.com.cn/gn/detail/code/{concept_code}/page/{page}/"
CONCEPT_AJAX_PAGE_URL = (
    "https://q.10jqka.com.cn/gn/detail/board/0/field/199112/order/desc/"
    "page/{page}/ajax/1/code/{concept_code}/"
)
DEFAULT_WORKERS = 4
DEFAULT_DELAY_SECONDS = 0.25
DEFAULT_MAX_PAGES = 5
REQUEST_TIMEOUT_SECONDS = 20
MAX_RETRIES = 3
HEXIN_SCRIPT_PATH = "chameleon.js"
USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
        "Gecko/20100101 Firefox/126.0"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
]

engine = create_engine(DATABASE_URL)
print_lock = threading.Lock()
http_session = requests.Session()
edge_fetch_ws_url = None
edge_fetch_ws = None
edge_fetch_message_id = 100
edge_fetch_lock = threading.Lock()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sync public Tonghuashun concept and concept-stock membership pages."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Concurrent concept fetch workers. Default: 4.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help="Polite delay after each HTTP request in seconds. Default: 0.25.",
    )
    parser.add_argument(
        "--limit-concepts",
        type=int,
        default=None,
        help="Only sync the first N concepts. Useful for testing.",
    )
    parser.add_argument(
        "--concept-code",
        default=None,
        help="Only sync one Tonghuashun concept code, for example 309115.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help="Limit pages per concept. Default: 5 for stable public-page sync.",
    )
    parser.add_argument(
        "--all-pages",
        action="store_true",
        help="Fetch every page reported by Tonghuashun. This can be slow and less stable.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip concepts that already have current stock_concepts rows.",
    )
    parser.add_argument(
        "--use-db-concepts",
        action="store_true",
        help="Read concept list from local concepts table instead of Tonghuashun list page.",
    )
    parser.add_argument(
        "--use-hexin-v",
        action="store_true",
        help="Generate and send Tonghuashun hexin-v cookie/header for protected requests.",
    )
    parser.add_argument(
        "--edge-debug-url",
        default=None,
        help=(
            "Use cookies from an Edge/Chrome CDP endpoint, "
            "for example http://127.0.0.1:9222."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse data without writing database rows.",
    )
    return parser.parse_args()


def log(message):
    with print_lock:
        print(message, flush=True)


def generate_hexin_v(target_url):
    try:
        result = subprocess.run(
            [
                "node",
                "tools_ths_hexin_v.js",
                HEXIN_SCRIPT_PATH,
                target_url,
            ],
            cwd=str(__import__("pathlib").Path(__file__).resolve().parent),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout).get("hexinV")
    except Exception:
        return None


def cdp_call(ws, message_id, method, params=None):
    ws.send(json.dumps({
        "id": message_id,
        "method": method,
        "params": params or {},
    }))
    while True:
        message = json.loads(ws.recv())
        if message.get("id") == message_id:
            if "error" in message:
                raise RuntimeError(message["error"].get("message", message["error"]))
            return message.get("result", {})


def edge_cdp_call(method, params=None):
    global edge_fetch_ws
    global edge_fetch_message_id

    if not edge_fetch_ws_url:
        raise RuntimeError("Edge browser fetcher is not configured")

    with edge_fetch_lock:
        if edge_fetch_ws is None:
            edge_fetch_ws = websocket.create_connection(
                edge_fetch_ws_url,
                timeout=30,
                suppress_origin=True,
            )

        edge_fetch_message_id += 1
        message_id = edge_fetch_message_id
        try:
            edge_fetch_ws.send(json.dumps({
                "id": message_id,
                "method": method,
                "params": params or {},
            }))
            while True:
                message = json.loads(edge_fetch_ws.recv())
                if message.get("id") != message_id:
                    continue
                if "error" in message:
                    raise RuntimeError(message["error"].get("message", message["error"]))
                return message.get("result", {})
        except Exception:
            try:
                edge_fetch_ws.close()
            except Exception:
                pass
            edge_fetch_ws = None
            raise


def fetch_html_with_edge(url):
    expression = """
        fetch(%s, {
            credentials: 'include',
            headers: {'X-Requested-With': 'XMLHttpRequest'}
        }).then(async (response) => {
            const buffer = await response.arrayBuffer();
            const text = new TextDecoder('gbk').decode(buffer);
            return {status: response.status, text};
        })
    """ % json.dumps(url)
    result = edge_cdp_call(
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
        },
    )
    value = result.get("result", {}).get("value") or {}
    status_code = value.get("status")
    text_value = value.get("text") or ""
    if status_code in {401, 403, 429, 500, 502, 503, 504}:
        raise RuntimeError(f"HTTP {status_code}")
    if status_code and status_code >= 400:
        raise RuntimeError(f"HTTP {status_code}")
    return text_value


def load_edge_cookies(debug_url):
    global edge_fetch_ws_url

    tabs_url = debug_url.rstrip("/") + "/json"
    with urllib.request.urlopen(tabs_url, timeout=10) as response:
        tabs = json.loads(response.read().decode("utf-8"))

    tab = next(
        (
            item for item in tabs
            if item.get("type") == "page"
            and "q.10jqka.com.cn" in item.get("url", "")
            and item.get("webSocketDebuggerUrl")
        ),
        None,
    )
    if tab is None:
        tab = next(
            (
                item for item in tabs
                if item.get("type") == "page" and item.get("webSocketDebuggerUrl")
            ),
            None,
        )
    if tab is None:
        raise RuntimeError(f"No debuggable Edge/Chrome page found at {tabs_url}")

    edge_fetch_ws_url = tab["webSocketDebuggerUrl"]
    ws = websocket.create_connection(
        tab["webSocketDebuggerUrl"],
        timeout=10,
        suppress_origin=True,
    )
    try:
        cdp_call(ws, 1, "Network.enable")
        cookies_result = cdp_call(ws, 2, "Network.getAllCookies")
        login_result = cdp_call(
            ws,
            3,
            "Runtime.evaluate",
            {
                "expression": "document.body ? document.body.innerText : ''",
                "returnByValue": True,
            },
        )
    finally:
        ws.close()

    cookie_count = 0
    login_text = login_result.get("result", {}).get("value") or ""
    for cookie in cookies_result.get("cookies", []):
        domain = cookie.get("domain") or ""
        if "10jqka.com.cn" not in domain:
            continue
        http_session.cookies.set(
            cookie.get("name"),
            cookie.get("value"),
            domain=domain,
            path=cookie.get("path") or "/",
        )
        cookie_count += 1

    return {
        "tab_url": tab.get("url"),
        "cookie_count": cookie_count,
        "logged_in": "退出" in login_text,
    }


def request_headers(referer=None, hexin_v=None, user_agent=None):
    headers = {
        "User-Agent": user_agent or random.choice(USER_AGENTS),
        "Accept": "text/html, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "X-Requested-With": "XMLHttpRequest",
    }
    if referer:
        headers["Referer"] = referer
    if hexin_v:
        headers["hexin-v"] = hexin_v
        headers["Cookie"] = f"v={hexin_v}"
    return headers


def fetch_html(url, referer=None, retries=MAX_RETRIES, delay=DEFAULT_DELAY_SECONDS, use_hexin_v=False):
    last_error = None
    if edge_fetch_ws_url and url.startswith("https://q.10jqka.com.cn/"):
        for attempt in range(1, retries + 1):
            try:
                return fetch_html_with_edge(url)
            except Exception as exc:
                last_error = exc
                if attempt == retries:
                    break
                time.sleep(delay * attempt + random.uniform(0, delay))
        raise RuntimeError(f"Failed to fetch {url} with Edge: {last_error}")

    for attempt in range(1, retries + 1):
        candidate_url = url
        try:
            hexin_v = generate_hexin_v(candidate_url) if use_hexin_v else None
            response = http_session.get(
                candidate_url,
                headers=request_headers(referer, hexin_v, USER_AGENTS[0]),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code in {401, 403, 429, 500, 502, 503, 504}:
                raise RuntimeError(f"HTTP {response.status_code}")
            response.raise_for_status()
            text_value = response.content.decode("gbk", errors="replace")
            if (
                len(text_value) < 2000
                and "location.href" in text_value
                and "upass.10jqka.com.cn/login" in text_value
            ):
                raise RuntimeError("login required")
            return text_value
        except Exception as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(delay * attempt + random.uniform(0, delay))
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def create_tables():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS concepts (
                id BIGINT NOT NULL AUTO_INCREMENT,
                source VARCHAR(20) NOT NULL,
                concept_code VARCHAR(30) NOT NULL,
                concept_name VARCHAR(100) NOT NULL,
                detail_url VARCHAR(255) NULL,
                created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uq_concepts_source_code (source, concept_code),
                KEY idx_concepts_name (concept_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stock_concepts (
                id BIGINT NOT NULL AUTO_INCREMENT,
                source VARCHAR(20) NOT NULL,
                concept_code VARCHAR(30) NOT NULL,
                ts_code VARCHAR(20) NOT NULL,
                stock_name VARCHAR(100) NULL,
                rank_no INT NULL,
                latest_price DECIMAL(16, 4) NULL,
                pct_chg DECIMAL(12, 4) NULL,
                turnover_rate DECIMAL(12, 4) NULL,
                amount_text VARCHAR(50) NULL,
                float_share_text VARCHAR(50) NULL,
                float_mv_text VARCHAR(50) NULL,
                pe_text VARCHAR(50) NULL,
                is_current TINYINT NOT NULL DEFAULT 1,
                created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uq_stock_concepts_source_code_stock (source, concept_code, ts_code),
                KEY idx_stock_concepts_ts_code (ts_code),
                KEY idx_stock_concepts_concept (source, concept_code),
                KEY idx_stock_concepts_current (is_current)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))


def parse_concept_code_from_url(url):
    match = re.search(r"/code/(\d+)/?", url)
    return match.group(1) if match else None


def normalize_detail_url(url):
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme == "http":
        return "https://" + parsed.netloc + parsed.path
    return url


def parse_concept_list(html):
    soup = BeautifulSoup(html, "html.parser")
    concepts = []
    seen_codes = set()

    for link in soup.select("a[href*='/gn/detail/code/']"):
        name = link.get_text(strip=True)
        href = normalize_detail_url(link.get("href"))
        code = parse_concept_code_from_url(href or "")
        if not name or not code or code in seen_codes:
            continue
        seen_codes.add(code)
        concepts.append({
            "source": SOURCE,
            "concept_code": code,
            "concept_name": name,
            "detail_url": href,
        })

    return concepts


def get_total_pages(soup):
    page_info = soup.select_one(".page_info")
    if page_info:
        match = re.search(r"/(\d+)", page_info.get_text(strip=True))
        if match:
            return int(match.group(1))

    page_numbers = []
    for link in soup.select("a[page]"):
        page = link.get("page")
        if page and page.isdigit():
            page_numbers.append(int(page))
    return max(page_numbers) if page_numbers else 1


def parse_decimal(value):
    value = (value or "").strip().replace(",", "")
    if not value or value == "--":
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def stock_code_to_ts_code(code):
    code = (code or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        return None
    if code.startswith(("6", "9")):
        suffix = "SH"
    elif code.startswith(("0", "2", "3")):
        suffix = "SZ"
    elif code.startswith(("4", "8")):
        suffix = "BJ"
    else:
        suffix = ""
    return f"{code}.{suffix}" if suffix else code


def parse_member_table(html, concept):
    soup = BeautifulSoup(html, "html.parser")
    table = find_member_table(soup)
    if not table:
        return [], get_total_pages(soup)

    members = []
    for tr in table.select("tr"):
        cells = [cell.get_text(strip=True) for cell in tr.find_all(["td", "th"])]
        if len(cells) < 14 or not cells[0].isdigit():
            continue

        ts_code = stock_code_to_ts_code(cells[1])
        if not ts_code:
            continue

        members.append({
            "source": SOURCE,
            "concept_code": concept["concept_code"],
            "ts_code": ts_code,
            "stock_name": cells[2],
            "rank_no": int(cells[0]),
            "latest_price": parse_decimal(cells[3]),
            "pct_chg": parse_decimal(cells[4]),
            "turnover_rate": parse_decimal(cells[7]),
            "amount_text": cells[10] or None,
            "float_share_text": cells[11] or None,
            "float_mv_text": cells[12] or None,
            "pe_text": cells[13] or None,
        })

    return members, get_total_pages(soup)


def find_member_table(soup):
    for table in soup.find_all("table"):
        header_text = table.get_text("\t", strip=True)[:120]
        if "序号" in header_text and "代码" in header_text and "名称" in header_text and "涨跌幅" in header_text:
            return table
    return None


def fetch_concepts(delay=DEFAULT_DELAY_SECONDS, use_hexin_v=False):
    html = fetch_html(CONCEPT_LIST_URL, delay=delay, use_hexin_v=use_hexin_v)
    return parse_concept_list(html)


def get_concepts_from_db():
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT source, concept_code, concept_name, detail_url
                FROM concepts
                WHERE source = :source
                ORDER BY concept_code
            """),
            {"source": SOURCE},
        ).mappings().all()
    return [dict(row) for row in rows]


def fetch_concept_members(
    concept,
    max_pages=None,
    delay=DEFAULT_DELAY_SECONDS,
    use_hexin_v=False,
    use_ajax_pages=False,
):
    detail_url = CONCEPT_DETAIL_URL.format(concept_code=concept["concept_code"])
    if use_ajax_pages:
        first_url = CONCEPT_AJAX_PAGE_URL.format(
            concept_code=concept["concept_code"],
            page=1,
        )
    else:
        first_url = detail_url
    first_html = fetch_html(first_url, referer=CONCEPT_LIST_URL, delay=delay, use_hexin_v=use_hexin_v)
    members, total_pages = parse_member_table(first_html, concept)
    fetched_pages = 1
    page_errors = []

    if max_pages is not None:
        total_pages = min(total_pages, max(max_pages, 1))

    page_url_template = CONCEPT_AJAX_PAGE_URL if use_ajax_pages else CONCEPT_PAGE_URL
    for page in range(2, total_pages + 1):
        page_url = page_url_template.format(
            concept_code=concept["concept_code"],
            page=page,
        )
        try:
            html = fetch_html(page_url, referer=detail_url, delay=delay, use_hexin_v=use_hexin_v)
            page_members, _ = parse_member_table(html, concept)
            members.extend(page_members)
            fetched_pages = page
        except Exception as exc:
            page_errors.append({"page": page, "error": str(exc)})
            break
        time.sleep(delay + random.uniform(0, delay))

    return {
        "concept": concept,
        "total_pages": total_pages,
        "fetched_pages": fetched_pages,
        "page_errors": page_errors,
        "members": dedupe_members(members),
    }


def dedupe_members(members):
    deduped = {}
    for member in members:
        deduped[member["ts_code"]] = member
    return list(deduped.values())


def save_concepts(concepts):
    if not concepts:
        return 0
    sql = text("""
        INSERT INTO concepts (
            source,
            concept_code,
            concept_name,
            detail_url
        )
        VALUES (
            :source,
            :concept_code,
            :concept_name,
            :detail_url
        )
        ON DUPLICATE KEY UPDATE
            concept_name = VALUES(concept_name),
            detail_url = VALUES(detail_url)
    """)
    with engine.begin() as conn:
        conn.execute(sql, concepts)
    return len(concepts)


def save_members_for_concept(concept, members):
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE stock_concepts
                SET is_current = 0
                WHERE source = :source
                    AND concept_code = :concept_code
            """),
            {
                "source": SOURCE,
                "concept_code": concept["concept_code"],
            },
        )

        if not members:
            return 0

        conn.execute(
            text("""
                INSERT INTO stock_concepts (
                    source,
                    concept_code,
                    ts_code,
                    stock_name,
                    rank_no,
                    latest_price,
                    pct_chg,
                    turnover_rate,
                    amount_text,
                    float_share_text,
                    float_mv_text,
                    pe_text,
                    is_current
                )
                VALUES (
                    :source,
                    :concept_code,
                    :ts_code,
                    :stock_name,
                    :rank_no,
                    :latest_price,
                    :pct_chg,
                    :turnover_rate,
                    :amount_text,
                    :float_share_text,
                    :float_mv_text,
                    :pe_text,
                    1
                )
                ON DUPLICATE KEY UPDATE
                    stock_name = VALUES(stock_name),
                    rank_no = VALUES(rank_no),
                    latest_price = VALUES(latest_price),
                    pct_chg = VALUES(pct_chg),
                    turnover_rate = VALUES(turnover_rate),
                    amount_text = VALUES(amount_text),
                    float_share_text = VALUES(float_share_text),
                    float_mv_text = VALUES(float_mv_text),
                    pe_text = VALUES(pe_text),
                    is_current = 1
            """),
            members,
        )
    return len(members)


def get_sample_rows(limit=10):
    with engine.connect() as conn:
        return conn.execute(
            text("""
                SELECT
                    c.concept_name,
                    sc.concept_code,
                    sc.ts_code,
                    sc.stock_name,
                    sc.pct_chg,
                    sc.turnover_rate
                FROM stock_concepts sc
                JOIN concepts c
                    ON c.source = sc.source COLLATE utf8mb4_unicode_ci
                    AND c.concept_code = sc.concept_code COLLATE utf8mb4_unicode_ci
                WHERE sc.source = :source
                    AND sc.is_current = 1
                ORDER BY c.concept_code, sc.rank_no
                LIMIT :limit
            """),
            {"source": SOURCE, "limit": limit},
        ).mappings().all()


def get_existing_concept_codes():
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT DISTINCT concept_code
                FROM stock_concepts
                WHERE source = :source
                    AND is_current = 1
            """),
            {"source": SOURCE},
        ).scalars().all()
    return set(rows)


def print_summary(total_concepts, saved_concepts, success_count, failed_items, total_members):
    print("")
    print("=" * 78)
    print("Summary")
    print("=" * 78)
    print(f"Concepts fetched: {total_concepts}")
    print(f"Concepts saved: {saved_concepts}")
    print(f"Concepts synced successfully: {success_count}")
    print(f"Concepts failed: {len(failed_items)}")
    print(f"Current stock-concept rows saved: {total_members}")
    if failed_items:
        print("Failed concepts:")
        for item in failed_items[:20]:
            concept = item["concept"]
            print(f"  {concept['concept_code']} {concept['concept_name']}: {item['error']}")


def main():
    args = parse_args()
    worker_count = max(args.workers, 1)
    delay = max(args.delay, 0)

    print("Tonghuashun concept sync")
    print(f"Workers: {worker_count}")
    print(f"Delay: {delay}s")
    print(f"Dry run: {args.dry_run}")
    max_pages = None if args.all_pages else args.max_pages
    print(f"Max pages per concept: {'all' if max_pages is None else max_pages}")
    use_ajax_pages = bool(args.edge_debug_url) or max_pages is None

    if args.edge_debug_url:
        edge_state = load_edge_cookies(args.edge_debug_url)
        print(
            "Edge login state: "
            f"cookies={edge_state['cookie_count']}, "
            f"logged_in={edge_state['logged_in']}, "
            f"tab={edge_state['tab_url']}"
        )

    if args.use_db_concepts:
        create_tables()
        concepts = get_concepts_from_db()
        print(f"Loaded concept list from database: {len(concepts)}")
    else:
        concepts = fetch_concepts(delay=delay, use_hexin_v=args.use_hexin_v)
    if args.concept_code:
        concepts = [
            concept for concept in concepts
            if concept["concept_code"] == args.concept_code
        ]
    if args.limit_concepts:
        concepts = concepts[:args.limit_concepts]

    if not concepts:
        print("No concepts found.")
        return

    if args.skip_existing and not args.dry_run:
        create_tables()
        existing_codes = get_existing_concept_codes()
        before_count = len(concepts)
        concepts = [
            concept for concept in concepts
            if concept["concept_code"] not in existing_codes
        ]
        print(f"Skipped concepts with existing current members: {before_count - len(concepts)}")
        if not concepts:
            print("No remaining concepts to sync.")
            return

    print(f"Fetched concept list: {len(concepts)}")
    if not args.dry_run:
        create_tables()
        saved_concepts = save_concepts(concepts)
    else:
        saved_concepts = 0
        print("Dry run: concept rows will not be written.")

    total_members = 0
    success_count = 0
    failed_items = []

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {
            executor.submit(
                fetch_concept_members,
                concept,
                max_pages,
                delay,
                args.use_hexin_v,
                use_ajax_pages,
            ): concept
            for concept in concepts
        }
        for index, future in enumerate(as_completed(future_map), start=1):
            concept = future_map[future]
            try:
                result = future.result()
                members = result["members"]
                if result["page_errors"]:
                    error = result["page_errors"][0]
                    saved_count = 0
                    failed_items.append({
                        "concept": concept,
                        "error": f"stopped at page {error['page']}: {error['error']}",
                    })
                elif args.dry_run:
                    saved_count = 0
                else:
                    saved_count = save_members_for_concept(concept, members)
                total_members += len(members)
                if not result["page_errors"]:
                    success_count += 1
                log(
                    f"[{index}/{len(concepts)}] "
                    f"{concept['concept_code']} {concept['concept_name']}: "
                    f"pages={result['fetched_pages']}/{result['total_pages']}, "
                    f"members={len(members)}, saved={saved_count}"
                )
                if result["page_errors"]:
                    error = result["page_errors"][0]
                    log(
                        f"  stopped at page {error['page']}: {error['error']} "
                        "(not saved)"
                    )
            except Exception as exc:
                failed_items.append({"concept": concept, "error": str(exc)})
                log(
                    f"[{index}/{len(concepts)}] "
                    f"{concept['concept_code']} {concept['concept_name']}: failed: {exc}"
                )

    print_summary(len(concepts), saved_concepts, success_count, failed_items, total_members)

    if not args.dry_run:
        sample_rows = get_sample_rows()
        if sample_rows:
            print("Sample current stock-concept rows:")
            for row in sample_rows:
                print(
                    f"  {row['concept_name']}({row['concept_code']}) | "
                    f"{row['ts_code']} {row['stock_name'] or ''} | "
                    f"pct_chg={row['pct_chg'] if row['pct_chg'] is not None else '--'} | "
                    f"turnover={row['turnover_rate'] if row['turnover_rate'] is not None else '--'}"
                )

    if failed_items:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
