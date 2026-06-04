# 日常数据更新

本文档说明如何使用 `backfill_missing_daily_quotes.py` 检查并补齐 `daily_quotes` 表中缺失的股票日线数据。

## 常用更新命令

```powershell
cd E:\stock1\fastapi1
.\.venv\Scripts\python.exe backfill_missing_daily_quotes.py
```

脚本会自动检查最近交易日是否缺数据：

- 如果有缺失数据，会打印需要更新的交易日，并写入数据库。
- 如果没有缺失数据，会输出 `已经是最新的数据，不用更新`，不会写入数据库。

## 检查逻辑

脚本会按交易日检查数据是否完整：

1. 查询 `daily_quotes` 表中的最新 `trade_date`、最新 `updated_at` 和总记录数。
2. 通过 Tushare 交易日历获取需要检查的开市日。
3. 对每个交易日调用 Tushare `pro.daily(trade_date=...)` 获取当天全市场日线数据。
4. 对比数据库中该交易日已有记录数和 Tushare 返回记录数。
5. 如果数据库记录数少于 Tushare 返回记录数，则认为该交易日需要更新。

写入时使用 `ts_code + trade_date` 唯一键：

- 已存在的记录会更新。
- 缺失的记录会插入。
- 不会生成重复数据。

## 有数据需要更新时

脚本会打印需要更新的日期，例如：

```text
需要更新的交易日: 20260522,20260525
[1/2] 20260522: 更新完成，原有 0 条，写入 5504 条
[2/2] 20260525: 更新完成，原有 0 条，写入 5504 条
已更新交易日: 20260522,20260525
Done. Saved or updated 11008 daily quote row(s).
```

## 数据已经最新时

如果所有检查日期都完整，会输出：

```text
[1/2] 20260527: 已完整，已有 5506 条，Tushare 有 5506 条
[2/2] 20260528: 已完整，已有 5506 条，Tushare 有 5506 条
已经是最新的数据，不用更新
```

## 只检查不写入

使用 `--dry-run` 可以只检查，不写数据库：

```powershell
.\.venv\Scripts\python.exe backfill_missing_daily_quotes.py --dry-run
```

## 指定检查截止日期

例如检查到 `20260528`：

```powershell
.\.venv\Scripts\python.exe backfill_missing_daily_quotes.py --end-date 20260528
```

## 强制刷新

如果想刷新目标交易日，即使记录数已经完整，也可以使用：

```powershell
.\.venv\Scripts\python.exe backfill_missing_daily_quotes.py --force-refresh
```

日常使用通常只需要运行常用更新命令。

---

# 股票基础信息更新

本文档说明如何使用 `update_stocks.py` 更新 `stocks` 表。这个脚本用于处理新股上市、股票名称变化、地区或行业信息变化等情况。

## 常用更新命令

```powershell
cd E:\stock1\fastapi1
.\.venv\Scripts\python.exe update_stocks.py
```

脚本会自动：

- 从 Tushare 获取当前所有上市股票基础信息。
- 读取数据库 `stocks` 表中的现有股票信息。
- 对比 `ts_code`、`symbol`、`name`、`area`、`industry` 字段。
- 如果发现新股票，则插入数据库。
- 如果发现已有股票的信息变化，则更新数据库。
- 如果发现新股票，则自动为这些新股票补齐日线数据到 `daily_quotes`。
- 如果没有新增或变化，则输出 `股票基础信息已经是最新的数据，不用更新`。

## 有数据需要更新时

脚本会打印新增股票和信息变化股票，例如：

```text
New stocks: 5
Changed stocks: 53
新增股票:
  001237.SZ C惠康
  920220.BJ 朗信电气
信息变化股票:
  000608.SZ 阳光股份 changed_fields=name
Done. Saved or updated 58 stock row(s).
```

如果包含新增股票，脚本还会继续补齐这些新股票的日线数据，例如：

```text
Backfilling daily quotes for 5 new stock(s), date range 20120820 to 20260528
[1/5] 001237.SZ C惠康: saved 4 daily quote row(s)
已补齐日线数据的新股票: 001237.SZ,920220.BJ
```

## 数据已经最新时

如果数据库已经和 Tushare 一致，会输出：

```text
Tushare listed stocks: 5524
New stocks: 0
Changed stocks: 0
股票基础信息已经是最新的数据，不用更新
```

## 只检查不写入

```powershell
.\.venv\Scripts\python.exe update_stocks.py --dry-run
```

## 只检查一只股票

```powershell
.\.venv\Scripts\python.exe update_stocks.py --ts-code 000001.SZ
```

## 测试前 N 只股票

```powershell
.\.venv\Scripts\python.exe update_stocks.py --limit 10
```

## 新股票日线补齐范围

默认会为新增股票回填最近 5000 个自然日的日线数据：

```powershell
.\.venv\Scripts\python.exe update_stocks.py
```

也可以指定回填天数：

```powershell
.\.venv\Scripts\python.exe update_stocks.py --quote-days 1000
```

如果只想更新 `stocks` 表，不想补日线数据：

```powershell
.\.venv\Scripts\python.exe update_stocks.py --skip-quotes
```
