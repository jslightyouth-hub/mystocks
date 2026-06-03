import { useEffect, useMemo, useState } from "react";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";
const RANK_LIMIT = 50;

const RANKING_CONFIG = {
  "top-movers": {
    endpoint: "/stocks/top-movers",
    title: "涨幅前 50",
    ariaLabel: "前一交易日涨幅榜",
    errorText: "获取涨幅榜失败",
  },
  "bottom-movers": {
    endpoint: "/stocks/bottom-movers",
    title: "跌幅前 50",
    ariaLabel: "前一交易日跌幅榜",
    errorText: "获取跌幅榜失败",
  },
};

function getPathFromLocation() {
  return decodeURIComponent(window.location.pathname.replace(/^\/+/, "").trim());
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

function MoversPage({ config }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    setError("");

    fetch(`${API_BASE}${config.endpoint}?limit=${RANK_LIMIT}`)
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
  }, [config]);

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
            <h1>{config.title}</h1>
          </div>
          <div className="trade-date">
            <span>交易日</span>
            <strong>{formatTradeDate(data.trade_date)}</strong>
          </div>
        </header>

        <div className="market-table-wrap">
          <table className="market-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>股票</th>
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
                      <span className="rank">{index + 1}</span>
                    </td>
                    <td data-label="股票">
                      <a className="stock-link" href={`/${stock.ts_code}`}>
                        <strong>{stock.name}</strong>
                        <span>{stock.ts_code}</span>
                      </a>
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
      </section>
    </main>
  );
}

function HomeNav() {
  return (
    <main className="home-page">
      <nav className="home-nav" aria-label="首页导航">
        <a className="nav-brand" href="/">
          股票行情
        </a>
        <div className="nav-links">
          <a href="/top-movers">涨幅前 50</a>
          <a href="/bottom-movers">跌幅前 50</a>
        </div>
      </nav>
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
      .then((data) => {
        setStock(data);
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
    return <MoversPage config={RANKING_CONFIG[path]} />;
  }

  return <StockQuotePage tsCode={path} />;
}

export default App;
