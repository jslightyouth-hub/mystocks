import { useEffect, useMemo, useState } from "react";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";
const RANK_PAGE_SIZE = 50;
const TOTAL_RANK_PAGES = 5;
const AUTH_TOKEN_KEY = "auth_token";
const AUTH_USER_KEY = "auth_user";

const RANKING_CONFIG = {
  "top-movers": {
    endpoint: "/stocks/top-movers",
    title: "涨幅榜",
    ariaLabel: "前一交易日涨幅榜",
    errorText: "获取涨幅榜失败",
  },
  "bottom-movers": {
    endpoint: "/stocks/bottom-movers",
    title: "跌幅榜",
    ariaLabel: "前一交易日跌幅榜",
    errorText: "获取跌幅榜失败",
  },
};

const RESEARCH_STATUS_OPTIONS = [
  { value: "focus", label: "重点关注" },
  { value: "portfolio", label: "持仓" },
  { value: "buy_watch", label: "待买入" },
  { value: "watchlist", label: "观察池" },
  { value: "risk", label: "风险警示" },
  { value: "archive", label: "已淘汰" },
];

const RESEARCH_PRIORITY_OPTIONS = [
  { value: "high", label: "高" },
  { value: "medium", label: "中" },
  { value: "low", label: "低" },
];

const RESEARCH_LOG_TYPE_OPTIONS = ["新增研究", "上调评级", "下调评级", "风险提醒", "复盘"];
const INDUSTRY_TAG_CATEGORIES = [
  { value: "", label: "全部标签" },
  { value: "position", label: "行业地位" },
  { value: "growth", label: "成长性" },
  { value: "profitability", label: "盈利能力" },
  { value: "quality", label: "财务质量" },
  { value: "risk", label: "风险" },
];

const RESEARCH_STATUS_LABELS = Object.fromEntries(
  RESEARCH_STATUS_OPTIONS.map((option) => [option.value, option.label]),
);

const RESEARCH_PRIORITY_LABELS = Object.fromEntries(
  RESEARCH_PRIORITY_OPTIONS.map((option) => [option.value, option.label]),
);

function getPathFromLocation() {
  return decodeURIComponent(window.location.pathname.replace(/^\/+/, "").trim());
}

function getPageFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const page = Number(params.get("page"));

  if (!Number.isInteger(page)) {
    return 1;
  }

  return Math.min(Math.max(page, 1), TOTAL_RANK_PAGES);
}

function getPositivePageFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const page = Number(params.get("page"));

  if (!Number.isInteger(page)) {
    return 1;
  }

  return Math.max(page, 1);
}

function getQueryParamFromLocation(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name) || "";
}

function updatePageInUrl(page) {
  const url = new URL(window.location.href);

  if (page === 1) {
    url.searchParams.delete("page");
  } else {
    url.searchParams.set("page", String(page));
  }

  window.history.replaceState(null, "", url);
}

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return Number(value).toFixed(digits);
}

function formatSigned(value, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  const number = Number(value);
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toFixed(2)}${suffix}`;
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return `${Number(value).toFixed(2)}%`;
}

function formatTradeDate(value) {
  if (!value || value.length !== 8) {
    return "--";
  }

  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6)}`;
}

function formatDateTime(value) {
  if (!value) {
    return "--";
  }

  return String(value).replace("T", " ").slice(0, 19);
}

function formatResearchStatus(value) {
  return RESEARCH_STATUS_LABELS[value] || value || "--";
}

function formatResearchPriority(value) {
  return RESEARCH_PRIORITY_LABELS[value] || value || "--";
}

function normalizeTagInput(value) {
  return (value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item, index, list) => list.findIndex((current) => current.toLowerCase() === item.toLowerCase()) === index);
}

function formatWatchlistAmount(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return `${formatNumber(Number(value) / 100000)} 亿元`;
}

function getWatchlistSortValue(item, sortKey) {
  if (sortKey === "change_percent") {
    return Number(item.change_percent);
  }

  if (sortKey === "price") {
    return Number(item.price);
  }

  if (sortKey === "amount") {
    return Number(item.amount);
  }

  return 0;
}

function formatCompactNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  const number = Number(value);
  const abs = Math.abs(number);

  if (abs >= 100000000) {
    return `${(number / 100000000).toFixed(digits)} 亿`;
  }

  if (abs >= 10000) {
    return `${(number / 10000).toFixed(digits)} 万`;
  }

  return number.toFixed(digits);
}

function formatWanShare(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  const number = Number(value);
  if (Math.abs(number) >= 10000) {
    return `${(number / 10000).toFixed(2)} 亿股`;
  }

  return `${number.toFixed(2)} 万股`;
}

function formatWanYuan(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  const number = Number(value);
  if (Math.abs(number) >= 10000) {
    return `${(number / 10000).toFixed(2)} 亿元`;
  }

  return `${number.toFixed(2)} 万元`;
}

function formatRatio(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return `${Number(value).toFixed(2)}x`;
}

function formatRatioPercentInteger(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return `${Math.round(Number(value) * 100)}%`;
}

function isNumericValue(value) {
  return value !== null && value !== undefined && Number.isFinite(Number(value));
}

function formatYuanToYi(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return `${(Number(value) / 100000000).toFixed(2)} 亿元`;
}

function fetchJson(path, errorText) {
  return fetch(`${API_BASE}${path}`).then((res) => {
    if (!res.ok) {
      throw new Error(errorText);
    }
    return res.json();
  });
}

function fetchOptionalJson(path) {
  return fetch(`${API_BASE}${path}`).then((res) => {
    if (!res.ok) {
      return null;
    }
    return res.json();
  });
}

function readStoredUser() {
  try {
    const raw = window.localStorage.getItem(AUTH_USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function persistAuth(token, user) {
  if (token) {
    window.localStorage.setItem(AUTH_TOKEN_KEY, token);
  } else {
    window.localStorage.removeItem(AUTH_TOKEN_KEY);
  }

  if (user) {
    window.localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
  } else {
    window.localStorage.removeItem(AUTH_USER_KEY);
  }
}

function apiRequest(path, { token, method = "GET", body } = {}) {
  const headers = {};
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  return fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then(async (res) => {
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(payload.detail || "请求失败");
    }
    return payload;
  });
}

function getTrendClass(change) {
  const number = Number(change);

  if (number > 0) {
    return "is-up";
  }

  if (number < 0) {
    return "is-down";
  }

  return "";
}

function sortMoverItems(items, sortKey, sortDirection) {
  const direction = sortDirection === "asc" ? 1 : -1;

  return [...(items || [])].sort((left, right) => {
    if (sortKey === "up_down") {
      const leftUp = Number(left.up_count) || 0;
      const rightUp = Number(right.up_count) || 0;
      const leftDown = Number(left.down_count) || 0;
      const rightDown = Number(right.down_count) || 0;

      if (leftUp !== rightUp) {
        return (leftUp - rightUp) * direction;
      }

      return (rightDown - leftDown) * direction;
    }

    const leftNumber = Number(left[sortKey]);
    const rightNumber = Number(right[sortKey]);
    const leftValid = isNumericValue(left[sortKey]);
    const rightValid = isNumericValue(right[sortKey]);

    if (!leftValid && !rightValid) {
      return 0;
    }

    if (!leftValid) {
      return 1;
    }

    if (!rightValid) {
      return -1;
    }

    return (leftNumber - rightNumber) * direction;
  });
}

function getMoverAriaSort(activeSortKey, sortDirection, headerSortKey) {
  if (headerSortKey !== activeSortKey) {
    return "none";
  }

  return sortDirection === "asc" ? "ascending" : "descending";
}

function SortableHeaderButton({ activeSortKey, label, onSort, sortDirection, sortKey }) {
  return (
    <button
      type="button"
      className={`sortable-header ${activeSortKey === sortKey ? `is-active is-${sortDirection}` : ""}`}
      onClick={() => onSort(sortKey)}
    >
      {label}
    </button>
  );
}

function sortStockItems(items, sortKey, sortDirection) {
  if (!sortKey) {
    return [...(items || [])];
  }

  const direction = sortDirection === "asc" ? 1 : -1;

  return [...(items || [])].sort((left, right) => {
    const leftNumber = Number(left[sortKey]);
    const rightNumber = Number(right[sortKey]);
    const leftValid = Number.isFinite(leftNumber);
    const rightValid = Number.isFinite(rightNumber);

    if (!leftValid && !rightValid) {
      return 0;
    }

    if (!leftValid) {
      return 1;
    }

    if (!rightValid) {
      return -1;
    }

    return (leftNumber - rightNumber) * direction;
  });
}

function MarketNavDropdown() {
  const [open, setOpen] = useState(false);
  const menuItems = [
    { href: "/top-movers", label: "涨幅榜" },
    { href: "/bottom-movers", label: "跌幅榜" },
    { href: "/volume-movers", label: "成交量异动榜" },
    { href: "/industry-movers", label: "二级行业排行" },
    { href: "/industry-movers-l3", label: "三级行业排行" },
    { href: "/industry-tags", label: "三级行业财务标签" },
    { href: "/concept-movers", label: "概念排行" },
  ];

  return (
    <div
      className={`nav-dropdown ${open ? "is-open" : ""}`}
      onMouseLeave={() => setOpen(false)}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setOpen(false);
        }
      }}
    >
      <button
        type="button"
        className="nav-dropdown-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        市场行情
      </button>
      {open && (
        <div className="nav-dropdown-menu" role="menu">
          {menuItems.map((item) => (
            <a key={item.href} href={item.href} role="menuitem" onClick={() => setOpen(false)}>
              {item.label}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function AppNav() {
  return (
    <nav className="home-nav" aria-label="页面导航">
      <a className="nav-brand" href="/">
        股票行情
      </a>
      <div className="nav-links">
        <a href="/admin">管理</a>
        <MarketNavDropdown />
      </div>
    </nav>
  );
}

function AdminPage() {
  const [scriptStatus, setScriptStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [runningAction, setRunningAction] = useState(false);
  const [error, setError] = useState("");

  const loadStatus = () => {
    return fetchJson("/api/v1/admin/scripts/daily-market-update", "获取脚本状态失败")
      .then((payload) => {
        setScriptStatus(payload);
        setError("");
      })
      .catch((err) => {
        setError(err.message);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    loadStatus();
  }, []);

  useEffect(() => {
    if (!scriptStatus?.running) {
      return undefined;
    }

    const timer = window.setInterval(loadStatus, 3000);
    return () => window.clearInterval(timer);
  }, [scriptStatus?.running]);

  const runUpdate = () => {
    setRunningAction(true);
    setError("");

    fetch(`${API_BASE}/api/v1/admin/scripts/daily-market-update/run`, {
      method: "POST",
    })
      .then((res) => {
        if (!res.ok) {
          return res.json().catch(() => ({})).then((payload) => {
            throw new Error(payload.detail || "启动脚本失败");
          });
        }

        return res.json();
      })
      .then((payload) => {
        setScriptStatus(payload);
      })
      .catch((err) => {
        setError(err.message);
        loadStatus();
      })
      .finally(() => {
        setRunningAction(false);
      });
  };

  const statusLabel = {
    idle: "未运行",
    running: "运行中",
    success: "已完成",
    failed: "失败",
  }[scriptStatus?.status] || "未知";

  return (
    <main className="admin-page">
      <section className="admin-shell" aria-label="系统管理">
        <header className="admin-header">
          <div>
            <p className="eyebrow">系统管理</p>
            <h1>更新脚本</h1>
            <p className="admin-subtitle">在网页上启动每日行情数据更新，并查看最近运行日志。</p>
          </div>
          <a className="industry-action-link" href="/">
            返回首页
          </a>
        </header>

        <section className="admin-script-panel" aria-label="每日行情数据更新">
          <div className="admin-script-main">
            <div>
              <h2>{scriptStatus?.title || "每日行情数据更新"}</h2>
              <p>运行 update_all_market_data.py，更新股票、行业、日行情、盘前数据、融资融券和量能指标。</p>
            </div>
            <button
              type="button"
              className="admin-run-button"
              disabled={loading || runningAction || scriptStatus?.running}
              onClick={runUpdate}
            >
              {scriptStatus?.running ? "运行中..." : runningAction ? "启动中..." : "开始更新"}
            </button>
          </div>

          {error && <p className="admin-error">{error}</p>}

          <dl className="admin-status-grid">
            <div>
              <dt>状态</dt>
              <dd className={`admin-status admin-status-${scriptStatus?.status || "idle"}`}>
                {statusLabel}
              </dd>
            </div>
            <div>
              <dt>PID</dt>
              <dd>{scriptStatus?.pid || "--"}</dd>
            </div>
            <div>
              <dt>开始时间</dt>
              <dd>{formatDateTime(scriptStatus?.started_at)}</dd>
            </div>
            <div>
              <dt>结束时间</dt>
              <dd>{formatDateTime(scriptStatus?.finished_at)}</dd>
            </div>
            <div>
              <dt>返回码</dt>
              <dd>{scriptStatus?.return_code ?? "--"}</dd>
            </div>
          </dl>

          <div className="admin-log-block">
            <div className="admin-log-header">
              <h2>最近日志</h2>
              <button type="button" className="admin-refresh-button" onClick={loadStatus}>
                刷新
              </button>
            </div>
            <pre>{scriptStatus?.log || "暂无日志"}</pre>
          </div>
        </section>
      </section>
    </main>
  );
}

function Pagination({ page, totalPages, onPageChange }) {
  const pages = [];
  const maxPage = Math.max(1, totalPages);
  const addPage = (pageNumber) => {
    if (pageNumber >= 1 && pageNumber <= maxPage && !pages.includes(pageNumber)) {
      pages.push(pageNumber);
    }
  };

  addPage(1);
  for (let pageNumber = page - 2; pageNumber <= page + 2; pageNumber += 1) {
    addPage(pageNumber);
  }
  addPage(maxPage);
  pages.sort((left, right) => left - right);

  return (
    <nav className="pager" aria-label="榜单分页">
      <button
        type="button"
        className="pager-button"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        上一页
      </button>
      <div className="pager-pages">
        {pages.map((pageNumber, index) => (
          <span className="pager-item" key={pageNumber}>
            {index > 0 && pageNumber - pages[index - 1] > 1 && (
              <span className="pager-ellipsis">...</span>
            )}
            <button
              type="button"
              className={`pager-page ${pageNumber === page ? "is-active" : ""}`}
              aria-current={pageNumber === page ? "page" : undefined}
              onClick={() => onPageChange(pageNumber)}
            >
              {pageNumber}
            </button>
          </span>
        ))}
      </div>
      <button
        type="button"
        className="pager-button"
        disabled={page >= maxPage}
        onClick={() => onPageChange(page + 1)}
      >
        下一页
      </button>
    </nav>
  );
}

function MoversPage({ config, watchlistStateMap, onWatchClick }) {
  const [page, setPage] = useState(getPageFromLocation);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    updatePageInUrl(page);

    fetch(`${API_BASE}${config.endpoint}?page=${page}&page_size=${RANK_PAGE_SIZE}`)
      .then((res) => {
        if (!res.ok) {
          throw new Error(config.errorText);
        }
        return res.json();
      })
      .then((payload) => {
        setData(payload);
      })
      .catch((err) => {
        setError(err.message);
      });
  }, [config, page]);

  const totalPages = data?.total_pages || TOTAL_RANK_PAGES;
  const startRank = (page - 1) * RANK_PAGE_SIZE;

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!data) {
    return <main className="market-page status">加载中...</main>;
  }

  return (
    <main className="market-page">
      <section className="market-shell" aria-label={config.ariaLabel}>
        <header className="market-header">
          <div>
            <p className="eyebrow">前一交易日</p>
            <h1>
              {config.title}
              <span>第 {page} 页</span>
            </h1>
            <p className="market-subtitle">
              数据日期：{formatTradeDate(data.trade_date)}
            </p>
          </div>
          <div className="trade-date">
            <span>交易日期</span>
            <strong>{formatTradeDate(data.trade_date)}</strong>
          </div>
        </header>

        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />

        <div className="market-table-wrap">
          <table className="market-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>股票</th>
                <th>二级行业</th>
                <th>收盘价</th>
                <th>涨跌额</th>
                <th>涨跌幅</th>
                <th>换手率</th>
                <th>成交量</th>
                <th>成交额</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((stock, index) => {
                const trendClass = getTrendClass(stock.pct_chg);

                return (
                  <tr key={stock.ts_code}>
                    <td data-label="排名">
                      <span className="rank">{startRank + index + 1}</span>
                    </td>
                    <td data-label="股票">
                      <StockLinkCell stock={stock} watchlistState={watchlistStateMap[stock.ts_code]} onWatchClick={onWatchClick} />
                    </td>
                    <td className="industry-cell" data-label="二级行业">
                      {stock.sw_l2_name || stock.industry || "--"}
                    </td>
                    <td data-label="收盘价">{formatNumber(stock.close)}</td>
                    <td data-label="涨跌额" className={trendClass}>
                      {formatSigned(stock.change)}
                    </td>
                    <td data-label="涨跌幅" className={trendClass}>
                      {formatSigned(stock.pct_chg, "%")}
                    </td>
                    <td data-label="换手率">{formatPercent(stock.turnover_rate)}</td>
                    <td data-label="成交量">{formatNumber(stock.vol / 10000)} 万手</td>
                    <td data-label="成交额">{formatNumber(stock.amount / 100000)} 亿元</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
      </section>
    </main>
  );
}

function VolumeMoversPage({ watchlistStateMap, onWatchClick }) {
  const [page, setPage] = useState(getPositivePageFromLocation);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    updatePageInUrl(page);

    fetch(`${API_BASE}/stocks/volume-movers?page=${page}&page_size=50`)
      .then((res) => {
        if (!res.ok) {
          throw new Error("获取成交量异动榜失败");
        }
        return res.json();
      })
      .then((payload) => {
        setData(payload);
      })
      .catch((err) => {
        setError(err.message);
      });
  }, [page]);

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!data) {
    return <main className="market-page status">加载中...</main>;
  }

  const totalPages = data.total_pages || 1;
  const startRank = (page - 1) * data.page_size;

  return (
    <main className="market-page">
      <section className="market-shell volume-movers-shell" aria-label="成交量异动榜">
        <header className="market-header">
          <div>
            <p className="eyebrow">量价异动</p>
            <h1>
              成交量异动榜
              <span>第 {page} 页</span>
            </h1>
            <p className="market-subtitle">
              数据日期：{formatTradeDate(data.trade_date)}；按 20 日量比降序排列。
            </p>
          </div>
          <div className="trade-date">
            <span>交易日期</span>
            <strong>{formatTradeDate(data.trade_date)}</strong>
          </div>
        </header>

        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />

        <div className="market-table-wrap">
          <table className="market-table volume-movers-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>股票</th>
                <th>二级行业</th>
                <th>收盘价</th>
                <th>涨跌幅</th>
                <th>5日量比</th>
                <th>20日量比</th>
                <th>20日额比</th>
                <th>异动标签</th>
                <th>成交额</th>
                <th>换手率</th>
                <th>总市值</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((stock, index) => {
                const trendClass = getTrendClass(stock.pct_chg);

                return (
                  <tr key={stock.ts_code}>
                    <td data-label="排名">
                      <span className="rank">{startRank + index + 1}</span>
                    </td>
                    <td data-label="股票">
                      <StockLinkCell stock={stock} watchlistState={watchlistStateMap[stock.ts_code]} onWatchClick={onWatchClick} />
                    </td>
                    <td className="industry-cell" data-label="二级行业">
                      {stock.sw_l2_name || stock.industry || "--"}
                    </td>
                    <td data-label="收盘价">{formatNumber(stock.close)}</td>
                    <td data-label="涨跌幅" className={trendClass}>
                      {formatSigned(stock.pct_chg, "%")}
                    </td>
                    <td data-label="5日量比">{formatRatio(stock.vol_ratio_5)}</td>
                    <td data-label="20日量比">{formatRatio(stock.vol_ratio_20)}</td>
                    <td data-label="20日额比">{formatRatio(stock.amount_ratio_20)}</td>
                    <td data-label="异动标签">
                      <span className="volume-signal">{stock.volume_signal || "--"}</span>
                    </td>
                    <td data-label="成交额">{formatNumber(stock.amount / 100000)} 亿元</td>
                    <td data-label="换手率">{formatPercent(stock.turnover_rate)}</td>
                    <td data-label="总市值">{formatNumber(stock.market_value / 10000)} 亿元</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
      </section>
    </main>
  );
}

function IndustryMoversPage({
  endpoint = "/api/v1/industries/l2/movers",
  detailBasePath = "/industry/l2",
  levelLabel = "二级行业",
}) {
  const [excludeHigh, setExcludeHigh] = useState(0);
  const [excludeLow, setExcludeLow] = useState(0);
  const [sortKey, setSortKey] = useState("avg_pct_chg");
  const [sortDirection, setSortDirection] = useState("desc");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}${endpoint}?exclude_high=${excludeHigh}&exclude_low=${excludeLow}`)
      .then((res) => {
        if (!res.ok) {
          throw new Error("获取行业排行失败");
        }
        return res.json();
      })
      .then((payload) => {
        setData(payload);
      })
      .catch((err) => {
        setError(err.message);
      });
  }, [endpoint, excludeHigh, excludeLow]);

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!data) {
    return <main className="market-page status">加载中...</main>;
  }

  const sortedItems = sortMoverItems(data.items, sortKey, sortDirection);

  const handleSort = (nextSortKey) => {
    if (nextSortKey === sortKey) {
      setSortDirection((currentDirection) => (currentDirection === "desc" ? "asc" : "desc"));
      return;
    }

    setSortKey(nextSortKey);
    setSortDirection("desc");
  };

  return (
    <main className="market-page">
      <section className="market-shell industry-shell" aria-label={`${levelLabel}涨跌排行`}>
        <header className="market-header">
          <div>
            <p className="eyebrow">{levelLabel}</p>
            <h1>{levelLabel}涨跌排行</h1>
            <p className="market-subtitle">
              数据日期：{formatTradeDate(data.trade_date)}；按{levelLabel}计算平均涨跌幅。
            </p>
          </div>
          <div className="trade-date">
            <span>交易日期</span>
            <strong>{formatTradeDate(data.trade_date)}</strong>
          </div>
        </header>

        <div className="industry-controls" aria-label="行业排行计算参数">
          <label>
            剔除最高涨幅
            <select value={excludeHigh} onChange={(event) => setExcludeHigh(Number(event.target.value))}>
              {Array.from({ length: 6 }, (_, value) => (
                <option key={value} value={value}>
                  {value} 只
                </option>
              ))}
            </select>
          </label>
          <label>
            剔除最高跌幅
            <select value={excludeLow} onChange={(event) => setExcludeLow(Number(event.target.value))}>
              {Array.from({ length: 6 }, (_, value) => (
                <option key={value} value={value}>
                  {value} 只
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="market-table-wrap">
          <table className="market-table industry-rank-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>{levelLabel}</th>
                <th aria-sort={getMoverAriaSort(sortKey, sortDirection, "avg_pct_chg")}>
                  <SortableHeaderButton
                    activeSortKey={sortKey}
                    label="平均涨跌幅"
                    onSort={handleSort}
                    sortDirection={sortDirection}
                    sortKey="avg_pct_chg"
                  />
                </th>
                <th aria-sort={getMoverAriaSort(sortKey, sortDirection, "up_down")}>
                  <SortableHeaderButton
                    activeSortKey={sortKey}
                    label="上涨/下跌"
                    onSort={handleSort}
                    sortDirection={sortDirection}
                    sortKey="up_down"
                  />
                </th>
                <th aria-sort={getMoverAriaSort(sortKey, sortDirection, "vol_ratio_20")}>
                  <SortableHeaderButton
                    activeSortKey={sortKey}
                    label="20日量比"
                    onSort={handleSort}
                    sortDirection={sortDirection}
                    sortKey="vol_ratio_20"
                  />
                </th>
                <th aria-sort={getMoverAriaSort(sortKey, sortDirection, "vol_ratio_5")}>
                  <SortableHeaderButton
                    activeSortKey={sortKey}
                    label="5日量比"
                    onSort={handleSort}
                    sortDirection={sortDirection}
                    sortKey="vol_ratio_5"
                  />
                </th>
                <th aria-sort={getMoverAriaSort(sortKey, sortDirection, "amount_ratio_20")}>
                  <SortableHeaderButton
                    activeSortKey={sortKey}
                    label="20日额比"
                    onSort={handleSort}
                    sortDirection={sortDirection}
                    sortKey="amount_ratio_20"
                  />
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((industry, index) => {
                const trendClass = getTrendClass(industry.avg_pct_chg);

                return (
                  <tr key={industry.industry_code}>
                    <td data-label="排名">
                      <span className="rank">{index + 1}</span>
                    </td>
                    <td data-label={levelLabel} className="industry-name-cell">
                      <a href={`${detailBasePath}/${encodeURIComponent(industry.industry_code)}`}>
                        {industry.industry_name}
                      </a>
                    </td>
                    <td data-label="平均涨跌幅" className={trendClass}>
                      {formatSigned(industry.avg_pct_chg, "%")}
                    </td>
                    <td data-label="上涨/下跌">
                      <UpDownRatioBar upCount={industry.up_count} downCount={industry.down_count} />
                    </td>
                    <td data-label="20日量比">{formatRatio(industry.vol_ratio_20)}</td>
                    <td data-label="5日量比">{formatRatio(industry.vol_ratio_5)}</td>
                    <td data-label="20日额比">{formatRatio(industry.amount_ratio_20)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function UpDownRatioBar({ upCount, downCount }) {
  const up = Number(upCount) || 0;
  const down = Number(downCount) || 0;
  const total = up + down;

  if (!total) {
    return <span className="up-down-ratio-empty">--</span>;
  }

  const upWidth = `${(up / total) * 100}%`;
  const downWidth = `${(down / total) * 100}%`;

  return (
    <div className="up-down-ratio" aria-label={`上涨 ${up}，下跌 ${down}`}>
      <div className="up-down-ratio-track" aria-hidden="true">
        <span className="up-down-ratio-up" style={{ width: upWidth }} />
        <span className="up-down-ratio-down" style={{ width: downWidth }} />
      </div>
      <span className="up-down-ratio-label">
        {up}/{down}
      </span>
    </div>
  );
}

function ConceptMoversPage() {
  const [sortKey, setSortKey] = useState("avg_pct_chg");
  const [sortDirection, setSortDirection] = useState("desc");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/concepts/movers`)
      .then((res) => {
        if (!res.ok) {
          throw new Error("获取概念排行失败");
        }
        return res.json();
      })
      .then((payload) => {
        setData(payload);
      })
      .catch((err) => {
        setError(err.message);
      });
  }, []);

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!data) {
    return <main className="market-page status">加载中...</main>;
  }

  const sortedItems = sortMoverItems(data.items, sortKey, sortDirection);

  const handleSort = (nextSortKey) => {
    if (nextSortKey === sortKey) {
      setSortDirection((currentDirection) => (currentDirection === "desc" ? "asc" : "desc"));
      return;
    }

    setSortKey(nextSortKey);
    setSortDirection("desc");
  };

  return (
    <main className="market-page">
      <section className="market-shell industry-shell" aria-label="概念涨跌幅排行">
        <header className="market-header">
          <div>
            <p className="eyebrow">同花顺概念</p>
            <h1>概念涨跌幅排行</h1>
            <p className="market-subtitle">
              数据日期：{formatTradeDate(data.trade_date)}；按概念成分股最新交易日平均涨跌幅排序。
            </p>
          </div>
          <div className="trade-date">
            <span>交易日期</span>
            <strong>{formatTradeDate(data.trade_date)}</strong>
          </div>
        </header>

        <div className="market-table-wrap">
          <table className="market-table concept-rank-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>概念</th>
                <th aria-sort={getMoverAriaSort(sortKey, sortDirection, "avg_pct_chg")}>
                  <SortableHeaderButton
                    activeSortKey={sortKey}
                    label="平均涨跌幅"
                    onSort={handleSort}
                    sortDirection={sortDirection}
                    sortKey="avg_pct_chg"
                  />
                </th>
                <th aria-sort={getMoverAriaSort(sortKey, sortDirection, "up_down")}>
                  <SortableHeaderButton
                    activeSortKey={sortKey}
                    label="上涨/下跌"
                    onSort={handleSort}
                    sortDirection={sortDirection}
                    sortKey="up_down"
                  />
                </th>
                <th>成分股数</th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((concept, index) => {
                const trendClass = getTrendClass(concept.avg_pct_chg);

                return (
                  <tr key={concept.concept_code}>
                    <td data-label="排名">
                      <span className="rank">{index + 1}</span>
                    </td>
                    <td data-label="概念" className="industry-name-cell">
                      <a href={`/concept/${encodeURIComponent(concept.concept_code)}`}>
                        {concept.concept_name}
                      </a>
                    </td>
                    <td data-label="平均涨跌幅" className={trendClass}>
                      {formatSigned(concept.avg_pct_chg, "%")}
                    </td>
                    <td data-label="上涨/下跌">
                      <UpDownRatioBar upCount={concept.up_count} downCount={concept.down_count} />
                    </td>
                    <td data-label="成分股数">{concept.stock_count}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function ConceptOverviewPage({ conceptCode, watchlistStateMap, onWatchClick }) {
  const [page, setPage] = useState(getPositivePageFromLocation);
  const [sortKey, setSortKey] = useState("");
  const [sortDirection, setSortDirection] = useState("desc");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    updatePageInUrl(page);

    fetch(`${API_BASE}/api/v1/concepts/${encodeURIComponent(conceptCode)}/stocks?page=${page}&page_size=50`)
      .then((res) => {
        if (!res.ok) {
          throw new Error("获取概念成分股失败");
        }
        return res.json();
      })
      .then((payload) => {
        setData(payload);
      })
      .catch((err) => {
        setError(err.message);
      });
  }, [conceptCode, page]);

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!data) {
    return <main className="market-page status">加载中...</main>;
  }

  const totalPages = data.total_pages || 1;
  const startRank = (page - 1) * data.page_size;
  const sortedItems = sortStockItems(data.items, sortKey, sortDirection);

  const handleSort = (nextSortKey) => {
    if (nextSortKey === sortKey) {
      setSortDirection((currentDirection) => (currentDirection === "desc" ? "asc" : "desc"));
      return;
    }

    setSortKey(nextSortKey);
    setSortDirection("desc");
  };

  return (
    <main className="market-page">
      <section className="market-shell industry-shell" aria-label={`${data.concept_name} 概念成分股`}>
        <header className="market-header industry-detail-header">
          <div>
            <p className="eyebrow">概念成分股</p>
            <h1>{data.concept_name}</h1>
            <p className="market-subtitle">
              数据日期：{formatTradeDate(data.trade_date)}；成分股数：{data.total}；第 {page} / {totalPages} 页。
            </p>
          </div>
          <div className="concept-actions">
            <a className="industry-action-link" href={`/concept/${encodeURIComponent(conceptCode)}/movers`}>
              查看涨跌前后 10
            </a>
            <a className="industry-action-link" href="/concept-movers">
              返回概念排行
            </a>
          </div>
        </header>

        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />

        <div className="market-table-wrap">
          <table className="market-table concept-stock-table">
            <thead>
              <tr>
                <th>序号</th>
                <th>股票</th>
                <th>行业</th>
                <th aria-sort={getMoverAriaSort(sortKey, sortDirection, "close")}>
                  <SortableHeaderButton
                    activeSortKey={sortKey}
                    label="收盘价"
                    onSort={handleSort}
                    sortDirection={sortDirection}
                    sortKey="close"
                  />
                </th>
                <th aria-sort={getMoverAriaSort(sortKey, sortDirection, "change")}>
                  <SortableHeaderButton
                    activeSortKey={sortKey}
                    label="涨跌额"
                    onSort={handleSort}
                    sortDirection={sortDirection}
                    sortKey="change"
                  />
                </th>
                <th aria-sort={getMoverAriaSort(sortKey, sortDirection, "pct_chg")}>
                  <SortableHeaderButton
                    activeSortKey={sortKey}
                    label="涨跌幅"
                    onSort={handleSort}
                    sortDirection={sortDirection}
                    sortKey="pct_chg"
                  />
                </th>
                <th aria-sort={getMoverAriaSort(sortKey, sortDirection, "turnover_rate")}>
                  <SortableHeaderButton
                    activeSortKey={sortKey}
                    label="换手率"
                    onSort={handleSort}
                    sortDirection={sortDirection}
                    sortKey="turnover_rate"
                  />
                </th>
                <th aria-sort={getMoverAriaSort(sortKey, sortDirection, "vol_ratio_20")}>
                  <SortableHeaderButton
                    activeSortKey={sortKey}
                    label="20日量比"
                    onSort={handleSort}
                    sortDirection={sortDirection}
                    sortKey="vol_ratio_20"
                  />
                </th>
                <th aria-sort={getMoverAriaSort(sortKey, sortDirection, "amount")}>
                  <SortableHeaderButton
                    activeSortKey={sortKey}
                    label="成交额"
                    onSort={handleSort}
                    sortDirection={sortDirection}
                    sortKey="amount"
                  />
                </th>
                <th aria-sort={getMoverAriaSort(sortKey, sortDirection, "market_value")}>
                  <SortableHeaderButton
                    activeSortKey={sortKey}
                    label="总市值"
                    onSort={handleSort}
                    sortDirection={sortDirection}
                    sortKey="market_value"
                  />
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((stock, index) => {
                const trendClass = getTrendClass(stock.pct_chg);
                const volumeRatioNumber = Number(stock.vol_ratio_20);
                const hasVolumeRatio = isNumericValue(stock.vol_ratio_20);
                const volumeRatioTrendClass = hasVolumeRatio ? getTrendClass(volumeRatioNumber - 1) : "";
                const volumeRatioDisplay = hasVolumeRatio ? (
                  <span className="stock-volume-ratio concept-volume-ratio">
                    <strong className={volumeRatioTrendClass}>{formatRatioPercentInteger(stock.vol_ratio_20)}</strong>
                    {stock.volume_signal && <em>{stock.volume_signal}</em>}
                  </span>
                ) : "--";

                return (
                  <tr key={stock.ts_code}>
                    <td data-label="序号">
                      <span className="rank">{startRank + index + 1}</span>
                    </td>
                    <td data-label="股票">
                      <StockLinkCell stock={stock} watchlistState={watchlistStateMap[stock.ts_code]} onWatchClick={onWatchClick} />
                    </td>
                    <td className="industry-cell" data-label="行业">
                      {stock.sw_l2_name || stock.industry || "--"}
                    </td>
                    <td data-label="收盘价">{formatNumber(stock.close)}</td>
                    <td data-label="涨跌额" className={trendClass}>
                      {formatSigned(stock.change)}
                    </td>
                    <td data-label="涨跌幅" className={trendClass}>
                      {formatSigned(stock.pct_chg, "%")}
                    </td>
                    <td data-label="换手率">{formatPercent(stock.turnover_rate)}</td>
                    <td data-label="20日量比">{volumeRatioDisplay}</td>
                    <td data-label="成交额">{formatNumber(stock.amount / 100000)} 亿元</td>
                    <td data-label="总市值">{formatNumber(stock.market_value / 10000)} 亿元</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
      </section>
    </main>
  );
}

function ConceptMoversDetailPage({ conceptCode, watchlistStateMap, onWatchClick }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const endpoint = `/api/v1/concepts/${encodeURIComponent(conceptCode)}/movers?page=1&page_size=10`;

    Promise.all([
      fetch(`${API_BASE}${endpoint}&direction=top`).then((res) => {
        if (!res.ok) {
          throw new Error("获取概念涨幅榜失败");
        }
        return res.json();
      }),
      fetch(`${API_BASE}${endpoint}&direction=bottom`).then((res) => {
        if (!res.ok) {
          throw new Error("获取概念跌幅榜失败");
        }
        return res.json();
      }),
    ])
      .then(([topPayload, bottomPayload]) => {
        setData({
          ...topPayload,
          top_items: topPayload.items || [],
          bottom_items: bottomPayload.items || [],
        });
      })
      .catch((err) => {
        setError(err.message);
      });
  }, [conceptCode]);

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!data) {
    return <main className="market-page status">加载中...</main>;
  }

  return (
    <main className="market-page">
      <section className="market-shell industry-shell" aria-label={`${data.concept_name} 概念成分股排行`}>
        <header className="market-header industry-detail-header">
          <div>
            <p className="eyebrow">概念涨幅榜</p>
            <h1>{data.concept_name}</h1>
            <p className="market-subtitle">
              数据日期：{formatTradeDate(data.trade_date)}；成分股数：{data.total}；左侧涨幅前 10，右侧跌幅前 10。
            </p>
          </div>
          <a className="industry-action-link" href="/concept-movers">
            返回概念排行
          </a>
        </header>

        <div className="industry-stock-grid concept-stock-grid">
          <IndustryStockTable title="涨幅前 10" stocks={data.top_items || []} watchlistStateMap={watchlistStateMap} onWatchClick={onWatchClick} />
          <IndustryStockTable title="跌幅前 10" stocks={data.bottom_items || []} watchlistStateMap={watchlistStateMap} onWatchClick={onWatchClick} />
        </div>
      </section>
    </main>
  );
}

function IndustryOverviewPage({
  industryCode,
  level = "l2",
  levelLabel = "二级行业",
}) {
  const endpointBase = `/api/v1/industries/${level}/${encodeURIComponent(industryCode)}`;
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const requests = [
      fetchJson(endpointBase, "获取行业信息失败"),
      fetchOptionalJson(`${endpointBase}/market`),
      fetchOptionalJson(`${endpointBase}/financials/summary`),
    ];

    if (level === "l2") {
      requests.push(fetchOptionalJson(`${endpointBase}/children`));
    }

    Promise.all(requests)
      .then(([industry, market, financials, children]) => {
        setData({
          industry,
          market,
          financials,
          children: children?.items || [],
        });
      })
      .catch((err) => {
        setError(err.message);
      });
  }, [endpointBase, level]);

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!data) {
    return <main className="market-page status">加载中...</main>;
  }

  const { industry, market, financials, children } = data;
  const moversPath = `/industry/${level}/${encodeURIComponent(industryCode)}/movers`;
  const stocksPath = `/industry/${level}/${encodeURIComponent(industryCode)}/stocks`;
  const metrics = financials?.metrics || {};

  return (
    <main className="market-page">
      <section className="market-shell industry-shell" aria-label={`${industry.industry_name} 行业总览`}>
        <header className="market-header industry-detail-header">
          <div>
            <p className="eyebrow">{levelLabel}总览</p>
            <h1>{industry.industry_name}</h1>
            <p className="market-subtitle">
              行业代码：{industry.industry_code}；股票数：{industry.stock_count}；更新时间：{formatDateTime(industry.updated_at)}
            </p>
          </div>
          <div className="concept-actions">
            <a className="industry-action-link" href={moversPath}>
              查看涨跌榜
            </a>
            <a className="industry-action-link" href={stocksPath}>
              查看全部股票
            </a>
          </div>
        </header>

        <div className="industry-overview-grid">
          <section className="industry-panel" aria-label="行业信息">
            <h2>行业信息</h2>
            <dl className="industry-facts">
              <div>
                <dt>层级</dt>
                <dd>{level.toUpperCase()}</dd>
              </div>
              <div>
                <dt>来源</dt>
                <dd>{industry.source?.toUpperCase() || "--"}</dd>
              </div>
              <div>
                <dt>上级行业</dt>
                <dd>{industry.parent_name || "--"}</dd>
              </div>
              <div>
                <dt>子行业数</dt>
                <dd>{level !== "l3" ? industry.children_count : "--"}</dd>
              </div>
            </dl>
          </section>

          <section className="industry-panel" aria-label="行情聚合">
            <h2>行情聚合</h2>
            <dl className="industry-metrics">
              <div>
                <dt>平均涨跌幅</dt>
                <dd className={getTrendClass(market?.avg_pct_chg)}>
                  {formatSigned(market?.avg_pct_chg, "%")}
                </dd>
              </div>
              <div>
                <dt>上涨/下跌</dt>
                <dd>{market ? `${market.up_count}/${market.down_count}` : "--"}</dd>
              </div>
              <div>
                <dt>成交额</dt>
                <dd>{formatCompactNumber((market?.amount || 0) * 1000)}</dd>
              </div>
              <div>
                <dt>总市值</dt>
                <dd>{formatCompactNumber((market?.market_value || 0) * 10000)}</dd>
              </div>
              <div>
                <dt>平均换手率</dt>
                <dd>{formatPercent(market?.avg_turnover_rate)}</dd>
              </div>
              <div>
                <dt>交易日期</dt>
                <dd>{formatTradeDate(market?.trade_date)}</dd>
              </div>
              <div>
                <dt>20日量比</dt>
                <dd>{formatRatio(market?.vol_ratio_20)}</dd>
              </div>
              <div>
                <dt>5日量比</dt>
                <dd>{formatRatio(market?.vol_ratio_5)}</dd>
              </div>
              <div>
                <dt>20日额比</dt>
                <dd>{formatRatio(market?.amount_ratio_20)}</dd>
              </div>
              <div>
                <dt>放量/缩量</dt>
                <dd>
                  {market
                    ? `${(Number(market.extreme_volume_count) || 0) + (Number(market.strong_volume_count) || 0)}/${market.shrink_volume_count ?? 0}`
                    : "--"}
                </dd>
              </div>
            </dl>
          </section>

          <section className="industry-panel" aria-label="财务摘要">
            <h2>财务摘要</h2>
            <dl className="industry-metrics">
              <div>
                <dt>报告期</dt>
                <dd>{formatTradeDate(financials?.period)}</dd>
              </div>
              <div>
                <dt>统计股票数</dt>
                <dd>{financials?.stock_count ?? "--"}</dd>
              </div>
              <div>
                <dt>平均 ROE</dt>
                <dd>{formatPercent(metrics.avg_roe)}</dd>
              </div>
              <div>
                <dt>平均毛利率</dt>
                <dd>{formatPercent(metrics.avg_grossprofit_margin)}</dd>
              </div>
              <div>
                <dt>营业收入合计</dt>
                <dd>{formatCompactNumber(metrics.total_revenue)}</dd>
              </div>
              <div>
                <dt>归母净利润合计</dt>
                <dd>{formatCompactNumber(metrics.total_net_profit)}</dd>
              </div>
            </dl>
          </section>
        </div>

        {level === "l2" && (
          <section className="industry-panel industry-children-section" aria-label="三级子行业">
            <h2>三级子行业</h2>
            <div className="market-table-wrap">
              <table className="market-table industry-rank-table">
                <thead>
                  <tr>
                    <th>序号</th>
                    <th>三级行业</th>
                    <th>行业代码</th>
                    <th>股票数</th>
                  </tr>
                </thead>
                <tbody>
                  {children.map((child, index) => (
                    <tr key={child.industry_code}>
                      <td data-label="序号">
                        <span className="rank">{index + 1}</span>
                      </td>
                      <td data-label="三级行业" className="industry-name-cell">
                        <a href={`/industry/l3/${encodeURIComponent(child.industry_code)}`}>
                          {child.industry_name}
                        </a>
                      </td>
                      <td data-label="行业代码">{child.industry_code}</td>
                      <td data-label="股票数">{child.stock_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </section>
    </main>
  );
}

function IndustryStocksPage({
  industryCode,
  level = "l2",
  levelLabel = "二级行业",
  watchlistStateMap,
  onWatchClick,
}) {
  const [page, setPage] = useState(getPositivePageFromLocation);
  const [industry, setIndustry] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const endpointBase = `/api/v1/industries/${level}/${encodeURIComponent(industryCode)}`;

  useEffect(() => {
    updatePageInUrl(page);

    Promise.all([
      fetchJson(endpointBase, "获取行业信息失败"),
      fetchJson(`${endpointBase}/stocks?page=${page}&page_size=50`, "获取行业股票失败"),
    ])
      .then(([industryPayload, stocksPayload]) => {
        setIndustry(industryPayload);
        setData(stocksPayload);
      })
      .catch((err) => {
        setError(err.message);
      });
  }, [endpointBase, page]);

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!industry || !data) {
    return <main className="market-page status">加载中...</main>;
  }

  const pageSize = data.page_size || 50;
  const totalPages = Math.max(1, Math.ceil((data.total || 0) / pageSize));
  const startRank = (page - 1) * pageSize;

  return (
    <main className="market-page">
      <section className="market-shell industry-shell" aria-label={`${industry.industry_name} 行业全部股票`}>
        <header className="market-header industry-detail-header">
          <div>
            <p className="eyebrow">{levelLabel}全部股票</p>
            <h1>{industry.industry_name}</h1>
            <p className="market-subtitle">
              数据日期：{formatTradeDate(data.trade_date)}；行业股票数：{data.total}；第 {page} / {totalPages} 页。
            </p>
          </div>
          <div className="concept-actions">
            <a className="industry-action-link" href={`/industry/${level}/${encodeURIComponent(industryCode)}/movers`}>
              查看涨跌榜
            </a>
            <a className="industry-action-link" href={`/industry/${level}/${encodeURIComponent(industryCode)}`}>
              返回总览
            </a>
          </div>
        </header>

        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />

        <div className="market-table-wrap">
          <table className="market-table concept-stock-table">
            <thead>
              <tr>
                <th>序号</th>
                <th>股票</th>
                <th>行业</th>
                <th>收盘价</th>
                <th>涨跌额</th>
                <th>涨跌幅</th>
                <th>换手率</th>
                <th>20日量比</th>
                <th>成交额</th>
                <th>总市值</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((stock, index) => {
                const trendClass = getTrendClass(stock.pct_chg);
                const volumeRatioNumber = Number(stock.vol_ratio_20);
                const volumeRatioTrendClass = isNumericValue(stock.vol_ratio_20)
                  ? getTrendClass(volumeRatioNumber - 1)
                  : "";

                return (
                  <tr key={stock.ts_code}>
                    <td data-label="序号">
                      <span className="rank">{startRank + index + 1}</span>
                    </td>
                    <td data-label="股票">
                      <StockLinkCell stock={stock} watchlistState={watchlistStateMap[stock.ts_code]} onWatchClick={onWatchClick} />
                    </td>
                    <td className="industry-cell" data-label="行业">
                      {stock.industry_name || "--"}
                    </td>
                    <td data-label="收盘价">{formatNumber(stock.close)}</td>
                    <td data-label="涨跌额" className={trendClass}>
                      {formatSigned(stock.change)}
                    </td>
                    <td data-label="涨跌幅" className={trendClass}>
                      {formatSigned(stock.pct_chg, "%")}
                    </td>
                    <td data-label="换手率">{formatPercent(stock.turnover_rate)}</td>
                    <td data-label="20日量比" className={volumeRatioTrendClass}>
                      {formatRatioPercentInteger(stock.vol_ratio_20)}
                    </td>
                    <td data-label="成交额">{formatNumber(stock.amount / 100000)} 亿元</td>
                    <td data-label="总市值">{formatNumber(stock.market_value / 10000)} 亿元</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
      </section>
    </main>
  );
}

function IndustryMoversDetailPage({
  industryCode,
  level = "l2",
  levelLabel = "二级行业",
  watchlistStateMap,
  onWatchClick,
}) {
  const endpointBase = `/api/v1/industries/${level}/${encodeURIComponent(industryCode)}`;
  const [industry, setIndustry] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}${endpointBase}`).then((res) => {
        if (!res.ok) {
          throw new Error("获取行业信息失败");
        }
        return res.json();
      }),
      fetch(`${API_BASE}${endpointBase}/movers?limit=10`).then((res) => {
        if (!res.ok) {
          throw new Error("获取行业股票失败");
        }
        return res.json();
      }),
    ])
      .then(([industryPayload, moversPayload]) => {
        setIndustry(industryPayload);
        setData(moversPayload);
      })
      .catch((err) => {
        setError(err.message);
      });
  }, [endpointBase]);

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!industry || !data) {
    return <main className="market-page status">加载中...</main>;
  }

  return (
    <main className="market-page">
      <section className="market-shell industry-shell" aria-label={`${industry.industry_name} 行业股票`}>
        <header className="market-header industry-detail-header">
          <div>
            <p className="eyebrow">{levelLabel}涨跌榜</p>
            <h1>{industry.industry_name}</h1>
            <p className="market-subtitle">
              数据日期：{formatTradeDate(data.trade_date)}；行业股票数：{industry.stock_count}。
            </p>
          </div>
          <a className="industry-action-link" href={`/industry/${level}/${encodeURIComponent(industryCode)}`}>
            返回总览
          </a>
        </header>

        <div className="industry-stock-grid">
          <IndustryStockTable title="涨幅前 10" stocks={data.top_items || []} watchlistStateMap={watchlistStateMap} onWatchClick={onWatchClick} />
          <IndustryStockTable title="跌幅前 10" stocks={data.bottom_items || []} watchlistStateMap={watchlistStateMap} onWatchClick={onWatchClick} />
        </div>
      </section>
    </main>
  );
}

function IndustryStockTable({ title, stocks, watchlistStateMap, onWatchClick }) {
  return (
    <section className="industry-stock-section" aria-label={title}>
      <h2>{title}</h2>
      <div className="market-table-wrap compact-table-wrap">
        <table className="market-table industry-stock-table">
          <thead>
            <tr>
              <th>排名</th>
              <th>股票</th>
              <th>收盘价</th>
              <th>涨跌幅</th>
              <th>换手率</th>
              <th>20日量比</th>
              <th>总市值</th>
              <th>成交额</th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((stock, index) => {
              const trendClass = getTrendClass(stock.pct_chg);
              const volumeRatioNumber = Number(stock.vol_ratio_20);
              const volumeRatioTrendClass = isNumericValue(stock.vol_ratio_20)
                ? getTrendClass(volumeRatioNumber - 1)
                : "";

              return (
                <tr key={stock.ts_code}>
                  <td data-label="排名">
                    <span className="rank">{index + 1}</span>
                  </td>
                  <td data-label="股票">
                    <StockLinkCell stock={stock} watchlistState={watchlistStateMap[stock.ts_code]} onWatchClick={onWatchClick} />
                  </td>
                  <td data-label="收盘价">{formatNumber(stock.close)}</td>
                  <td data-label="涨跌幅" className={trendClass}>
                    {formatSigned(stock.pct_chg, "%")}
                  </td>
                  <td data-label="换手率">{formatPercent(stock.turnover_rate)}</td>
                  <td data-label="20日量比" className={volumeRatioTrendClass}>
                    {formatRatioPercentInteger(stock.vol_ratio_20)}
                  </td>
                  <td data-label="总市值">{formatNumber(stock.market_value / 10000)} 亿元</td>
                  <td data-label="成交额">{formatNumber(stock.amount / 100000)} 亿元</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PageNav({ authUser, onOpenAuth, onLogout }) {
  return (
    <nav className="home-nav" aria-label="页面导航">
      <a className="nav-brand" href="/">
        股票行情
      </a>
      <div className="nav-links">
        <a href="/admin">管理</a>
        <a href="/watchlist">我的自选</a>
        <MarketNavDropdown />
        {authUser ? (
          <>
            <span className="nav-user">{authUser.username}</span>
            <button type="button" className="nav-auth-button" onClick={onLogout}>
              退出
            </button>
          </>
        ) : (
          <button type="button" className="nav-auth-button" onClick={onOpenAuth}>
            登录/注册
          </button>
        )}
      </div>
    </nav>
  );
}

void PageNav;

function AuthModal({ open, mode, onClose, onSubmit, onSwitchMode, error }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  if (!open) {
    return null;
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div className="modal-card auth-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <h2>{mode === "register" ? "注册账号" : "登录账号"}</h2>
          <button type="button" className="modal-close" onClick={onClose}>
            ×
          </button>
        </div>
        <form
          className="auth-form"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit({ username, password });
          }}
        >
          <label>
            用户名
            <input value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label>
            密码
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          {error && <p className="form-error">{error}</p>}
          <button type="submit" className="primary-button">
            {mode === "register" ? "注册并登录" : "登录"}
          </button>
        </form>
        <button type="button" className="text-button" onClick={onSwitchMode}>
          {mode === "register" ? "已有账号？去登录" : "没有账号？去注册"}
        </button>
      </div>
    </div>
  );
}

void AuthModal;

function getAuthErrorMessage(message) {
  if (message === "Invalid username or password") {
    return "用户名或密码错误。如果还没有账号，请先注册。";
  }

  if (message === "Username already exists") {
    return "用户名已存在，请直接登录或换一个用户名。";
  }

  if (message === "Username is required") {
    return "请输入用户名。";
  }

  if (message === "Password is required") {
    return "请输入密码。";
  }

  return message || "登录请求失败，请稍后再试。";
}

function ChineseAuthModal({ open, mode, onClose, onSubmit, onSwitchMode, error }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  if (!open) {
    return null;
  }

  const isRegister = mode === "register";

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div className="modal-card auth-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>{isRegister ? "注册账号" : "登录账号"}</h2>
            <p>{isRegister ? "创建账号后即可管理自选股和研究工作台。" : "使用已有账号继续查看自选股。"}</p>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>
        <form
          className="auth-form"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit({ username, password });
          }}
        >
          <label>
            用户名
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label>
            密码
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={isRegister ? "new-password" : "current-password"}
            />
          </label>
          {error && <p className="form-error">{getAuthErrorMessage(error)}</p>}
          <button type="submit" className="primary-button">
            {isRegister ? "注册并登录" : "登录"}
          </button>
        </form>
        <button type="button" className="text-button auth-switch-button" onClick={onSwitchMode}>
          {isRegister ? "已有账号？去登录" : "还没有账号？先注册"}
        </button>
      </div>
    </div>
  );
}

function StockLinkCell({ stock, watchlistState, onWatchClick }) {
  return (
    <div className="stock-link-cell">
      <a className="stock-link" href={`/${stock.ts_code}`}>
        <strong>{stock.name}</strong>
        <span>{stock.ts_code}</span>
      </a>
      <button
        type="button"
        className={`watchlist-trigger ${watchlistState?.in_watchlist ? "is-active" : ""}`}
        onClick={() => onWatchClick(stock)}
      >
        {watchlistState?.in_watchlist ? "已自选" : "+"}
      </button>
    </div>
  );
}

function WatchlistEditorModal({ open, stock, groups, stockState, error, onClose, onSave, onCreateGroup }) {
  const [selectedIds, setSelectedIds] = useState(() => (stockState?.groups || []).map((group) => Number(group.id)));
  const [newGroupName, setNewGroupName] = useState("");

  if (!open || !stock) {
    return null;
  }

  const toggleGroup = (groupId) => {
    setSelectedIds((current) =>
      current.includes(groupId) ? current.filter((id) => id !== groupId) : [...current, groupId],
    );
  };

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div className="modal-card watchlist-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>设置自选股</h2>
            <p>{stock.name} {stock.ts_code}</p>
          </div>
          <button type="button" className="modal-close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="watchlist-group-list">
          {groups.length ? (
            groups.map((group) => (
              <label className="watchlist-group-option" key={group.id}>
                <input
                  type="checkbox"
                  checked={selectedIds.includes(Number(group.id))}
                  onChange={() => toggleGroup(Number(group.id))}
                />
                <span>{group.name}</span>
              </label>
            ))
          ) : (
            <p className="stock-panel-empty">还没有分组，先创建一个吧。</p>
          )}
        </div>
        <div className="watchlist-create-row">
          <input placeholder="新分组名称" value={newGroupName} onChange={(event) => setNewGroupName(event.target.value)} />
          <button
            type="button"
            className="secondary-button"
            onClick={async () => {
              const created = await onCreateGroup(newGroupName);
              if (!created) {
                return;
              }
              setNewGroupName("");
              setSelectedIds((current) =>
                current.includes(Number(created.id)) ? current : [...current, Number(created.id)],
              );
            }}
          >
            新建分组
          </button>
        </div>
        {error && <p className="form-error">{error}</p>}
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            取消
          </button>
          <button type="button" className="primary-button" onClick={() => onSave(selectedIds)}>
            保存
          </button>
        </div>
      </div>
    </div>
  );
}

function HomeNav({ authUser, onOpenAuth, onLogout }) {
  return (
    <main className="home-page">
      <ResearchPageNav authUser={authUser} onOpenAuth={onOpenAuth} onLogout={onLogout} />
    </main>
  );
}

function LegacyWatchlistPage({ authToken, authUser, onOpenAuth, onWatchClick, onGroupsChange }) {
  const [groups, setGroups] = useState([]);
  const [items, setItems] = useState([]);
  const [newGroupName, setNewGroupName] = useState("");
  const [renameDrafts, setRenameDrafts] = useState({});
  const [error, setError] = useState("");

  const loadData = () => {
    if (!authToken) {
      return;
    }

    Promise.all([
      apiRequest("/api/v1/watchlist/groups", { token: authToken }),
      apiRequest("/api/v1/watchlist/stocks", { token: authToken }),
    ])
      .then(([groupsPayload, stocksPayload]) => {
        const nextGroups = groupsPayload.items || [];
        setGroups(nextGroups);
        setItems(stocksPayload.items || []);
        onGroupsChange(nextGroups);
      })
      .catch((err) => {
        setError(err.message);
      });
  };

  useEffect(() => {
    if (!authToken) {
      return;
    }

    Promise.all([
      apiRequest("/api/v1/watchlist/groups", { token: authToken }),
      apiRequest("/api/v1/watchlist/stocks", { token: authToken }),
    ])
      .then(([groupsPayload, stocksPayload]) => {
        const nextGroups = groupsPayload.items || [];
        setGroups(nextGroups);
        setItems(stocksPayload.items || []);
        onGroupsChange(nextGroups);
      })
      .catch((err) => {
        setError(err.message);
      });
  }, [authToken, onGroupsChange]);

  if (!authUser) {
    return (
      <main className="market-page status">
        <div className="watchlist-empty">
          <p>登录后才能查看和管理自选股。</p>
          <button type="button" className="primary-button" onClick={onOpenAuth}>
            去登录
          </button>
        </div>
      </main>
    );
  }

  const groupedItems = groups.map((group) => ({
    ...group,
    stocks: items.filter((item) => (item.groups || []).some((itemGroup) => Number(itemGroup.id) === Number(group.id))),
  }));

  return (
    <main className="market-page">
      <section className="market-shell watchlist-shell" aria-label="我的自选">
        <header className="market-header">
          <div>
            <p className="eyebrow">我的自选</p>
            <h1>自选股分组</h1>
            <p className="market-subtitle">按分组管理你关注的股票。</p>
          </div>
        </header>
        <div className="watchlist-create-row watchlist-page-create">
          <input placeholder="新分组名称" value={newGroupName} onChange={(event) => setNewGroupName(event.target.value)} />
          <button
            type="button"
            className="primary-button"
            onClick={() => {
              apiRequest("/api/v1/watchlist/groups", {
                token: authToken,
                method: "POST",
                body: { name: newGroupName },
              })
                .then(() => {
                  setNewGroupName("");
                  setError("");
                  loadData();
                })
                .catch((err) => setError(err.message));
            }}
          >
            新建分组
          </button>
        </div>
        {error && <p className="form-error">{error}</p>}
        <div className="watchlist-groups-grid">
          {groupedItems.map((group) => (
            <section className="watchlist-group-card" key={group.id}>
              <div className="watchlist-group-header">
                <strong>{group.name}</strong>
                <span>{group.stocks.length} 只</span>
              </div>
              <div className="watchlist-group-actions">
                <input
                  value={renameDrafts[group.id] ?? group.name}
                  onChange={(event) => setRenameDrafts((current) => ({ ...current, [group.id]: event.target.value }))}
                />
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    apiRequest(`/api/v1/watchlist/groups/${group.id}`, {
                      token: authToken,
                      method: "PATCH",
                      body: { name: renameDrafts[group.id] ?? group.name },
                    })
                      .then(() => {
                        setError("");
                        loadData();
                      })
                      .catch((err) => setError(err.message));
                  }}
                >
                  重命名
                </button>
                <button
                  type="button"
                  className="secondary-button danger-button"
                  onClick={() => {
                    apiRequest(`/api/v1/watchlist/groups/${group.id}`, {
                      token: authToken,
                      method: "DELETE",
                    })
                      .then(() => {
                        setError("");
                        loadData();
                      })
                      .catch((err) => setError(err.message));
                  }}
                >
                  删除
                </button>
              </div>
              <div className="watchlist-stock-list">
                {group.stocks.length ? (
                  group.stocks.map((stock) => (
                    <div className="watchlist-stock-row" key={`${group.id}-${stock.ts_code}`}>
                      <a href={`/${stock.ts_code}`}>
                        <strong>{stock.name}</strong>
                        <span>{stock.ts_code}</span>
                      </a>
                      <button type="button" className="text-button" onClick={() => onWatchClick(stock)}>
                        调整分组
                      </button>
                    </div>
                  ))
                ) : (
                  <p className="stock-panel-empty">该分组还没有股票。</p>
                )}
              </div>
            </section>
          ))}
        </div>
      </section>
    </main>
  );
}

void LegacyWatchlistPage;

function WatchlistPage({ authToken, authUser, onOpenAuth, onWatchClick, onGroupsChange }) {
  const [groups, setGroups] = useState([]);
  const [items, setItems] = useState([]);
  const [newGroupName, setNewGroupName] = useState("");
  const [renameDrafts, setRenameDrafts] = useState({});
  const [activeGroupId, setActiveGroupId] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [stockSearchQuery, setStockSearchQuery] = useState("");
  const [stockSearchResults, setStockSearchResults] = useState([]);
  const [stockSearchLoading, setStockSearchLoading] = useState(false);
  const [stockSearchError, setStockSearchError] = useState("");
  const [stockSearchOpen, setStockSearchOpen] = useState(false);
  const [sortKey, setSortKey] = useState("change_percent");
  const [sortDirection, setSortDirection] = useState("desc");
  const [error, setError] = useState("");

  const loadData = () => {
    if (!authToken) {
      return;
    }

    Promise.all([
      apiRequest("/api/v1/watchlist/groups", { token: authToken }),
      apiRequest("/api/v1/watchlist/stocks", { token: authToken }),
    ])
      .then(([groupsPayload, stocksPayload]) => {
        const nextGroups = groupsPayload.items || [];
        setGroups(nextGroups);
        setItems(stocksPayload.items || []);
        onGroupsChange(nextGroups);
        setError("");
      })
      .catch((err) => {
        setError(err.message);
      });
  };

  useEffect(() => {
    if (!authToken) {
      return;
    }

    Promise.all([
      apiRequest("/api/v1/watchlist/groups", { token: authToken }),
      apiRequest("/api/v1/watchlist/stocks", { token: authToken }),
    ])
      .then(([groupsPayload, stocksPayload]) => {
        const nextGroups = groupsPayload.items || [];
        setGroups(nextGroups);
        setItems(stocksPayload.items || []);
        onGroupsChange(nextGroups);
        setError("");
      })
      .catch((err) => {
        setError(err.message);
      });
  }, [authToken, onGroupsChange]);

  useEffect(() => {
    const keyword = stockSearchQuery.trim();
    if (!keyword) {
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setStockSearchLoading(true);
      fetch(`${API_BASE}/api/v1/stocks/search?q=${encodeURIComponent(keyword)}&limit=8`, {
        signal: controller.signal,
      })
        .then(async (res) => {
          const payload = await res.json().catch(() => ({}));
          if (!res.ok) {
            throw new Error(payload.detail || "搜索股票失败");
          }
          setStockSearchResults(payload.items || []);
          setStockSearchError("");
          setStockSearchOpen(true);
        })
        .catch((err) => {
          if (err.name === "AbortError") {
            return;
          }
          setStockSearchResults([]);
          setStockSearchError(err.message);
        })
        .finally(() => {
          setStockSearchLoading(false);
        });
    }, 240);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [stockSearchQuery]);

  if (!authUser) {
    return (
      <main className="market-page status">
        <div className="watchlist-empty">
          <p>登录后才能查看和管理自选股。</p>
          <button type="button" className="primary-button" onClick={onOpenAuth}>
            去登录
          </button>
        </div>
      </main>
    );
  }

  const groupTabs = [
    { id: "all", name: "全部自选", stock_count: items.length },
    ...groups.map((group) => ({
      ...group,
      stock_count: items.filter((item) => (item.groups || []).some((itemGroup) => Number(itemGroup.id) === Number(group.id))).length,
    })),
  ];

  const visibleItems = (() => {
    const query = searchQuery.trim().toLowerCase();
    const filtered = items.filter((item) => {
      const inActiveGroup =
        activeGroupId === "all" ||
        (item.groups || []).some((group) => Number(group.id) === Number(activeGroupId));

      if (!inActiveGroup) {
        return false;
      }

      if (!query) {
        return true;
      }

      const groupNames = (item.groups || []).map((group) => group.name).join(" ");
      return (
        item.name.toLowerCase().includes(query) ||
        item.ts_code.toLowerCase().includes(query) ||
        (item.industry || "").toLowerCase().includes(query) ||
        (item.sw_l2_name || "").toLowerCase().includes(query) ||
        groupNames.toLowerCase().includes(query)
      );
    });

    return filtered.sort((left, right) => {
      const direction = sortDirection === "asc" ? 1 : -1;
      const leftValue = getWatchlistSortValue(left, sortKey);
      const rightValue = getWatchlistSortValue(right, sortKey);
      const leftValid = Number.isFinite(leftValue);
      const rightValid = Number.isFinite(rightValue);

      if (!leftValid && !rightValid) {
        return left.name.localeCompare(right.name);
      }

      if (!leftValid) {
        return 1;
      }

      if (!rightValid) {
        return -1;
      }

      if (leftValue === rightValue) {
        return left.name.localeCompare(right.name);
      }

      return (leftValue - rightValue) * direction;
    });
  })();

  const risingCount = items.filter((item) => Number(item.change_percent) > 0).length;
  const fallingCount = items.filter((item) => Number(item.change_percent) < 0).length;
  const latestTradeDate = items
    .map((item) => item.trade_date)
    .filter(Boolean)
    .sort()
    .at(-1);

  const handleSort = (nextSortKey) => {
    if (sortKey === nextSortKey) {
      setSortDirection((current) => (current === "desc" ? "asc" : "desc"));
      return;
    }

    setSortKey(nextSortKey);
    setSortDirection("desc");
  };

  const createGroup = () => {
    apiRequest("/api/v1/watchlist/groups", {
      token: authToken,
      method: "POST",
      body: { name: newGroupName },
    })
      .then(() => {
        setNewGroupName("");
        loadData();
      })
      .catch((err) => setError(err.message));
  };

  const openStockPage = (tsCode) => {
    if (!tsCode) {
      return;
    }
    window.location.assign(`/${encodeURIComponent(tsCode)}`);
  };

  const submitStockSearch = (event) => {
    event.preventDefault();
    const firstResult = stockSearchResults[0];
    if (firstResult) {
      openStockPage(firstResult.ts_code);
    }
  };

  return (
    <main className="market-page watchlist-page">
      <section className="market-shell watchlist-shell" aria-label="我的自选股">
        <header className="market-header watchlist-header">
          <div>
            <p className="eyebrow">我的自选</p>
            <h1>自选股行情</h1>
            <p className="market-subtitle">按分组查看关注股票，快速比较最新行情和行业位置。</p>
          </div>
          <div className="watchlist-header-actions">
            <a className="industry-action-link" href="/research">
              研究工作台
            </a>
          </div>
        </header>

        <section className="watchlist-stock-search" aria-label="搜索股票">
          <form className="watchlist-stock-search-form" onSubmit={submitStockSearch}>
            <div className="watchlist-stock-search-box">
              <input
                placeholder="输入股票代码或股票名称，回车进入个股页"
                value={stockSearchQuery}
                onChange={(event) => {
                  const nextQuery = event.target.value;
                  setStockSearchQuery(nextQuery);
                  if (!nextQuery.trim()) {
                    setStockSearchResults([]);
                    setStockSearchLoading(false);
                    setStockSearchError("");
                  }
                  setStockSearchOpen(true);
                }}
                onFocus={() => setStockSearchOpen(true)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    setStockSearchOpen(false);
                  }
                }}
              />
              {stockSearchOpen && stockSearchQuery.trim() && (
                <div className="watchlist-stock-search-results">
                  {stockSearchLoading && <div className="watchlist-stock-search-status">搜索中...</div>}
                  {!stockSearchLoading && stockSearchError && (
                    <div className="watchlist-stock-search-status is-error">{stockSearchError}</div>
                  )}
                  {!stockSearchLoading && !stockSearchError && stockSearchResults.length === 0 && (
                    <div className="watchlist-stock-search-status">没有匹配股票</div>
                  )}
                  {!stockSearchLoading && !stockSearchError && stockSearchResults.map((stock) => (
                    <button
                      type="button"
                      key={stock.ts_code}
                      className="watchlist-stock-search-result"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => openStockPage(stock.ts_code)}
                    >
                      <span>
                        <strong>{stock.name}</strong>
                        <em>{stock.ts_code}</em>
                      </span>
                      <small>{stock.sw_l3_name || stock.sw_l2_name || stock.industry || "--"}</small>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button type="submit" className="primary-button" disabled={!stockSearchResults.length}>
              查看个股
            </button>
          </form>
        </section>

        <section className="watchlist-summary" aria-label="自选股概览">
          <div>
            <span>自选总数</span>
            <strong>{items.length}</strong>
          </div>
          <div>
            <span>上涨</span>
            <strong className="is-up">{risingCount}</strong>
          </div>
          <div>
            <span>下跌</span>
            <strong className="is-down">{fallingCount}</strong>
          </div>
          <div>
            <span>最新交易日</span>
            <strong>{formatTradeDate(latestTradeDate)}</strong>
          </div>
        </section>

        <div className="watchlist-layout">
          <aside className="watchlist-sidebar" aria-label="自选股分组">
            <div className="watchlist-sidebar-header">
              <h2>分组</h2>
            </div>
            <div className="watchlist-group-tabs">
              {groupTabs.map((group) => (
                <button
                  type="button"
                  className={`watchlist-group-tab ${String(activeGroupId) === String(group.id) ? "is-active" : ""}`}
                  key={group.id}
                  onClick={() => setActiveGroupId(group.id)}
                >
                  <span>{group.name}</span>
                  <strong>{group.stock_count}</strong>
                </button>
              ))}
            </div>

            <div className="watchlist-create-panel">
              <input
                placeholder="新分组名称"
                value={newGroupName}
                onChange={(event) => setNewGroupName(event.target.value)}
              />
              <button type="button" className="primary-button" onClick={createGroup}>
                新建分组
              </button>
            </div>

            <div className="watchlist-group-manage">
              {groups.map((group) => (
                <div className="watchlist-group-manage-row" key={group.id}>
                  <input
                    value={renameDrafts[group.id] ?? group.name}
                    onChange={(event) => setRenameDrafts((current) => ({ ...current, [group.id]: event.target.value }))}
                  />
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => {
                      apiRequest(`/api/v1/watchlist/groups/${group.id}`, {
                        token: authToken,
                        method: "PATCH",
                        body: { name: renameDrafts[group.id] ?? group.name },
                      })
                        .then(loadData)
                        .catch((err) => setError(err.message));
                    }}
                  >
                    重命名
                  </button>
                  <button
                    type="button"
                    className="secondary-button danger-button"
                    onClick={() => {
                      apiRequest(`/api/v1/watchlist/groups/${group.id}`, {
                        token: authToken,
                        method: "DELETE",
                      })
                        .then(() => {
                          if (String(activeGroupId) === String(group.id)) {
                            setActiveGroupId("all");
                          }
                          loadData();
                        })
                        .catch((err) => setError(err.message));
                    }}
                  >
                    删除
                  </button>
                </div>
              ))}
            </div>
          </aside>

          <section className="watchlist-main" aria-label="自选股行情表">
            <div className="watchlist-filterbar">
              <input
                placeholder="搜索名称、代码、行业、分组"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
              <div className="watchlist-sort-buttons" aria-label="排序">
                <button type="button" className={sortKey === "change_percent" ? "is-active" : ""} onClick={() => handleSort("change_percent")}>
                  涨跌幅{sortKey === "change_percent" ? (sortDirection === "desc" ? " ↓" : " ↑") : ""}
                </button>
                <button type="button" className={sortKey === "price" ? "is-active" : ""} onClick={() => handleSort("price")}>
                  最新价{sortKey === "price" ? (sortDirection === "desc" ? " ↓" : " ↑") : ""}
                </button>
                <button type="button" className={sortKey === "amount" ? "is-active" : ""} onClick={() => handleSort("amount")}>
                  成交额{sortKey === "amount" ? (sortDirection === "desc" ? " ↓" : " ↑") : ""}
                </button>
              </div>
            </div>

            {error && <p className="form-error">{error}</p>}

            <div className="market-table-wrap watchlist-table-wrap">
              <table className="market-table watchlist-table">
                <thead>
                  <tr>
                    <th>股票</th>
                    <th>最新价</th>
                    <th>涨跌幅</th>
                    <th>涨跌额</th>
                    <th>行业</th>
                    <th>分组</th>
                    <th>成交额</th>
                    <th>换手率</th>
                    <th>交易日</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleItems.length ? visibleItems.map((stock) => (
                    <tr key={stock.ts_code}>
                      <td data-label="股票">
                        <a className="stock-link" href={`/${stock.ts_code}`}>
                          <strong>{stock.name}</strong>
                          <span>{stock.ts_code}</span>
                        </a>
                      </td>
                      <td data-label="最新价">{formatNumber(stock.price)}</td>
                      <td data-label="涨跌幅" className={getTrendClass(stock.change_percent)}>
                        {formatSigned(stock.change_percent, "%")}
                      </td>
                      <td data-label="涨跌额" className={getTrendClass(stock.change)}>
                        {formatSigned(stock.change)}
                      </td>
                      <td data-label="行业">
                        <span className="watchlist-industry">{stock.sw_l2_name || stock.industry || "--"}</span>
                      </td>
                      <td data-label="分组">
                        <div className="watchlist-stock-groups">
                          {(stock.groups || []).map((group) => (
                            <span key={group.id}>{group.name}</span>
                          ))}
                        </div>
                      </td>
                      <td data-label="成交额">{formatWatchlistAmount(stock.amount)}</td>
                      <td data-label="换手率">{formatPercent(stock.turnover_rate)}</td>
                      <td data-label="交易日">{formatTradeDate(stock.trade_date)}</td>
                      <td data-label="操作">
                        <div className="watchlist-row-actions">
                          <a className="text-button" href={`/${stock.ts_code}`}>查看行情</a>
                          <button type="button" className="text-button" onClick={() => onWatchClick(stock)}>
                            调整分组
                          </button>
                        </div>
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan="10">当前分组还没有匹配的自选股。</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}

function ResearchPageNav({ authUser, onOpenAuth, onLogout }) {
  return (
    <nav className="home-nav" aria-label="页面导航">
      <a className="nav-brand" href="/">
        股票行情
      </a>
      <div className="nav-links">
        <a href="/admin">管理</a>
        <a href="/research">研究工作台</a>
        <a href="/watchlist">旧版自选</a>
        <MarketNavDropdown />
        {authUser ? (
          <>
            <span className="nav-user">{authUser.username}</span>
            <button type="button" className="nav-auth-button" onClick={onLogout}>
              退出
            </button>
          </>
        ) : (
          <button type="button" className="nav-auth-button" onClick={onOpenAuth}>
            登录/注册
          </button>
        )}
      </div>
    </nav>
  );
}

function ResearchGate({ authUser, onOpenAuth, message = "登录后即可使用研究工作台。" }) {
  if (authUser) {
    return null;
  }

  return (
    <main className="market-page status">
      <div className="watchlist-empty">
        <p>{message}</p>
        <button type="button" className="primary-button" onClick={onOpenAuth}>
          去登录
        </button>
      </div>
    </main>
  );
}

function ResearchStatusBadge({ status }) {
  return <span className={`research-badge research-status-badge research-status-${status}`}>{formatResearchStatus(status)}</span>;
}

function ResearchPriorityBadge({ priority }) {
  return <span className={`research-badge research-priority-badge research-priority-${priority}`}>{formatResearchPriority(priority)}</span>;
}

function ResearchTagList({ tags }) {
  if (!tags?.length) {
    return <span className="research-empty-inline">--</span>;
  }

  return (
    <div className="research-tag-list">
      {tags.map((tag) => (
        <span className="research-tag" key={tag}>
          {tag}
        </span>
      ))}
    </div>
  );
}

function ResearchScoreGrid({ score }) {
  if (!score) {
    return null;
  }

  return (
    <div className="research-score-grid">
      <div>
        <dt>行业景气</dt>
        <dd>{score.industry_trend}</dd>
      </div>
      <div>
        <dt>竞争优势</dt>
        <dd>{score.competitive_advantage}</dd>
      </div>
      <div>
        <dt>财务质量</dt>
        <dd>{score.financial_quality}</dd>
      </div>
      <div>
        <dt>管理层</dt>
        <dd>{score.management}</dd>
      </div>
      <div>
        <dt>估值</dt>
        <dd>{score.valuation}</dd>
      </div>
      <div className="research-score-total">
        <dt>总分</dt>
        <dd>{score.total_score}</dd>
      </div>
    </div>
  );
}

function ResearchDashboardPage({ authToken, authUser, onOpenAuth }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!authToken) {
      return;
    }

    apiRequest("/api/v1/research/dashboard", { token: authToken })
      .then((payload) => {
        setData(payload);
        setError("");
      })
      .catch((err) => setError(err.message));
  }, [authToken]);

  if (!authUser) {
    return <ResearchGate authUser={authUser} onOpenAuth={onOpenAuth} />;
  }

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!data) {
    return <main className="market-page status">Loading research dashboard...</main>;
  }

  return (
    <main className="market-page research-page">
      <section className="market-shell research-shell" aria-label="Research dashboard">
        <header className="market-header">
          <div>
            <p className="eyebrow">Research Workspace</p>
            <h1>股票研究工作台</h1>
            <p className="market-subtitle">围绕研究、行动和复盘组织你的股票池。</p>
          </div>
          <div className="research-header-actions">
            <a className="industry-action-link" href="/research/stocks">
              打开研究列表
            </a>
          </div>
        </header>

        <section className="research-card">
          <div className="research-card-header">
            <h2>状态分组总览</h2>
          </div>
          <div className="research-status-overview">
            {RESEARCH_STATUS_OPTIONS.map((option) => (
              <a className="research-status-card" key={option.value} href={`/research/stocks?status=${option.value}`}>
                <span>{option.label}</span>
                <strong>{data.statusCounts?.[option.value] ?? 0}</strong>
              </a>
            ))}
          </div>
        </section>

        <div className="research-dashboard-grid">
          <section className="research-card">
            <div className="research-card-header">
              <h2>今日异动</h2>
              <span>阈值 ±5%</span>
            </div>
            <div className="research-list-block">
              {data.todayMovers?.length ? data.todayMovers.map((item) => (
                <a className="research-list-row" key={item.ts_code} href={`/research/${item.ts_code}`}>
                  <div>
                    <strong>{item.name}</strong>
                    <span>{item.ts_code}</span>
                  </div>
                  <div className={getTrendClass(item.change_percent)}>
                    {formatSigned(item.change_percent, "%")}
                  </div>
                </a>
              )) : <p className="stock-panel-empty">今天没有超过阈值的研究股票。</p>}
            </div>
          </section>

          <section className="research-card">
            <div className="research-card-header">
              <h2>触发条件达成</h2>
              <span>{data.isMock ? "Mock" : ""}</span>
            </div>
            <div className="research-list-block">
              {data.triggeredItems?.length ? data.triggeredItems.map((item) => (
                <a className="research-list-row research-list-row-stacked" key={item.ts_code} href={`/research/${item.ts_code}`}>
                  <div className="research-list-row-head">
                    <strong>{item.name}</strong>
                    <span className={getTrendClass(item.change_percent)}>{formatSigned(item.change_percent, "%")}</span>
                  </div>
                  <p>{item.trigger_condition}</p>
                </a>
              )) : <p className="stock-panel-empty">当前没有触发项。</p>}
            </div>
          </section>

          <section className="research-card">
            <div className="research-card-header">
              <h2>最近研究记录</h2>
            </div>
            <div className="research-list-block">
              {data.recentLogs?.length ? data.recentLogs.map((item) => (
                <a className="research-list-row research-list-row-stacked" key={item.id} href={`/research/${item.ts_code}`}>
                  <div className="research-list-row-head">
                    <strong>{item.name}</strong>
                    <span>{item.date}</span>
                  </div>
                  <p>{item.type} · {item.content}</p>
                </a>
              )) : <p className="stock-panel-empty">还没有研究日志。</p>}
            </div>
          </section>

          <section className="research-card">
            <div className="research-card-header">
              <h2>研究过期提醒</h2>
              <span>{data.staleAfterDays || 14} 天未更新</span>
            </div>
            <div className="research-list-block">
              {data.staleResearchItems?.length ? data.staleResearchItems.map((item) => (
                <a className="research-list-row" key={item.ts_code} href={`/research/${item.ts_code}`}>
                  <div>
                    <strong>{item.name}</strong>
                    <span>{formatDateTime(item.updated_at)}</span>
                  </div>
                  <ResearchStatusBadge status={item.status} />
                </a>
              )) : <p className="stock-panel-empty">当前没有过期研究。</p>}
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}

function ResearchStocksPage({ authToken, authUser, onOpenAuth }) {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState(() => getQueryParamFromLocation("status") || "all");
  const [priorityFilter, setPriorityFilter] = useState(() => getQueryParamFromLocation("priority") || "all");
  const [tagFilter, setTagFilter] = useState(() => getQueryParamFromLocation("tag") || "all");
  const [searchQuery, setSearchQuery] = useState(() => getQueryParamFromLocation("q"));
  const [createDraft, setCreateDraft] = useState({
    ts_code: "",
    status: "watchlist",
    priority: "medium",
    tags: "",
  });

  useEffect(() => {
    if (!authToken) {
      return;
    }

    apiRequest("/api/v1/research/stocks", { token: authToken })
      .then((payload) => {
        setItems(payload.items || []);
        setError("");
      })
      .catch((err) => setError(err.message));
  }, [authToken]);

  const allTags = useMemo(() => {
    return [...new Set(items.flatMap((item) => item.tags || []))].sort((left, right) => left.localeCompare(right));
  }, [items]);

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      if (statusFilter !== "all" && item.status !== statusFilter) {
        return false;
      }
      if (priorityFilter !== "all" && item.priority !== priorityFilter) {
        return false;
      }
      if (tagFilter !== "all" && !(item.tags || []).includes(tagFilter)) {
        return false;
      }
      if (!searchQuery.trim()) {
        return true;
      }
      const query = searchQuery.trim().toLowerCase();
      return (
        item.name.toLowerCase().includes(query) ||
        item.ts_code.toLowerCase().includes(query) ||
        (item.tags || []).some((tag) => tag.toLowerCase().includes(query))
      );
    });
  }, [items, priorityFilter, searchQuery, statusFilter, tagFilter]);

  if (!authUser) {
    return <ResearchGate authUser={authUser} onOpenAuth={onOpenAuth} message="登录后即可管理研究股票列表。" />;
  }

  return (
    <main className="market-page research-page">
      <section className="market-shell research-shell" aria-label="Research stocks">
        <header className="market-header">
          <div>
            <p className="eyebrow">Research Stocks</p>
            <h1>研究股票列表</h1>
            <p className="market-subtitle">筛选、搜索并进入单只股票的研究详情。</p>
          </div>
          <div className="research-header-actions">
            <a className="industry-action-link" href="/research">
              返回总览
            </a>
          </div>
        </header>

        <section className="research-card research-create-card">
          <div className="research-card-header">
            <h2>新增研究对象</h2>
          </div>
          <div className="research-create-grid">
            <input
              placeholder="股票代码，例如 000001.SZ"
              value={createDraft.ts_code}
              onChange={(event) => setCreateDraft((current) => ({ ...current, ts_code: event.target.value }))}
            />
            <select
              value={createDraft.status}
              onChange={(event) => setCreateDraft((current) => ({ ...current, status: event.target.value }))}
            >
              {RESEARCH_STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <select
              value={createDraft.priority}
              onChange={(event) => setCreateDraft((current) => ({ ...current, priority: event.target.value }))}
            >
              {RESEARCH_PRIORITY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <input
              placeholder="标签，逗号分隔"
              value={createDraft.tags}
              onChange={(event) => setCreateDraft((current) => ({ ...current, tags: event.target.value }))}
            />
            <button
              type="button"
              className="primary-button"
              onClick={() => {
                apiRequest("/api/v1/research/stocks", {
                  token: authToken,
                  method: "POST",
                  body: {
                    ts_code: createDraft.ts_code,
                    status: createDraft.status,
                    priority: createDraft.priority,
                    tags: normalizeTagInput(createDraft.tags),
                    thesis: "",
                    trigger_condition: "",
                    risk: "",
                    exit_condition: "",
                    score: {
                      industry_trend: 3,
                      competitive_advantage: 3,
                      financial_quality: 3,
                      management: 3,
                      valuation: 3,
                    },
                  },
                })
                  .then((payload) => {
                    window.location.href = `/research/${payload.ts_code}`;
                  })
                  .catch((err) => setError(err.message));
              }}
            >
              创建
            </button>
          </div>
        </section>

        <section className="research-card">
          <div className="research-filters">
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All Status</option>
              {RESEARCH_STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <select value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)}>
              <option value="all">All Priority</option>
              {RESEARCH_PRIORITY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <select value={tagFilter} onChange={(event) => setTagFilter(event.target.value)}>
              <option value="all">All Tags</option>
              {allTags.map((tag) => (
                <option key={tag} value={tag}>{tag}</option>
              ))}
            </select>
            <input
              placeholder="搜索名称、代码、标签"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </div>

          {error && <p className="form-error">{error}</p>}

          <div className="market-table-wrap research-table-wrap">
            <table className="market-table research-table">
              <thead>
                <tr>
                  <th>名称</th>
                  <th>代码</th>
                  <th>现价</th>
                  <th>涨跌幅</th>
                  <th>状态</th>
                  <th>优先级</th>
                  <th>标签</th>
                  <th>关注理由</th>
                  <th>触发条件</th>
                  <th>风险点</th>
                  <th>更新时间</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.length ? filteredItems.map((item) => (
                  <tr key={item.ts_code}>
                    <td data-label="名称">
                      <a className="stock-link" href={`/research/${item.ts_code}`}>
                        <strong>{item.name}</strong>
                      </a>
                    </td>
                    <td data-label="代码">{item.ts_code}</td>
                    <td data-label="现价">{formatNumber(item.price)}</td>
                    <td data-label="涨跌幅" className={getTrendClass(item.change_percent)}>
                      {formatSigned(item.change_percent, "%")}
                    </td>
                    <td data-label="状态"><ResearchStatusBadge status={item.status} /></td>
                    <td data-label="优先级"><ResearchPriorityBadge priority={item.priority} /></td>
                    <td data-label="标签"><ResearchTagList tags={item.tags} /></td>
                    <td data-label="关注理由">{item.thesis || "--"}</td>
                    <td data-label="触发条件">{item.trigger_condition || "--"}</td>
                    <td data-label="风险点">{item.risk || "--"}</td>
                    <td data-label="更新时间">{formatDateTime(item.updated_at)}</td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan="11">还没有匹配的研究股票。</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </main>
  );
}

function ResearchDetailPage({ authToken, authUser, onOpenAuth, tsCode }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState(null);
  const [tagInput, setTagInput] = useState("");
  const [logDraft, setLogDraft] = useState({
    date: new Date().toISOString().slice(0, 10),
    type: RESEARCH_LOG_TYPE_OPTIONS[0],
    content: "",
  });

  const loadDetail = () => {
    apiRequest(`/api/v1/research/stocks/${encodeURIComponent(tsCode)}`, { token: authToken })
      .then((payload) => {
        setData(payload);
        setDraft({
          status: payload.status,
          priority: payload.priority,
          thesis: payload.thesis || "",
          trigger_condition: payload.trigger_condition || "",
          risk: payload.risk || "",
          exit_condition: payload.exit_condition || "",
          score: { ...payload.score },
        });
        setTagInput((payload.tags || []).join(", "));
        setError("");
      })
      .catch((err) => setError(err.message));
  };

  useEffect(() => {
    if (!authToken) {
      return;
    }

    apiRequest(`/api/v1/research/stocks/${encodeURIComponent(tsCode)}`, { token: authToken })
      .then((payload) => {
        setData(payload);
        setDraft({
          status: payload.status,
          priority: payload.priority,
          thesis: payload.thesis || "",
          trigger_condition: payload.trigger_condition || "",
          risk: payload.risk || "",
          exit_condition: payload.exit_condition || "",
          score: { ...payload.score },
        });
        setTagInput((payload.tags || []).join(", "));
        setError("");
      })
      .catch((err) => setError(err.message));
  }, [authToken, tsCode]);

  const scorePreview = draft ? (
    Number(draft.score.industry_trend) +
    Number(draft.score.competitive_advantage) +
    Number(draft.score.financial_quality) +
    Number(draft.score.management) +
    Number(draft.score.valuation)
  ) : 0;

  if (!authUser) {
    return <ResearchGate authUser={authUser} onOpenAuth={onOpenAuth} message="登录后即可查看和维护研究详情。" />;
  }

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!data || !draft) {
    return <main className="market-page status">正在加载研究详情...</main>;
  }

  return (
    <main className="market-page research-page">
      <section className="market-shell research-shell" aria-label={`${data.name} 研究详情`}>
        <header className="research-detail-hero research-card">
          <div>
            <p className="eyebrow">研究详情</p>
            <h1>{data.name} <span>{data.ts_code}</span></h1>
            <div className="research-summary-row">
              <ResearchStatusBadge status={data.status} />
              <ResearchPriorityBadge priority={data.priority} />
              <ResearchTagList tags={data.tags} />
            </div>
          </div>
          <div className="research-price-summary">
            <strong>{formatNumber(data.price)}</strong>
            <span className={getTrendClass(data.change_percent)}>{formatSigned(data.change_percent, "%")}</span>
            <em>总分 {data.score?.total_score ?? scorePreview}</em>
          </div>
        </header>

        <section className="research-card">
          <div className="research-card-header">
            <h2>研究信息编辑</h2>
            <a className="industry-action-link" href="/research/stocks">返回列表</a>
          </div>
          <div className="research-editor-grid">
            <label>
              当前状态
              <select value={draft.status} onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value }))}>
                {RESEARCH_STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label>
              优先级
              <select value={draft.priority} onChange={(event) => setDraft((current) => ({ ...current, priority: event.target.value }))}>
                {RESEARCH_PRIORITY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="research-field-wide">
              产业标签
              <input value={tagInput} onChange={(event) => setTagInput(event.target.value)} placeholder="AI, 算力, 出海" />
            </label>
            <label className="research-field-wide">
              投资逻辑
              <textarea value={draft.thesis} onChange={(event) => setDraft((current) => ({ ...current, thesis: event.target.value }))} />
            </label>
            <label className="research-field-wide">
              买入 / 行动条件
              <textarea value={draft.trigger_condition} onChange={(event) => setDraft((current) => ({ ...current, trigger_condition: event.target.value }))} />
            </label>
            <label className="research-field-wide">
              风险因素
              <textarea value={draft.risk} onChange={(event) => setDraft((current) => ({ ...current, risk: event.target.value }))} />
            </label>
            <label className="research-field-wide">
              退出条件
              <textarea value={draft.exit_condition} onChange={(event) => setDraft((current) => ({ ...current, exit_condition: event.target.value }))} />
            </label>
          </div>

          <div className="research-score-editor">
            {[
              ["industry_trend", "行业景气"],
              ["competitive_advantage", "竞争优势"],
              ["financial_quality", "财务质量"],
              ["management", "管理层"],
              ["valuation", "估值"],
            ].map(([key, label]) => (
              <label key={key}>
                {label}
                <select
                  value={draft.score[key]}
                  onChange={(event) => setDraft((current) => ({
                    ...current,
                    score: { ...current.score, [key]: Number(event.target.value) },
                  }))}
                >
                  {[1, 2, 3, 4, 5].map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              </label>
            ))}
            <div className="research-score-preview">
              <span>预览总分</span>
              <strong>{scorePreview}</strong>
            </div>
          </div>

          <div className="modal-actions">
            <button
              type="button"
              className="primary-button"
              disabled={saving}
              onClick={() => {
                setSaving(true);
                apiRequest(`/api/v1/research/stocks/${encodeURIComponent(data.ts_code)}`, {
                  token: authToken,
                  method: "PUT",
                  body: {
                    ...draft,
                    tags: normalizeTagInput(tagInput),
                    score: draft.score,
                  },
                })
                  .then((payload) => {
                    setData(payload);
                    setDraft({
                      status: payload.status,
                      priority: payload.priority,
                      thesis: payload.thesis || "",
                      trigger_condition: payload.trigger_condition || "",
                      risk: payload.risk || "",
                      exit_condition: payload.exit_condition || "",
                      score: { ...payload.score },
                    });
                    setTagInput((payload.tags || []).join(", "));
                    setError("");
                  })
                  .catch((err) => setError(err.message))
                  .finally(() => setSaving(false));
              }}
            >
              {saving ? "保存中..." : "保存研究"}
            </button>
          </div>
        </section>

        <div className="research-detail-grid">
          <section className="research-card">
            <div className="research-card-header">
              <h2>投资逻辑</h2>
            </div>
            <p className="research-rich-text">{data.thesis || "--"}</p>
          </section>
          <section className="research-card">
            <div className="research-card-header">
              <h2>买入 / 行动条件</h2>
            </div>
            <p className="research-rich-text">{data.trigger_condition || "--"}</p>
          </section>
          <section className="research-card">
            <div className="research-card-header">
              <h2>风险因素</h2>
            </div>
            <p className="research-rich-text">{data.risk || "--"}</p>
          </section>
          <section className="research-card">
            <div className="research-card-header">
              <h2>退出条件</h2>
            </div>
            <p className="research-rich-text">{data.exit_condition || "--"}</p>
          </section>
        </div>

        <section className="research-card">
          <div className="research-card-header">
            <h2>评分系统</h2>
          </div>
          <ResearchScoreGrid score={data.score} />
        </section>

        <section className="research-card">
          <div className="research-card-header">
            <h2>研究日志</h2>
          </div>
          <div className="research-log-form">
            <input type="date" value={logDraft.date} onChange={(event) => setLogDraft((current) => ({ ...current, date: event.target.value }))} />
            <select value={logDraft.type} onChange={(event) => setLogDraft((current) => ({ ...current, type: event.target.value }))}>
              {RESEARCH_LOG_TYPE_OPTIONS.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
            <textarea
              value={logDraft.content}
              placeholder="记录新的研究观察、评级变化或复盘结论"
              onChange={(event) => setLogDraft((current) => ({ ...current, content: event.target.value }))}
            />
            <button
              type="button"
              className="primary-button"
              onClick={() => {
                apiRequest(`/api/v1/research/stocks/${encodeURIComponent(data.ts_code)}/logs`, {
                  token: authToken,
                  method: "POST",
                  body: logDraft,
                })
                  .then(() => {
                    setLogDraft((current) => ({ ...current, content: "" }));
                    loadDetail();
                  })
                  .catch((err) => setError(err.message));
              }}
            >
              添加日志
            </button>
          </div>
          <div className="research-log-list">
            {data.research_logs?.length ? data.research_logs.map((item) => (
              <article className="research-log-item" key={item.id}>
                <div className="research-log-meta">
                  <strong>{item.date}</strong>
                  <span>{item.type}</span>
                </div>
                <p>{item.content}</p>
              </article>
            )) : <p className="stock-panel-empty">还没有研究日志。</p>}
          </div>
        </section>
      </section>
    </main>
  );
}

function StockFactList({ items, className = "" }) {
  return (
    <dl className={`stock-fact-list ${className}`.trim()}>
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd className={item.className || ""}>{item.value ?? "--"}</dd>
        </div>
      ))}
    </dl>
  );
}

function StockPanel({ title, children, className = "" }) {
  return (
    <section className={`stock-panel ${className}`.trim()} aria-label={title}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

const PIE_COLORS = ["#d91f11", "#2563eb", "#f59e0b", "#008f4c", "#7c3aed", "#64748b", "#0f766e", "#be123c"];
const PIE_DEPTH_COLORS = ["#a9150b", "#1d4ed8", "#d97706", "#04703d", "#5b21b6", "#475569", "#115e59", "#9f1239"];

function polarToCartesian(radius, angle) {
  const radians = ((angle - 90) * Math.PI) / 180;

  return {
    x: radius * Math.cos(radians),
    y: radius * Math.sin(radians),
  };
}

function buildDonutSlicePath(startAngle, endAngle, outerRadius = 92, innerRadius = 25) {
  const outerStart = polarToCartesian(outerRadius, startAngle);
  const outerEnd = polarToCartesian(outerRadius, endAngle);
  const innerEnd = polarToCartesian(innerRadius, endAngle);
  const innerStart = polarToCartesian(innerRadius, startAngle);
  const largeArcFlag = endAngle - startAngle > 180 ? 1 : 0;

  return [
    `M ${outerStart.x} ${outerStart.y}`,
    `A ${outerRadius} ${outerRadius} 0 ${largeArcFlag} 1 ${outerEnd.x} ${outerEnd.y}`,
    `L ${innerEnd.x} ${innerEnd.y}`,
    `A ${innerRadius} ${innerRadius} 0 ${largeArcFlag} 0 ${innerStart.x} ${innerStart.y}`,
    "Z",
  ].join(" ");
}

function CompositionPie({ title, items = [] }) {
  const positiveItems = items
    .map((item) => ({
      ...item,
      salesNumber: Number(item.bz_sales),
    }))
    .filter((item) => Number.isFinite(item.salesNumber) && item.salesNumber > 0);
  const totalSales = positiveItems.reduce((sum, item) => sum + item.salesNumber, 0);
  const chartItems = positiveItems.map((item, index) => ({
    ...item,
    color: PIE_COLORS[index % PIE_COLORS.length],
    depthColor: PIE_DEPTH_COLORS[index % PIE_DEPTH_COLORS.length],
    ratio: totalSales > 0 ? (item.salesNumber / totalSales) * 100 : 0,
  }));
  const segments = chartItems.reduce(
    (acc, item) => {
      const start = acc.cursor;
      const end = start + item.ratio;
      const startAngle = (start / 100) * 360;
      const endAngle = (end / 100) * 360;
      const midAngle = (startAngle + endAngle) / 2;
      const explode = polarToCartesian(7, midAngle);
      const labelPoint = polarToCartesian(59, midAngle);

      return {
        cursor: end,
        values: [
          ...acc.values,
          {
            ...item,
            startAngle,
            endAngle,
            explode,
            labelPoint,
            path: buildDonutSlicePath(startAngle, endAngle),
          },
        ],
      };
    },
    { cursor: 0, values: [] },
  ).values;

  return (
    <section className="main-business-pie-card" aria-label={title}>
      <h3>{title}</h3>
      {chartItems.length ? (
        <>
          <svg className="main-business-pie" viewBox="-120 -116 240 238" role="img" aria-label={`${title}收入占比`}>
            {segments.map((segment) => (
              <g
                key={`${segment.end_date}-${segment.bz_item}-depth`}
                transform={`translate(${segment.explode.x} ${segment.explode.y + 7})`}
              >
                <path d={segment.path} fill={segment.depthColor} />
              </g>
            ))}
            <g className="main-business-pie-face">
              {segments.map((segment) => (
                <g
                  key={`${segment.end_date}-${segment.bz_item}`}
                  transform={`translate(${segment.explode.x} ${segment.explode.y})`}
                >
                  <path d={segment.path} fill={segment.color} />
                  {segment.ratio >= 4 && (
                    <text
                      x={segment.labelPoint.x}
                      y={segment.labelPoint.y}
                      textAnchor="middle"
                      dominantBaseline="central"
                    >
                      {`${segment.ratio.toFixed(0)}%`}
                    </text>
                  )}
                </g>
              ))}
            </g>
            <circle cx="0" cy="0" r="23" fill="#ffffff" />
          </svg>
          <div className="main-business-legend">
            {chartItems.map((item) => (
              <div className="main-business-legend-row" key={`${item.end_date}-${item.bz_item}`}>
                <span className="main-business-color" style={{ background: item.color }} />
                <strong>{item.bz_item || "--"}</strong>
                <em>{formatCompactNumber(item.bz_sales)}</em>
                <b>{item.ratio.toFixed(1)}%</b>
              </div>
            ))}
          </div>
        </>
      ) : (
        <p className="stock-panel-empty">暂无数据</p>
      )}
    </section>
  );
}

function MainBusinessComposition({ groups, items = [] }) {
  const productItems = groups?.product || items;
  const regionItems = groups?.region || [];
  const industryItems = groups?.industry || [];
  const period = productItems[0]?.end_date || regionItems[0]?.end_date || industryItems[0]?.end_date;

  if (!productItems.length && !regionItems.length && !industryItems.length) {
    return <p className="stock-panel-empty">暂无主营业务构成数据</p>;
  }

  return (
    <div className="main-business-composition">
      <div className="main-business-meta">
        <span>报告期</span>
        <strong>{formatTradeDate(period)}</strong>
      </div>
      <div className="main-business-pie-grid">
        <CompositionPie title="业务构成" items={productItems} />
        <CompositionPie title="地区构成" items={regionItems} />
        <CompositionPie title="行业口径" items={industryItems} />
      </div>
    </div>
  );
}

function getSameOriginReferrer() {
  if (!document.referrer) {
    return "";
  }

  try {
    const referrerUrl = new URL(document.referrer);
    if (referrerUrl.origin !== window.location.origin) {
      return "";
    }

    return `${referrerUrl.pathname}${referrerUrl.search}${referrerUrl.hash}`;
  } catch {
    return "";
  }
}

function getXueqiuUrl(tsCode) {
  const [symbol, exchange] = String(tsCode || "").split(".");

  if (!symbol || !exchange) {
    return "";
  }

  const exchangePrefix = {
    SH: "SH",
    SZ: "SZ",
    BJ: "BJ",
  }[exchange.toUpperCase()];

  if (!exchangePrefix) {
    return "";
  }

  return `https://xueqiu.com/S/${exchangePrefix}${symbol}`;
}

function getTonghuashunF10Url(tsCode) {
  const [symbol] = String(tsCode || "").split(".");

  if (!symbol) {
    return "";
  }

  return `https://basic.10jqka.com.cn/${symbol}/`;
}

function StockIdentityLinkList({ basic, concepts = [] }) {
  const industryItems = [
    {
      label: basic.sw_l1_name,
      href: basic.sw_l1_code ? `/industry/l1/${encodeURIComponent(basic.sw_l1_code)}` : "",
    },
    {
      label: basic.sw_l2_name,
      href: basic.sw_l2_code ? `/industry/l2/${encodeURIComponent(basic.sw_l2_code)}` : "",
    },
    {
      label: basic.sw_l3_name,
      href: basic.sw_l3_code ? `/industry/l3/${encodeURIComponent(basic.sw_l3_code)}` : "",
    },
  ].filter((item) => item.label);
  const conceptItems = concepts.map((concept) => ({
    label: concept.concept_name,
    href: concept.concept_code ? `/concept/${encodeURIComponent(concept.concept_code)}` : "",
  }));
  const items = [...industryItems, ...conceptItems];

  if (!items.length && basic.industry) {
    return <p className="stock-industry-path">{basic.industry}</p>;
  }

  if (!items.length) {
    return <p className="stock-industry-path">--</p>;
  }

  return (
    <p className="stock-industry-path">
      {items.map((item, index) => (
        <span className="stock-industry-path-item" key={`${item.label}-${index}`}>
          {index > 0 && <span className="stock-industry-separator">/</span>}
          {item.href ? <a href={item.href}>{item.label}</a> : <span>{item.label}</span>}
        </span>
      ))}
    </p>
  );
}

function IndustryTagsPage() {
  const [periods, setPeriods] = useState([]);
  const [industries, setIndustries] = useState([]);
  const [data, setData] = useState(null);
  const [period, setPeriod] = useState("latest");
  const [industryCode, setIndustryCode] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchJson("/api/v1/industry-tags/periods", "获取标签周期失败")
      .then((payload) => {
        const items = payload.items || [];
        setPeriods(items);
        if (items[0]?.end_date) {
          setPeriod(items[0].end_date);
        }
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    fetchOptionalJson(`/api/v1/industry-tags/industries?period=${encodeURIComponent(period)}`)
      .then((payload) => {
        setIndustries(payload?.items || []);
      })
      .catch(() => {
        setIndustries([]);
      });
  }, [period]);

  useEffect(() => {
    const params = new URLSearchParams({
      period,
      page: String(page),
      page_size: "50",
    });
    if (industryCode) {
      params.set("sw_l3_code", industryCode);
    }
    if (category) {
      params.set("tag_category", category);
    }

    fetchJson(`/api/v1/industry-tags?${params.toString()}`, "获取三级行业财务标签失败")
      .then((payload) => {
        setData(payload);
        setError("");
      })
      .catch((err) => setError(err.message));
  }, [period, industryCode, category, page]);

  const resetPage = (setter) => (value) => {
    setter(value);
    setPage(1);
  };

  const totalPages = data?.total_pages || 1;
  const items = data?.items || [];

  return (
    <main className="market-page industry-tags-page">
      <section className="market-shell industry-shell" aria-label="三级行业财务标签">
        <header className="market-header industry-detail-header">
          <div>
            <p className="eyebrow">三级行业财务标签</p>
            <h1>同业横向财务标签</h1>
            <p className="market-subtitle">
              只使用最近五年年报数据，所有高低判断都在同一申万三级行业内部完成。
            </p>
          </div>
          <a className="industry-action-link" href="/industry-movers-l3">
            三级行业排行
          </a>
        </header>

        <section className="industry-tag-controls" aria-label="标签筛选">
          <label>
            财报周期
            <select value={period} onChange={(event) => resetPage(setPeriod)(event.target.value)}>
              <option value="latest">最新已生成</option>
              {periods.map((item) => (
                <option key={item.end_date} value={item.end_date}>
                  {formatTradeDate(item.end_date)} · {item.stock_count || 0}股
                </option>
              ))}
            </select>
          </label>
          <label>
            三级行业
            <select value={industryCode} onChange={(event) => resetPage(setIndustryCode)(event.target.value)}>
              <option value="">全部三级行业</option>
              {industries.map((item) => (
                <option key={item.sw_l3_code} value={item.sw_l3_code}>
                  {item.sw_l3_name || item.sw_l3_code} · {item.stock_count || 0}股
                </option>
              ))}
            </select>
          </label>
          <label>
            标签分类
            <select value={category} onChange={(event) => resetPage(setCategory)(event.target.value)}>
              {INDUSTRY_TAG_CATEGORIES.map((item) => (
                <option key={item.value || "all"} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
        </section>

        {error && <p className="form-error">{error}</p>}

        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />

        <div className="market-table-wrap industry-tag-table-wrap">
          <table className="market-table industry-tag-table">
            <thead>
              <tr>
                <th>股票</th>
                <th>三级行业</th>
                <th>周期</th>
                <th>分类</th>
                <th>标签</th>
                <th>收入</th>
                <th>归母净利</th>
                <th>毛利率</th>
                <th>净利率</th>
                <th>ROE</th>
                <th>资产负债率</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              {items.length ? items.map((item) => (
                <tr key={`${item.ts_code}-${item.end_date}-${item.tag_code}`}>
                  <td data-label="股票">
                    <a className="stock-link" href={`/industry-tags/stock/${encodeURIComponent(item.ts_code)}`}>
                      <strong>{item.name || item.ts_code}</strong>
                      <span>{item.ts_code}</span>
                    </a>
                  </td>
                  <td data-label="三级行业">
                    <span className="industry-tag-path">
                      {item.sw_l3_code ? (
                        <a href={`/industry-tags/l3/${encodeURIComponent(item.sw_l3_code)}`}>
                          {item.sw_l3_name || item.sw_l3_code}
                        </a>
                      ) : (
                        <strong>{item.sw_l3_name || "--"}</strong>
                      )}
                      <em>{[item.sw_l1_name, item.sw_l2_name].filter(Boolean).join(" / ") || "--"}</em>
                    </span>
                  </td>
                  <td data-label="周期">{formatTradeDate(item.end_date)}</td>
                  <td data-label="分类">{item.tag_category_label}</td>
                  <td data-label="标签">
                    <span className={`industry-tag-pill industry-tag-${item.tag_category}`}>{item.tag_name}</span>
                  </td>
                  <td data-label="收入">{formatYuanToYi(item.revenue)}</td>
                  <td data-label="归母净利">{formatYuanToYi(item.net_profit)}</td>
                  <td data-label="毛利率">{formatPercent(item.gross_margin)}</td>
                  <td data-label="净利率">{formatPercent(item.net_margin)}</td>
                  <td data-label="ROE">{formatPercent(item.roe)}</td>
                  <td data-label="资产负债率">{formatPercent(item.debt_to_assets)}</td>
                  <td data-label="说明">{item.explanation || "--"}</td>
                </tr>
              )) : (
                <tr>
                  <td colSpan="12">暂无标签数据，请先运行三级行业财务标签生成脚本。</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
      </section>
    </main>
  );
}

function IndustryStockTagsPage({ tsCode }) {
  const [data, setData] = useState(null);
  const [period, setPeriod] = useState("");
  const [category, setCategory] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams();
    if (period) {
      params.set("period", period);
    }
    if (category) {
      params.set("tag_category", category);
    }

    const query = params.toString();
    fetchJson(
      `/api/v1/industry-tags/stocks/${encodeURIComponent(tsCode)}${query ? `?${query}` : ""}`,
      "获取股票财务标签失败",
    )
      .then((payload) => {
        setData(payload);
        setError("");
      })
      .catch((err) => setError(err.message));
  }, [tsCode, period, category]);

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!data) {
    return <main className="market-page status">加载中...</main>;
  }

  const industryPath = [data.sw_l1_name, data.sw_l2_name, data.sw_l3_name].filter(Boolean).join(" / ");

  return (
    <main className="market-page industry-tags-page">
      <section className="market-shell industry-shell" aria-label={`${data.name || tsCode} 财务标签总览`}>
        <header className="market-header industry-detail-header">
          <div>
            <p className="eyebrow">单股财务标签</p>
            <h1>{data.name || tsCode} <span>{data.ts_code}</span></h1>
            <p className="market-subtitle">
              {industryPath || "暂无行业路径"}；覆盖周期：{data.periods?.length ? data.periods.map(formatTradeDate).join("、") : "--"}。
            </p>
          </div>
          <div className="concept-actions">
            {data.sw_l3_code && (
              <a className="industry-action-link" href={`/industry-tags/l3/${encodeURIComponent(data.sw_l3_code)}`}>
                查看同行标签
              </a>
            )}
            <a className="industry-action-link" href={`/${encodeURIComponent(tsCode)}`}>
              股票 F10
            </a>
            <a className="industry-action-link" href="/industry-tags">
              返回标签列表
            </a>
          </div>
        </header>

        <section className="industry-tag-controls stock-tag-controls" aria-label="股票标签筛选">
          <label>
            财报周期
            <select value={period} onChange={(event) => setPeriod(event.target.value)}>
              <option value="">全部年报周期</option>
              {(data.periods || []).map((item) => (
                <option key={item} value={item}>{formatTradeDate(item)}</option>
              ))}
            </select>
          </label>
          <label>
            标签分类
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              {INDUSTRY_TAG_CATEGORIES.map((item) => (
                <option key={item.value || "all"} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
        </section>

        {(data.groups || []).length ? (
          <div className="stock-tag-groups">
            {data.groups.map((group) => (
              <section className="stock-tag-period" key={group.end_date}>
                <div className="stock-tag-period-header">
                  <div>
                    <p className="eyebrow">年报周期</p>
                    <h2>{formatTradeDate(group.end_date)}</h2>
                  </div>
                  <dl className="stock-tag-metrics">
                    <div>
                      <dt>收入</dt>
                      <dd>{formatYuanToYi(group.metrics?.revenue)}</dd>
                    </div>
                    <div>
                      <dt>归母净利</dt>
                      <dd>{formatYuanToYi(group.metrics?.net_profit)}</dd>
                    </div>
                    <div>
                      <dt>毛利率</dt>
                      <dd>{formatPercent(group.metrics?.gross_margin)}</dd>
                    </div>
                    <div>
                      <dt>净利率</dt>
                      <dd>{formatPercent(group.metrics?.net_margin)}</dd>
                    </div>
                    <div>
                      <dt>ROE</dt>
                      <dd>{formatPercent(group.metrics?.roe)}</dd>
                    </div>
                    <div>
                      <dt>资产负债率</dt>
                      <dd>{formatPercent(group.metrics?.debt_to_assets)}</dd>
                    </div>
                  </dl>
                </div>
                <div className="stock-tag-list">
                  {group.tags.map((tag) => (
                    <article className="stock-tag-card" key={`${tag.end_date}-${tag.tag_code}`}>
                      <div>
                        <span className={`industry-tag-pill industry-tag-${tag.tag_category}`}>{tag.tag_name}</span>
                        <em>{tag.tag_category_label}</em>
                      </div>
                      <p>{tag.explanation || "--"}</p>
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>
        ) : (
          <section className="industry-panel">
            <h2>暂无标签</h2>
            <p className="market-subtitle">当前筛选条件下没有找到该股票的三级行业财务标签。</p>
          </section>
        )}
      </section>
    </main>
  );
}

function IndustryTagDetailModal({ tag, onClose }) {
  if (!tag) {
    return null;
  }

  const percentile = tag.industry_percentile === null || tag.industry_percentile === undefined
    ? "--"
    : `${Math.round(Number(tag.industry_percentile) * 100)}%`;

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div className="modal-card industry-tag-detail-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <p className="eyebrow">标签详情</p>
            <h2>{tag.name || tag.ts_code} <span>{tag.ts_code}</span></h2>
          </div>
          <button type="button" className="modal-close" onClick={onClose}>×</button>
        </div>
        <div className="industry-tag-detail-main">
          <span className={`industry-tag-pill industry-tag-${tag.tag_category}`}>{tag.tag_name}</span>
          <strong>{tag.tag_category_label} · {formatTradeDate(tag.end_date)}</strong>
          <p>{tag.explanation || "--"}</p>
        </div>
        <dl className="industry-tag-detail-grid">
          <div><dt>指标值</dt><dd>{formatNumber(tag.metric_value)}</dd></div>
          <div><dt>行业分位</dt><dd>{percentile}</dd></div>
          <div><dt>收入</dt><dd>{formatYuanToYi(tag.revenue)}</dd></div>
          <div><dt>归母净利</dt><dd>{formatYuanToYi(tag.net_profit)}</dd></div>
          <div><dt>毛利率</dt><dd>{formatPercent(tag.gross_margin)}</dd></div>
          <div><dt>净利率</dt><dd>{formatPercent(tag.net_margin)}</dd></div>
          <div><dt>ROE</dt><dd>{formatPercent(tag.roe)}</dd></div>
          <div><dt>资产负债率</dt><dd>{formatPercent(tag.debt_to_assets)}</dd></div>
        </dl>
        <a className="industry-action-link" href={`/industry-tags/stock/${encodeURIComponent(tag.ts_code)}`}>
          查看该股票全部标签
        </a>
      </div>
    </div>
  );
}

function L3IndustryTagsPage({ swL3Code }) {
  const [data, setData] = useState(null);
  const [period, setPeriod] = useState("latest");
  const [selectedTag, setSelectedTag] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchJson(
      `/api/v1/industry-tags/l3/${encodeURIComponent(swL3Code)}?period=${encodeURIComponent(period)}`,
      "获取三级行业标签失败",
    )
      .then((payload) => {
        setData(payload);
        setSelectedTag(null);
        setError("");
      })
      .catch((err) => setError(err.message));
  }, [swL3Code, period]);

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!data) {
    return <main className="market-page status">加载中...</main>;
  }

  const industryPath = [data.sw_l1_name, data.sw_l2_name].filter(Boolean).join(" / ");

  return (
    <main className="market-page industry-tags-page">
      <section className="market-shell industry-shell" aria-label={`${data.sw_l3_name || swL3Code} 行业标签`}>
        <header className="market-header industry-detail-header">
          <div>
            <p className="eyebrow">三级行业标签</p>
            <h1>{data.sw_l3_name || swL3Code}</h1>
            <p className="market-subtitle">
              {industryPath || "--"}；{formatTradeDate(data.period)}；股票数 {data.stock_count}；标签数 {data.tag_count}。
            </p>
          </div>
          <div className="concept-actions">
            <a className="industry-action-link" href={`/industry/l3/${encodeURIComponent(swL3Code)}`}>
              行业总览
            </a>
            <a className="industry-action-link" href="/industry-tags">
              返回标签列表
            </a>
          </div>
        </header>

        <section className="industry-tag-controls stock-tag-controls" aria-label="行业标签筛选">
          <label>
            年报周期
            <select value={period} onChange={(event) => setPeriod(event.target.value)}>
              <option value="latest">最新年报</option>
              {(data.periods || []).map((item) => (
                <option key={item} value={item}>{formatTradeDate(item)}</option>
              ))}
            </select>
          </label>
        </section>

        <div className="market-table-wrap l3-tag-table-wrap">
          <table className="market-table l3-tag-table">
            <thead>
              <tr>
                <th>股票</th>
                <th>标签</th>
                <th>收入</th>
                <th>归母净利</th>
                <th>毛利率</th>
                <th>净利率</th>
                <th>ROE</th>
                <th>资产负债率</th>
              </tr>
            </thead>
            <tbody>
              {(data.items || []).length ? data.items.map((item) => (
                <tr key={item.ts_code}>
                  <td data-label="股票">
                    <a className="stock-link" href={`/industry-tags/stock/${encodeURIComponent(item.ts_code)}`}>
                      <strong>{item.name || item.ts_code}</strong>
                      <span>{item.ts_code}</span>
                    </a>
                  </td>
                  <td data-label="标签">
                    <div className="l3-tag-pills">
                      {item.tags.map((tag) => (
                        <button
                          type="button"
                          className={`industry-tag-pill industry-tag-${tag.tag_category}`}
                          key={`${tag.end_date}-${tag.tag_code}`}
                          onClick={() => setSelectedTag({ ...tag, name: item.name })}
                        >
                          {tag.tag_name}
                        </button>
                      ))}
                    </div>
                  </td>
                  <td data-label="收入">{formatYuanToYi(item.metrics?.revenue)}</td>
                  <td data-label="归母净利">{formatYuanToYi(item.metrics?.net_profit)}</td>
                  <td data-label="毛利率">{formatPercent(item.metrics?.gross_margin)}</td>
                  <td data-label="净利率">{formatPercent(item.metrics?.net_margin)}</td>
                  <td data-label="ROE">{formatPercent(item.metrics?.roe)}</td>
                  <td data-label="资产负债率">{formatPercent(item.metrics?.debt_to_assets)}</td>
                </tr>
              )) : (
                <tr>
                  <td colSpan="8">当前周期暂无该三级行业标签。</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
      <IndustryTagDetailModal tag={selectedTag} onClose={() => setSelectedTag(null)} />
    </main>
  );
}

function StockQuotePage({ tsCode, watchlistStateMap, onWatchClick }) {
  const [stock, setStock] = useState(null);
  const [error, setError] = useState("");
  const [returnPath] = useState(getSameOriginReferrer);

  useEffect(() => {
    fetch(`${API_BASE}/stock/${encodeURIComponent(tsCode)}`)
      .then((res) => {
        if (!res.ok) {
          throw new Error("获取股票数据失败");
        }
        return res.json();
      })
      .then((payload) => {
        setStock(payload);
      })
      .catch((err) => {
        setError(err.message);
      });
  }, [tsCode]);

  const trendClass = useMemo(() => {
    if (!stock) {
      return "";
    }

    return getTrendClass(stock.quote?.change ?? stock.change);
  }, [stock]);

  if (error) {
    return <main className="quote-page status">{error}</main>;
  }

  if (!stock) {
    return <main className="quote-page status">加载中...</main>;
  }

  const quote = stock.quote || stock;
  const basic = stock.basic || stock;
  const company = stock.company || {};
  const share = stock.share || {};
  const financial = stock.financial || {};
  const indicator = financial.indicator || {};
  const income = financial.income || {};
  const balance = financial.balance || {};
  const cashflow = financial.cashflow || {};
  const mainBusinessComposition = financial.main_business_composition || [];
  const mainBusinessCompositionGroups = financial.main_business_composition_groups || {};
  const performance = stock.performance || {};
  const metrics = stock.metrics || {};
  const financingBalance = stock.margin?.financing_balance || {};
  const volumeRatioNumber = Number(metrics.vol_ratio_20);
  const hasVolumeRatio = isNumericValue(metrics.vol_ratio_20);
  const volumeRatioClass = hasVolumeRatio ? getTrendClass(volumeRatioNumber - 1) : "";
  const volumeRatioDisplay = hasVolumeRatio ? (
    <span className="stock-volume-ratio">
      <strong className={volumeRatioClass}>{formatRatioPercentInteger(metrics.vol_ratio_20)}</strong>
      {metrics.volume_signal && <em>{metrics.volume_signal}</em>}
    </span>
  ) : "--";
  const xueqiuUrl = getXueqiuUrl(basic.ts_code || tsCode);
  const tonghuashunF10Url = getTonghuashunF10Url(basic.ts_code || tsCode);
  const industryTagsUrl = `/industry-tags/stock/${encodeURIComponent(basic.ts_code || tsCode)}`;
  const returnLabel = returnPath ? "返回上一页" : "返回首页";

  const handleReturn = () => {
    if (returnPath && window.history.length > 1) {
      window.history.back();
      return;
    }

    window.location.href = "/";
  };

  return (
    <main className="quote-page stock-home-page">
      <section className="stock-home-shell" aria-label={`${basic.name || tsCode} 股票主页`}>
        <header className="stock-hero">
          <div className="stock-title-block">
            <p className="eyebrow">股票 F10 概览</p>
            <h1>
              {basic.name || tsCode}
              <span>{basic.ts_code || tsCode}</span>
            </h1>
            <button
              type="button"
              className={`watchlist-trigger stock-watchlist-trigger ${watchlistStateMap[basic.ts_code || tsCode]?.in_watchlist ? "is-active" : ""}`}
              onClick={() => onWatchClick({ ts_code: basic.ts_code || tsCode, name: basic.name || tsCode })}
            >
              {watchlistStateMap[basic.ts_code || tsCode]?.in_watchlist ? "已自选" : "+ 加入自选"}
            </button>
            <div className="stock-identity-meta">
              <p>{company.com_name || "--"}</p>
              <StockIdentityLinkList basic={basic} concepts={stock.concepts} />
            </div>
          </div>

          <div className="stock-center-links">
            <a className="stock-external-link" href={industryTagsUrl}>
              财务标签
            </a>
            {xueqiuUrl && (
              <a className="stock-external-link" href={xueqiuUrl} target="_blank" rel="noreferrer">
                雪球
              </a>
            )}
            {tonghuashunF10Url && (
              <a className="stock-external-link" href={tonghuashunF10Url} target="_blank" rel="noreferrer">
                同花顺
              </a>
            )}
          </div>

          <div className="stock-price-block">
            <button type="button" className="stock-return-link" onClick={handleReturn}>
              {returnLabel}
            </button>
            <strong className={`stock-last-price ${trendClass}`}>{formatNumber(quote.close)}</strong>
            <span className={trendClass}>
              {formatSigned(quote.change)} / {formatSigned(quote.pct_chg, "%")}
            </span>
            <em>交易日 {formatTradeDate(quote.trade_date)}</em>
          </div>
        </header>

        <section className="stock-market-strip" aria-label="行情摘要">
          <StockFactList
            items={[
              {
                label: "今日涨跌幅",
                value: formatSigned(performance.today_pct_chg ?? quote.pct_chg, "%"),
                className: getTrendClass(performance.today_pct_chg ?? quote.pct_chg),
              },
              {
                label: "本月涨跌幅",
                value: formatSigned(performance.month_pct_chg, "%"),
                className: getTrendClass(performance.month_pct_chg),
              },
              {
                label: "两个月涨跌幅",
                value: formatSigned(performance.two_month_pct_chg, "%"),
                className: getTrendClass(performance.two_month_pct_chg),
              },
              {
                label: "三个月涨跌幅",
                value: formatSigned(performance.three_month_pct_chg, "%"),
                className: getTrendClass(performance.three_month_pct_chg),
              },
              {
                label: "六个月涨跌幅",
                value: formatSigned(performance.six_month_pct_chg, "%"),
                className: getTrendClass(performance.six_month_pct_chg),
              },
              {
                label: "今年涨跌幅",
                value: formatSigned(performance.year_pct_chg, "%"),
                className: getTrendClass(performance.year_pct_chg),
              },
              {
                label: "三年涨跌幅",
                value: formatSigned(performance.three_year_pct_chg, "%"),
                className: getTrendClass(performance.three_year_pct_chg),
              },
              { label: "总市值", value: formatWanYuan(share.market_value) },
              { label: "20日量比", value: volumeRatioDisplay },
            ]}
          />
          <StockFactList
            className="stock-margin-fact-list"
            items={[
              { label: "当前融资余额", value: formatYuanToYi(financingBalance.current?.rzye) },
              { label: "上周末融资余额", value: formatYuanToYi(financingBalance.last_week_end?.rzye) },
              { label: "上月末融资余额", value: formatYuanToYi(financingBalance.last_month_end?.rzye) },
              { label: "三个月前末融资余额", value: formatYuanToYi(financingBalance.three_month_end?.rzye) },
              { label: "一年前融资余额", value: formatYuanToYi(financingBalance.one_year_ago?.rzye) },
              { label: "两年前融资余额", value: formatYuanToYi(financingBalance.two_year_ago?.rzye) },
            ]}
          />
        </section>

        <div className="stock-f10-grid">
          <StockPanel title="基本资料">
            <StockFactList
              items={[
                { label: "公司全称", value: company.com_name },
                { label: "所属地区", value: basic.area || company.city },
                { label: "上市交易所", value: company.exchange },
                { label: "基础行业", value: basic.industry },
                { label: "申万一级", value: basic.sw_l1_name },
                { label: "申万二级", value: basic.sw_l2_name },
                { label: "申万三级", value: basic.sw_l3_name },
                { label: "员工人数", value: company.employees },
                { label: "董事长", value: company.chairman },
                { label: "总经理", value: company.manager },
              ]}
            />
          </StockPanel>

          <StockPanel title="财务摘要">
            <StockFactList
              items={[
                { label: "报告期", value: formatTradeDate(financial.period) },
                { label: "公告日", value: formatTradeDate(financial.ann_date) },
                { label: "营业收入", value: formatCompactNumber(income.revenue) },
                { label: "归母净利润", value: formatCompactNumber(income.n_income_attr_p) },
                { label: "每股收益", value: formatNumber(indicator.eps ?? income.basic_eps, 4) },
                { label: "每股净资产", value: formatNumber(indicator.bps, 4) },
                { label: "ROE", value: formatPercent(indicator.roe) },
                { label: "毛利率", value: formatPercent(indicator.grossprofit_margin) },
                { label: "净利率", value: formatPercent(indicator.netprofit_margin) },
                { label: "资产负债率", value: formatPercent(indicator.debt_to_assets) },
              ]}
            />
          </StockPanel>

          <StockPanel title="股本与资产">
            <StockFactList
              items={[
                { label: "总股本", value: formatWanShare(share.total_share) },
                { label: "流通股本", value: formatWanShare(share.float_share) },
                { label: "总资产", value: formatCompactNumber(balance.total_assets) },
                { label: "总负债", value: formatCompactNumber(balance.total_liab) },
                { label: "股东权益", value: formatCompactNumber(balance.total_hldr_eqy_exc_min_int) },
                { label: "货币资金", value: formatCompactNumber(balance.money_cap) },
                { label: "经营现金流", value: formatCompactNumber(cashflow.n_cashflow_act) },
                { label: "自由现金流", value: formatCompactNumber(cashflow.free_cashflow) },
              ]}
            />
          </StockPanel>

          <StockPanel title="经营分析">
            <div className="business-summary">
              <dl>
                <div>
                  <dt>主营业务</dt>
                  <dd>{company.main_business || "--"}</dd>
                </div>
              </dl>
              <p>{company.introduction || "--"}</p>
            </div>
          </StockPanel>

          <StockPanel title="主营业务构成" className="stock-panel-wide">
            <MainBusinessComposition
              groups={mainBusinessCompositionGroups}
              items={mainBusinessComposition}
            />
          </StockPanel>
        </div>
      </section>
    </main>
  );
}

// Legacy router kept for reference while AppRoot owns the live app shell.
function App() {
  const path = getPathFromLocation();

  if (!path) {
    return <HomeNav />;
  }

  if (path === "admin") {
    return (
      <>
        <AppNav />
        <AdminPage />
      </>
    );
  }

  if (RANKING_CONFIG[path]) {
    return (
      <>
        <AppNav />
        <MoversPage config={RANKING_CONFIG[path]} />
      </>
    );
  }

  if (path === "volume-movers") {
    return (
      <>
        <AppNav />
        <VolumeMoversPage />
      </>
    );
  }

  if (path === "industry-movers") {
    return (
      <>
        <AppNav />
        <IndustryMoversPage />
      </>
    );
  }

  if (path === "industry-movers-l3") {
    return (
      <>
        <AppNav />
        <IndustryMoversPage
          endpoint="/api/v1/industries/l3/movers"
          detailBasePath="/industry/l3"
          levelLabel="三级行业"
        />
      </>
    );
  }

  if (path === "concept-movers") {
    return (
      <>
        <AppNav />
        <ConceptMoversPage />
      </>
    );
  }

  if (path.startsWith("concept/") && path.endsWith("/movers")) {
    const conceptCode = path.slice("concept/".length, -"/movers".length);

    return (
      <>
        <AppNav />
        <ConceptMoversDetailPage conceptCode={decodeURIComponent(conceptCode)} />
      </>
    );
  }

  if (path.startsWith("concept/")) {
    const conceptCode = path.slice("concept/".length);

    return (
      <>
        <AppNav />
        <ConceptOverviewPage conceptCode={decodeURIComponent(conceptCode)} />
      </>
    );
  }

  if (path.startsWith("industry/l1/") && path.endsWith("/movers")) {
    const industryCode = path.slice("industry/l1/".length, -"/movers".length);

    return (
      <>
        <AppNav />
        <IndustryMoversDetailPage
          industryCode={decodeURIComponent(industryCode)}
          level="l1"
          levelLabel="一级行业"
        />
      </>
    );
  }

  if (path.startsWith("industry/l2/") && path.endsWith("/movers")) {
    const industryCode = path.slice("industry/l2/".length, -"/movers".length);

    return (
      <>
        <AppNav />
        <IndustryMoversDetailPage
          industryCode={decodeURIComponent(industryCode)}
          level="l2"
        />
      </>
    );
  }

  if (path.startsWith("industry/l1/") && path.endsWith("/stocks")) {
    const industryCode = path.slice("industry/l1/".length, -"/stocks".length);

    return (
      <>
        <AppNav />
        <IndustryStocksPage
          industryCode={decodeURIComponent(industryCode)}
          level="l1"
          levelLabel="一级行业"
        />
      </>
    );
  }

  if (path.startsWith("industry/l2/") && path.endsWith("/stocks")) {
    const industryCode = path.slice("industry/l2/".length, -"/stocks".length);

    return (
      <>
        <AppNav />
        <IndustryStocksPage
          industryCode={decodeURIComponent(industryCode)}
          level="l2"
        />
      </>
    );
  }

  if (path.startsWith("industry/l3/") && path.endsWith("/movers")) {
    const industryCode = path.slice("industry/l3/".length, -"/movers".length);

    return (
      <>
        <AppNav />
        <IndustryMoversDetailPage
          industryCode={decodeURIComponent(industryCode)}
          level="l3"
          levelLabel="三级行业"
        />
      </>
    );
  }

  if (path.startsWith("industry/l3/") && path.endsWith("/stocks")) {
    const industryCode = path.slice("industry/l3/".length, -"/stocks".length);

    return (
      <>
        <AppNav />
        <IndustryStocksPage
          industryCode={decodeURIComponent(industryCode)}
          level="l3"
          levelLabel="三级行业"
        />
      </>
    );
  }

  if (path.startsWith("industry/l1/")) {
    return (
      <>
        <AppNav />
        <IndustryOverviewPage
          industryCode={decodeURIComponent(path.slice("industry/l1/".length))}
          level="l1"
          levelLabel="一级行业"
        />
      </>
    );
  }

  if (path.startsWith("industry/l2/")) {
    return (
      <>
        <AppNav />
        <IndustryOverviewPage
          industryCode={decodeURIComponent(path.slice("industry/l2/".length))}
          level="l2"
        />
      </>
    );
  }

  if (path.startsWith("industry/l3/")) {
    return (
      <>
        <AppNav />
        <IndustryOverviewPage
          industryCode={decodeURIComponent(path.slice("industry/l3/".length))}
          level="l3"
          levelLabel="三级行业"
        />
      </>
    );
  }

  return <StockQuotePage tsCode={path} />;
}

void App;

function AppRoot() {
  const path = getPathFromLocation();
  const [authToken, setAuthToken] = useState(() => window.localStorage.getItem(AUTH_TOKEN_KEY) || "");
  const [authUser, setAuthUser] = useState(() => readStoredUser());
  const [authMode, setAuthMode] = useState("login");
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [authError, setAuthError] = useState("");
  const [watchlistGroups, setWatchlistGroups] = useState([]);
  const [watchlistStateMap, setWatchlistStateMap] = useState({});
  const [watchEditorStock, setWatchEditorStock] = useState(null);
  const [watchEditorError, setWatchEditorError] = useState("");

  const openAuthModal = (mode = "login") => {
    setAuthMode(mode);
    setAuthError("");
    setAuthModalOpen(true);
  };

  const handleLogout = () => {
    persistAuth("", null);
    setAuthToken("");
    setAuthUser(null);
    setWatchlistGroups([]);
    setWatchlistStateMap({});
    setWatchEditorStock(null);
  };

  const mergeWatchlistItems = (items) => {
    setWatchlistStateMap((current) => {
      const next = { ...current };
      (items || []).forEach((item) => {
        next[item.ts_code] = {
          ts_code: item.ts_code,
          in_watchlist: Boolean(item.groups?.length),
          groups: item.groups || [],
        };
      });
      return next;
    });
  };

  const loadGroups = () =>
    apiRequest("/api/v1/watchlist/groups", { token: authToken }).then((payload) => {
      setWatchlistGroups(payload.items || []);
      return payload.items || [];
    });

  const loadWatchState = (tsCode) =>
    apiRequest(`/api/v1/watchlist/stocks/${encodeURIComponent(tsCode)}`, { token: authToken }).then((payload) => {
      setWatchlistStateMap((current) => ({ ...current, [tsCode]: payload }));
      return payload;
    });

  useEffect(() => {
    if (!authToken) {
      return;
    }

    apiRequest("/api/v1/auth/me", { token: authToken })
      .then((payload) => {
        setAuthUser(payload.user);
        persistAuth(authToken, payload.user);
        setAuthError("");

        apiRequest("/api/v1/watchlist/groups", { token: authToken })
          .then((groupsPayload) => {
            setWatchlistGroups(groupsPayload.items || []);
          })
          .catch((err) => {
            setWatchEditorError(err.message);
          });

        apiRequest("/api/v1/watchlist/stocks", { token: authToken })
          .then((watchlistPayload) => {
            mergeWatchlistItems(watchlistPayload.items || []);
          })
          .catch((err) => {
            setWatchEditorError(err.message);
          });
      })
      .catch(() => {
        handleLogout();
      });
  }, [authToken]);

  const openWatchEditor = (stock) => {
    if (!authToken) {
      openAuthModal("login");
      return;
    }

    Promise.all([loadGroups(), loadWatchState(stock.ts_code)])
      .then(() => {
        setWatchEditorError("");
        setWatchEditorStock(stock);
      })
      .catch((err) => setWatchEditorError(err.message));
  };

  const createGroupFromEditor = (name) => {
    if (!name.trim()) {
      setWatchEditorError("请输入分组名称");
      return Promise.resolve(null);
    }

    return apiRequest("/api/v1/watchlist/groups", {
      token: authToken,
      method: "POST",
      body: { name },
    })
      .then((group) => {
        setWatchEditorError("");
        setWatchlistGroups((current) => [...current, group]);
        return group;
      })
      .catch((err) => {
        setWatchEditorError(err.message);
        return null;
      });
  };

  const saveWatchEditor = (groupIds) => {
    if (!watchEditorStock) {
      return;
    }

    apiRequest(`/api/v1/watchlist/stocks/${encodeURIComponent(watchEditorStock.ts_code)}`, {
      token: authToken,
      method: "PUT",
      body: { group_ids: groupIds },
    })
      .then((payload) => {
        setWatchlistStateMap((current) => ({ ...current, [watchEditorStock.ts_code]: payload }));
        setWatchEditorError("");
        setWatchEditorStock(null);
        loadGroups().catch(() => {});
      })
      .catch((err) => setWatchEditorError(err.message));
  };

  const chromeProps = {
    watchlistStateMap,
    onWatchClick: openWatchEditor,
  };

  const nav = <ResearchPageNav authUser={authUser} onOpenAuth={() => openAuthModal("login")} onLogout={handleLogout} />;
  const authModal = authModalOpen ? (
    <ChineseAuthModal
      key={`auth-${authMode}`}
      open={authModalOpen}
      mode={authMode}
      error={authError}
      onClose={() => setAuthModalOpen(false)}
      onSwitchMode={() => setAuthMode((current) => (current === "login" ? "register" : "login"))}
      onSubmit={({ username, password }) => {
        setAuthError("");
        apiRequest(`/api/v1/auth/${authMode}`, {
          method: "POST",
          body: { username, password },
        })
          .then((payload) => {
            persistAuth(payload.token, payload.user);
            setAuthToken(payload.token);
            setAuthUser(payload.user);
            setAuthModalOpen(false);
          })
          .catch((err) => setAuthError(err.message));
      }}
    />
  ) : null;
  const watchEditor = watchEditorStock ? (
    <WatchlistEditorModal
      key={`watch-${watchEditorStock.ts_code}-${(watchlistStateMap[watchEditorStock.ts_code]?.groups || []).map((group) => group.id).join("-")}`}
      open={Boolean(watchEditorStock)}
      stock={watchEditorStock}
      groups={watchlistGroups}
      stockState={watchlistStateMap[watchEditorStock.ts_code] || null}
      error={watchEditorError}
      onClose={() => setWatchEditorStock(null)}
      onSave={saveWatchEditor}
      onCreateGroup={createGroupFromEditor}
    />
  ) : null;

  const withChrome = (content) => (
    <>
      {nav}
      {content}
      {authModal}
      {watchEditor}
    </>
  );

  if (!path) {
    return (
      <>
        <HomeNav authUser={authUser} onOpenAuth={() => openAuthModal("login")} onLogout={handleLogout} />
        {authModal}
        {watchEditor}
      </>
    );
  }

  if (path === "research") {
    return withChrome(
      <ResearchDashboardPage
        authToken={authToken}
        authUser={authUser}
        onOpenAuth={() => openAuthModal("login")}
      />,
    );
  }

  if (path === "research/stocks") {
    return withChrome(
      <ResearchStocksPage
        authToken={authToken}
        authUser={authUser}
        onOpenAuth={() => openAuthModal("login")}
      />,
    );
  }

  if (path.startsWith("research/")) {
    return withChrome(
      <ResearchDetailPage
        authToken={authToken}
        authUser={authUser}
        onOpenAuth={() => openAuthModal("login")}
        tsCode={decodeURIComponent(path.slice("research/".length))}
      />,
    );
  }

  if (path === "watchlist") {
    return withChrome(
      <WatchlistPage
        authToken={authToken}
        authUser={authUser}
        onOpenAuth={() => openAuthModal("login")}
        onWatchClick={openWatchEditor}
        onGroupsChange={setWatchlistGroups}
      />,
    );
  }

  if (path === "admin") {
    return withChrome(<AdminPage />);
  }

  if (RANKING_CONFIG[path]) {
    return withChrome(<MoversPage config={RANKING_CONFIG[path]} {...chromeProps} />);
  }

  if (path === "volume-movers") {
    return withChrome(<VolumeMoversPage {...chromeProps} />);
  }

  if (path === "industry-movers") {
    return withChrome(<IndustryMoversPage />);
  }

  if (path === "industry-movers-l3") {
    return withChrome(<IndustryMoversPage endpoint="/api/v1/industries/l3/movers" detailBasePath="/industry/l3" levelLabel="三级行业" />);
  }

  if (path.startsWith("industry-tags/l3/")) {
    return withChrome(<L3IndustryTagsPage swL3Code={decodeURIComponent(path.slice("industry-tags/l3/".length))} />);
  }

  if (path.startsWith("industry-tags/stock/")) {
    return withChrome(<IndustryStockTagsPage tsCode={decodeURIComponent(path.slice("industry-tags/stock/".length))} />);
  }

  if (path === "industry-tags") {
    return withChrome(<IndustryTagsPage />);
  }

  if (path === "concept-movers") {
    return withChrome(<ConceptMoversPage />);
  }

  if (path.startsWith("concept/") && path.endsWith("/movers")) {
    const conceptCode = path.slice("concept/".length, -"/movers".length);
    return withChrome(<ConceptMoversDetailPage conceptCode={decodeURIComponent(conceptCode)} {...chromeProps} />);
  }

  if (path.startsWith("concept/")) {
    const conceptCode = path.slice("concept/".length);
    return withChrome(<ConceptOverviewPage conceptCode={decodeURIComponent(conceptCode)} {...chromeProps} />);
  }

  if (path.startsWith("industry/l1/") && path.endsWith("/movers")) {
    const industryCode = path.slice("industry/l1/".length, -"/movers".length);
    return withChrome(<IndustryMoversDetailPage industryCode={decodeURIComponent(industryCode)} level="l1" levelLabel="一级行业" {...chromeProps} />);
  }

  if (path.startsWith("industry/l2/") && path.endsWith("/movers")) {
    const industryCode = path.slice("industry/l2/".length, -"/movers".length);
    return withChrome(<IndustryMoversDetailPage industryCode={decodeURIComponent(industryCode)} level="l2" {...chromeProps} />);
  }

  if (path.startsWith("industry/l1/") && path.endsWith("/stocks")) {
    const industryCode = path.slice("industry/l1/".length, -"/stocks".length);
    return withChrome(<IndustryStocksPage industryCode={decodeURIComponent(industryCode)} level="l1" levelLabel="一级行业" {...chromeProps} />);
  }

  if (path.startsWith("industry/l2/") && path.endsWith("/stocks")) {
    const industryCode = path.slice("industry/l2/".length, -"/stocks".length);
    return withChrome(<IndustryStocksPage industryCode={decodeURIComponent(industryCode)} level="l2" {...chromeProps} />);
  }

  if (path.startsWith("industry/l3/") && path.endsWith("/movers")) {
    const industryCode = path.slice("industry/l3/".length, -"/movers".length);
    return withChrome(<IndustryMoversDetailPage industryCode={decodeURIComponent(industryCode)} level="l3" levelLabel="三级行业" {...chromeProps} />);
  }

  if (path.startsWith("industry/l3/") && path.endsWith("/stocks")) {
    const industryCode = path.slice("industry/l3/".length, -"/stocks".length);
    return withChrome(<IndustryStocksPage industryCode={decodeURIComponent(industryCode)} level="l3" levelLabel="三级行业" {...chromeProps} />);
  }

  if (path.startsWith("industry/l1/")) {
    return withChrome(<IndustryOverviewPage industryCode={decodeURIComponent(path.slice("industry/l1/".length))} level="l1" levelLabel="一级行业" {...chromeProps} />);
  }

  if (path.startsWith("industry/l2/")) {
    return withChrome(<IndustryOverviewPage industryCode={decodeURIComponent(path.slice("industry/l2/".length))} level="l2" {...chromeProps} />);
  }

  if (path.startsWith("industry/l3/")) {
    return withChrome(<IndustryOverviewPage industryCode={decodeURIComponent(path.slice("industry/l3/".length))} level="l3" levelLabel="三级行业" {...chromeProps} />);
  }

  return withChrome(<StockQuotePage tsCode={path} {...chromeProps} />);
}

export default AppRoot;
