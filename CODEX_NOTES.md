# Codex Notes

## 财报数据库位置

- 财报数据使用本机 MySQL，不是本地 SQLite/DB 文件。
- 连接配置由 `fastapi1/settings.py` 读取 `fastapi1/config/.env`。
- 当前数据库位置：`mysql+pymysql://root:****@localhost:3306/stockdb`
- 财报同步脚本：`fastapi1/sync_financials.py`
- 主要财报表：
  - `financial_income`
  - `financial_balancesheet`
  - `financial_cashflow`
  - `financial_indicator`
  - `financial_mainbz`
  - `financial_sync_status`
