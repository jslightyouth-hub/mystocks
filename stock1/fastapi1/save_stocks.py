import pandas as pd
import tushare as ts
from sqlalchemy import create_engine, text

from settings import DATABASE_URL, TUSHARE_TOKEN


pro = ts.pro_api(TUSHARE_TOKEN)
engine = create_engine(DATABASE_URL)


# 获取股票基础信息
df = pro.stock_basic(
    exchange="",
    list_status="L",
    fields="ts_code,symbol,name,area,industry",
)

# MySQL 不接受 Pandas 的 NaN，写入前转成 None，对应数据库里的 NULL。
df = df.where(df.notna(), None)

print(df.head())


def clean_value(value):
    if pd.isna(value):
        return None
    return value


sql = text("""
    INSERT INTO stocks (
        ts_code,
        symbol,
        name,
        area,
        industry
    )
    VALUES (
        :ts_code,
        :symbol,
        :name,
        :area,
        :industry
    )
    ON DUPLICATE KEY UPDATE
        symbol = VALUES(symbol),
        name = VALUES(name),
        area = VALUES(area),
        industry = VALUES(industry)
""")


# 写入数据库
with engine.begin() as conn:
    for _, row in df.iterrows():
        conn.execute(sql, {
            "ts_code": clean_value(row["ts_code"]),
            "symbol": clean_value(row["symbol"]),
            "name": clean_value(row["name"]),
            "area": clean_value(row["area"]),
            "industry": clean_value(row["industry"]),
        })


print("股票同步完成")
