import { useEffect, useMemo, useState } from "react";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";
const RANK_PAGE_SIZE = 50;
const TOTAL_RANK_PAGES = 5;

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

function AppNav() {
  return (
    <nav className="home-nav" aria-label="页面导航">
      <a className="nav-brand" href="/">
        股票行情
      </a>
      <div className="nav-links">
        <a href="/top-movers">涨幅榜</a>
        <a href="/bottom-movers">跌幅榜</a>
        <a href="/industry-movers">二级行业排行</a>
        <a href="/industry-movers-l3">三级行业排行</a>
      </div>
    </nav>
  );
}

function Pagination({ page, totalPages, onPageChange }) {
  const pages = Array.from({ length: totalPages }, (_, index) => index + 1);

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
        {pages.map((pageNumber) => (
          <button
            type="button"
            key={pageNumber}
            className={`pager-page ${pageNumber === page ? "is-active" : ""}`}
            aria-current={pageNumber === page ? "page" : undefined}
            onClick={() => onPageChange(pageNumber)}
          >
            {pageNumber}
          </button>
        ))}
      </div>
      <button
        type="button"
        className="pager-button"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        下一页
      </button>
    </nav>
  );
}

function MoversPage({ config }) {
  const [page, setPage] = useState(getPageFromLocation);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setPage(getPageFromLocation());
  }, [config]);

  useEffect(() => {
    setData(null);
    setError("");
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
                      <a className="stock-link" href={`/${stock.ts_code}`}>
                        <strong>{stock.name}</strong>
                        <span>{stock.ts_code}</span>
                      </a>
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

function IndustryMoversPage({
  endpoint = "/industries/movers",
  detailBasePath = "/industry",
  levelLabel = "二级行业",
}) {
  const [excludeHigh, setExcludeHigh] = useState(1);
  const [excludeLow, setExcludeLow] = useState(1);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    setError("");

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
  }, [excludeHigh, excludeLow]);

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!data) {
    return <main className="market-page status">加载中...</main>;
  }

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
                <th>平均涨跌幅</th>
                <th>行业股票数</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((industry, index) => {
                const trendClass = getTrendClass(industry.avg_pct_chg);

                return (
                  <tr key={industry.industry_name}>
                    <td data-label="排名">
                      <span className="rank">{index + 1}</span>
                    </td>
                    <td data-label={levelLabel} className="industry-name-cell">
                      <a href={`${detailBasePath}/${encodeURIComponent(industry.industry_name)}`}>
                        {industry.industry_name}
                      </a>
                    </td>
                    <td data-label="平均涨跌幅" className={trendClass}>
                      {formatSigned(industry.avg_pct_chg, "%")}
                    </td>
                    <td data-label="行业股票数">{industry.stock_count}</td>
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

function IndustryStocksPage({
  industryName,
  endpointBase = "/industries",
  levelLabel = "二级行业",
}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    setError("");

    fetch(`${API_BASE}${endpointBase}/${encodeURIComponent(industryName)}/stocks?limit=10`)
      .then((res) => {
        if (!res.ok) {
          throw new Error("获取行业股票失败");
        }
        return res.json();
      })
      .then((payload) => {
        setData(payload);
      })
      .catch((err) => {
        setError(err.message);
      });
  }, [industryName]);

  if (error) {
    return <main className="market-page status">{error}</main>;
  }

  if (!data) {
    return <main className="market-page status">加载中...</main>;
  }

  return (
    <main className="market-page">
      <section className="market-shell industry-shell" aria-label={`${industryName} 行业股票`}>
        <header className="market-header industry-detail-header">
          <div>
            <h1>{levelLabel}：{data.industry_name}</h1>
            <p className="market-subtitle">
              数据日期：{formatTradeDate(data.trade_date)}；分别显示涨幅前 10 和跌幅前 10，股票数量不足 10 只时显示全部。
            </p>
          </div>
        </header>

        <div className="industry-stock-grid">
          <IndustryStockTable title="涨幅前 10" stocks={data.top_items || []} />
          <IndustryStockTable title="跌幅前 10" stocks={data.bottom_items || []} />
        </div>
      </section>
    </main>
  );
}

function IndustryStockTable({ title, stocks }) {
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
              <th>总市值</th>
              <th>成交额</th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((stock, index) => {
              const trendClass = getTrendClass(stock.pct_chg);

              return (
                <tr key={stock.ts_code}>
                  <td data-label="排名">
                    <span className="rank">{index + 1}</span>
                  </td>
                  <td data-label="股票">
                    <a className="stock-link" href={`/${stock.ts_code}`}>
                      <strong>{stock.name}</strong>
                      <span>{stock.ts_code}</span>
                    </a>
                  </td>
                  <td data-label="收盘价">{formatNumber(stock.close)}</td>
                  <td data-label="涨跌幅" className={trendClass}>
                    {formatSigned(stock.pct_chg, "%")}
                  </td>
                  <td data-label="换手率">{formatPercent(stock.turnover_rate)}</td>
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

function HomeNav() {
  return (
    <main className="home-page">
      <AppNav />
    </main>
  );
}

function StockQuotePage({ tsCode }) {
  const [stock, setStock] = useState(null);
  const [error, setError] = useState("");

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

    return getTrendClass(stock.change);
  }, [stock]);

  if (error) {
    return <main className="quote-page status">{error}</main>;
  }

  if (!stock) {
    return <main className="quote-page status">加载中...</main>;
  }

  return (
    <main className="quote-page">
      <section className="quote-row" aria-label="股票行情">
        <div className="quote-id">
          <strong>{stock.name}</strong>
          <span>{stock.ts_code}</span>
        </div>

        <strong className="quote-price">{formatNumber(stock.close)}</strong>

        <strong className={`quote-change ${trendClass}`}>
          {formatSigned(stock.change)} ({formatSigned(stock.pct_chg, "%")})
        </strong>

        <strong className="quote-metric">{formatNumber(stock.vol / 10000)} 万手</strong>
        <strong className="quote-metric">{formatNumber(stock.amount / 100000)} 亿</strong>

        <strong className={`quote-pct ${trendClass}`}>{formatSigned(stock.pct_chg, "%")}</strong>
      </section>
    </main>
  );
}

function App() {
  const path = getPathFromLocation();

  if (!path) {
    return <HomeNav />;
  }

  if (RANKING_CONFIG[path]) {
    return (
      <>
        <AppNav />
        <MoversPage config={RANKING_CONFIG[path]} />
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
          endpoint="/industries/l3/movers"
          detailBasePath="/industry-l3"
          levelLabel="三级行业"
        />
      </>
    );
  }

  if (path.startsWith("industry/")) {
    return (
      <>
        <AppNav />
        <IndustryStocksPage industryName={decodeURIComponent(path.slice("industry/".length))} />
      </>
    );
  }

  if (path.startsWith("industry-l3/")) {
    return (
      <>
        <AppNav />
        <IndustryStocksPage
          industryName={decodeURIComponent(path.slice("industry-l3/".length))}
          endpointBase="/industries/l3"
          levelLabel="三级行业"
        />
      </>
    );
  }

  return <StockQuotePage tsCode={path} />;
}

export default App;
