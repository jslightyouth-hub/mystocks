# 股票行情展示项目

这个项目由两个目录组成：

- `fastapi1`：后端服务，使用 FastAPI 调用 Tushare 获取股票行情。
- `react1/vite-project`：前端页面，使用 React 和 Vite 展示单行股票行情条。

访问方式：

```text
http://127.0.0.1:5173/{ts_code}
```

示例：

```text
http://127.0.0.1:5173/000001.SZ
```

## 后端文件说明

### `fastapi1/main.py`

FastAPI 后端入口文件。

主要职责：

- 创建 FastAPI 应用。
- 配置 CORS，允许前端访问后端接口。
- 提供接口 `GET /stock/{ts_code}`。
- 调用 `stock_service.py` 获取股票行情。
- 当当天没有行情数据时返回 `404`。

### `fastapi1/stock_service.py`

股票行情业务逻辑文件。

主要职责：

- 初始化 Tushare 客户端。
- 获取当前系统日期，并转换成 Tushare 需要的 `YYYYMMDD` 格式。
- 调用 Tushare 查询指定股票当天行情。
- 查询股票名称。
- 整理前端需要的字段：
  - `ts_code`
  - `trade_date`
  - `open`
  - `high`
  - `low`
  - `close`
  - `pre_close`
  - `change`
  - `pct_chg`
  - `vol`
  - `amount`
  - `name`
- 把 pandas/numpy 类型转换成 FastAPI 可以返回的普通 JSON 值。

### `fastapi1/settings.py`

后端配置文件。

主要职责：

- 读取 `fastapi1/config/.env`。
- 从环境变量中加载：
  - `TUSHARE_TOKEN`
  - `DATABASE_URL`
- 当必要配置缺失时抛出明确错误。

### `fastapi1/config/.env`

本地环境变量文件，不建议提交到代码仓库。

示例：

```env
TUSHARE_TOKEN=你的TushareToken
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/database
```

### `fastapi1/save_stocks.py`

股票基础信息同步脚本。

主要职责：

- 调用 Tushare 获取股票基础信息。
- 把股票代码、名称、地区、行业等信息写入 MySQL。
- 使用 `ON DUPLICATE KEY UPDATE` 更新已存在的数据。

### `fastapi1/test.py`

Tushare 接口测试脚本。

主要职责：

- 用于单独测试 Tushare 财务数据接口是否可用。

### `fastapi1/uvicorn.out.log` 和 `fastapi1/uvicorn.err.log`

Uvicorn 后端服务日志文件。

## 前端文件说明

### `react1/vite-project/src/App.jsx`

React 主页面组件。

主要职责：

- 从浏览器路径中读取股票代码，例如 `/000001.SZ`。
- 请求后端接口 `http://127.0.0.1:8000/stock/{ts_code}`。
- 显示股票名称、代码、收盘价、涨跌额、涨跌幅、成交量和成交额。
- 根据涨跌额设置颜色：
  - 上涨：红色
  - 下跌：绿色
  - 不涨不跌：默认黑色
- 当访问首页 `/` 时提示用户在地址后添加股票代码。

### `react1/vite-project/src/App.css`

行情条样式文件。

主要职责：

- 控制页面背景和行情条布局。
- 按截图样式展示单行行情。
- 设置上涨红色、下跌绿色。
- 保持窄屏时行情条不换成表格，仍然以单行形式展示。

### `react1/vite-project/src/main.jsx`

React 应用入口文件。

主要职责：

- 创建 React 根节点。
- 渲染 `App` 组件。

### `react1/vite-project/src/index.css`

全局样式文件。

主要职责：

- 设置页面字体、基础颜色、根节点布局等全局样式。

### `react1/vite-project/vite.config.js`

Vite 配置文件。

主要职责：

- 启用 React 插件。
- 提供 Vite 开发和构建配置入口。

### `react1/vite-project/package.json`

前端依赖和脚本配置文件。

常用脚本：

```bash
npm run dev
npm run build
npm run lint
npm run preview
```

### `react1/vite-project/package-lock.json`

前端依赖锁定文件。

主要职责：

- 固定 npm 依赖版本，保证不同环境安装结果一致。

### `react1/vite-project/public`

Vite 静态资源目录。

主要职责：

- 存放会被原样复制到构建结果中的静态文件。

### `react1/vite-project/src/assets`

前端资源目录。

主要职责：

- 存放图片、SVG 等前端资源文件。

### `react1/vite-project/src/components`

早期组件目录。

当前行情页面主要由 `App.jsx` 渲染，这个目录下的组件暂时没有参与当前页面展示。

## 运行方式

### 启动后端

在 `fastapi1` 目录执行：

```bash
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

后端接口地址：

```text
http://127.0.0.1:8000/stock/000001.SZ
```

### 启动前端

在 `react1/vite-project` 目录执行：

```bash
npm run dev -- --host 127.0.0.1 --port 5173
```

前端访问地址：

```text
http://127.0.0.1:5173/000001.SZ
```

## 数据说明

当前后端按系统日期查询当天行情：

```python
datetime.now().strftime("%Y%m%d")
```

如果当天不是交易日，或者 Tushare 暂时没有当天数据，接口会返回 `404`。

## 日线行情入库

### `fastapi1/sync_daily_quotes.py`

日线行情同步脚本。

主要职责：

- 创建 MySQL 表 `daily_quotes`。
- 从 `stocks` 表读取全部股票代码。
- 按每个 `ts_code` 调用 Tushare `pro.query("daily", ts_code=..., start_date=..., end_date=...)`。
- 默认日期范围是当前系统日期往前 5000 个自然日。
- 每只股票每天保存一条记录。
- 使用 `ts_code + trade_date` 做唯一约束，重复运行会更新已有记录。

默认同步全部股票最近 5000 天的日线数据：

```bash
.venv\Scripts\python.exe sync_daily_quotes.py
```

续跑时跳过已经入库过的股票：

```bash
.venv\Scripts\python.exe sync_daily_quotes.py --skip-existing
```

只测试一只股票：

```bash
.venv\Scripts\python.exe sync_daily_quotes.py --ts-code 000001.SZ
```

只测试前 10 只股票：

```bash
.venv\Scripts\python.exe sync_daily_quotes.py --limit 10
```

### `daily_quotes` 表

字段说明：

- `id`：自增主键
- `ts_code`：股票代码
- `trade_date`：交易日期
- `open`：开盘价
- `high`：最高价
- `low`：最低价
- `close`：收盘价
- `pre_close`：昨收价
- `change`：涨跌额
- `pct_chg`：涨跌幅
- `vol`：成交量，单位是手
- `amount`：成交额，单位是千元
- `created_at`：创建时间
- `updated_at`：更新时间
