import tushare as ts

from settings import TUSHARE_TOKEN


pro = ts.pro_api(TUSHARE_TOKEN)

df2 = pro.rt_k(ts_code='600000.SH,000001.SZ')

print(df2.head())
