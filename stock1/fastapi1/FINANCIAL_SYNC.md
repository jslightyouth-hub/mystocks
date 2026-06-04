# Tushare 财务数据全字段同步

`sync_financials.py` 用于把 Tushare 财务接口返回的全部字段同步到本地 MySQL。

## 同步范围

默认日期范围是从今天往前 10 年到今天。例如在 2026-06-03 运行时，默认范围是：

```text
20160603 到 20260603
```

默认同步 4 个接口：

```text
income          -> financial_income
balancesheet    -> financial_balancesheet
cashflow        -> financial_cashflow
fina_indicator  -> financial_indicator
```

脚本不传 `fields` 参数，Tushare 返回什么字段，本地就保存什么字段。

## 表结构策略

脚本会自动：

- 创建财务数据表。
- 根据 Tushare 返回字段自动补列。
- 使用 `row_key` 做唯一键，重复运行会更新旧数据，不会重复插入。
- 创建 `financial_sync_status` 记录每个股票、接口、日期范围的同步状态。

非关键文本字段使用 `TEXT`，避免资产负债表字段过多时触发 MySQL 单行大小限制。

## 常用命令

先测试单只股票：

```powershell
cd E:\stock1\fastapi1
.\.venv\Scripts\python.exe sync_financials.py --ts-code 600519.SH
```

测试前 10 只股票：

```powershell
.\.venv\Scripts\python.exe sync_financials.py --limit 10
```

全量同步：

```powershell
.\.venv\Scripts\python.exe sync_financials.py
```

指定日期范围：

```powershell
.\.venv\Scripts\python.exe sync_financials.py --start-date 20160101 --end-date 20260603
```

只同步某几个接口：

```powershell
.\.venv\Scripts\python.exe sync_financials.py --interfaces income,fina_indicator
```

跳过已经成功同步过的任务：

```powershell
.\.venv\Scripts\python.exe sync_financials.py --skip-synced
```

## 建议执行顺序

先更新股票基础表：

```powershell
.\.venv\Scripts\python.exe update_stocks.py --skip-quotes
```

再做小样本验证：

```powershell
.\.venv\Scripts\python.exe sync_financials.py --ts-code 600519.SH
.\.venv\Scripts\python.exe sync_financials.py --limit 10
```

最后全量跑：

```powershell
.\.venv\Scripts\python.exe sync_financials.py --skip-synced
```

如果中途失败，修复后重新执行同一条命令即可。已经成功的任务会因为 `--skip-synced` 被跳过，失败任务会继续重试。
