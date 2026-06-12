# 一键每日数据更新逻辑

## 项目默认约定

以后在这个项目里，如果用户要求“更新数据”“更新行情”“跑更新”或类似操作，默认运行本文档里的总控脚本：

```powershell
cd E:\stock1\fastapi1
.\.venv\Scripts\python.exe update_all_market_data.py
```

不要优先单独运行零散脚本，除非用户明确要求只更新某一张表或某一个步骤。

## 脚本位置

脚本文件：

```powershell
E:\stock1\fastapi1\update_all_market_data.py
```

日常运行：

```powershell
cd E:\stock1\fastapi1
.\.venv\Scripts\python.exe update_all_market_data.py
```

只预览、不写数据库：

```powershell
.\.venv\Scripts\python.exe update_all_market_data.py --dry-run
```

## 默认更新范围

脚本默认做每日增量更新，不做全量历史重建。

默认检查最近 5 个开市日：

```powershell
.\.venv\Scripts\python.exe update_all_market_data.py --lookback-open-days 5
```

如果只想检查最近 1 个开市日：

```powershell
.\.venv\Scripts\python.exe update_all_market_data.py --lookback-open-days 1
```

## 更新顺序

### 1. 更新股票基础信息

调用 Tushare `stock_basic`，更新本地 `stocks` 表。

作用：

- 补充新上市股票
- 更新名称、地区、基础行业等信息
- 避免后续日行情或行业归属找不到股票

注意：

- 总控脚本不会给新股单独补 5000 天历史行情
- 日行情统一由后面的“按交易日补齐”逻辑处理

### 2. 更新申万行业归属

调用申万行业接口，更新 `stocks` 表里的行业字段。

主要字段：

- `sw_l1_code`
- `sw_l1_name`
- `sw_l2_code`
- `sw_l2_name`
- `sw_l3_code`
- `sw_l3_name`
- `sw_industry_src`
- `sw_in_date`
- `industry_updated_at`

作用：

- 支持二级行业排行页面
- 支持三级行业排行页面
- 支持行业详情页里按行业筛选股票

### 3. 补齐日行情

检查最近开市日的 `daily_quotes` 数据。

逻辑：

- 先读取本地 `daily_quotes` 最新交易日
- 根据 `--lookback-open-days` 回看最近若干个开市日
- 调用 Tushare 日行情接口检查每个交易日的全市场数量
- 如果本地数量少于 Tushare 返回数量，则写入或更新该交易日行情
- 如果数量已经一致，则跳过

主要表：

```text
daily_quotes
```

### 4. 同步盘前股本表

调用 Tushare `daily_basic`，同步对应交易日的股本数据。

主要表：

```text
stock_premarket
```

主要字段：

- `trade_date`
- `ts_code`
- `total_share`
- `float_share`

作用：

- `float_share` 用于计算换手率
- `total_share` 用于计算总市值

计算方式：

```text
换手率 = daily_quotes.vol / stock_premarket.float_share
总市值 = daily_quotes.close * stock_premarket.total_share
```

脚本不会只同步“今天”，而是同步本次检查到的交易日，尤其是最新 `daily_quotes.trade_date`。

### 5. 最终校验

脚本最后会检查最新行情日是否具备可用盘前数据。

输出内容包括：

- `daily_quotes` 总行数
- `daily_quotes` 最新交易日
- `stock_premarket` 总行数
- `stock_premarket` 最新交易日
- 最新交易日行情数量
- 最新交易日盘前表数量
- 缺失 `float_share` 的股票数量
- 几个样例股票的：
  - `ts_code`
  - `close`
  - `vol`
  - `float_share`
  - `turnover_rate`
  - `total_share`
  - `market_value`

如果最新日行情存在，但 `stock_premarket` 没有对应日期数据，页面上的换手率就会显示 `--`。

这种情况下通常有两种原因：

- Tushare 当时还没有发布该交易日的 `daily_basic`
- 盘前表同步脚本没有运行

## 常用参数

指定结束日期：

```powershell
.\.venv\Scripts\python.exe update_all_market_data.py --end-date 20260604
```

强制刷新日行情：

```powershell
.\.venv\Scripts\python.exe update_all_market_data.py --force-refresh
```

跳过股票基础信息：

```powershell
.\.venv\Scripts\python.exe update_all_market_data.py --skip-stocks
```

跳过行业同步：

```powershell
.\.venv\Scripts\python.exe update_all_market_data.py --skip-industries
```

跳过日行情：

```powershell
.\.venv\Scripts\python.exe update_all_market_data.py --skip-quotes
```

跳过盘前表：

```powershell
.\.venv\Scripts\python.exe update_all_market_data.py --skip-premarket
```

开发测试时限制股票或行业数量：

```powershell
.\.venv\Scripts\python.exe update_all_market_data.py --limit 100
```

## 今天实际运行结果示例

最近一次真实运行结果：

```text
End date: 20260604
Lookback open days: 1

stocks:
  Existing stocks: 5525
  Tushare listed stocks checked: 5524
  New stocks: 0
  Changed stocks: 82
  Saved or updated stock rows: 82

industries:
  Fetched industry rows: 5530
  Updated stock rows: 5519

daily_quotes:
  20260604 已完整
  本地已有 5511 条
  Tushare 返回 5511 条
  新增或更新 0 条

stock_premarket:
  20260604 fetched 5511 rows
  saved or updated 5511 rows

verification:
  daily_quotes latest trade_date: 20260604
  stock_premarket latest trade_date: 20260604
  quote rows on latest date: 5511
  premarket rows on latest date: 5511
  rows missing usable float_share: 0
```

结论：最新交易日的盘前表已经补齐，换手率计算所需的 `float_share` 已经可用。
