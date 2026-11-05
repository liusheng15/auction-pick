import tushare as ts

# 初始化（这里会被GitHub的Secret自动替换，保持原样即可）
ts.set_token("你的TOKEN")
pro = ts.pro_api()

# 测试基础日线接口（不需要特殊权限）
df = pro.daily(ts_code='000001.SZ', start_date='20240101', end_date='20240105')
print(df)
