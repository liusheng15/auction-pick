import tushare as ts
import os
import requests
import json

# 初始化 Tushare
ts.set_token(os.environ.get('TUSHARE_TOKEN'))
pro = ts.pro_api()

# 测试基础日线接口
df = pro.daily(ts_code='000001.SZ', start_date='20240101', end_date='20240105')
print(df)

# --- 推送结果到微信 (Pushplus) ---
content = df.head(10).to_string()
token = os.environ.get('PUSHPLUS_TOKEN')

if token:
    url = "https://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": "GitHub工作流运行成功！",
        "content": f"数据抓取成功，预览：\n{content}",
        "template": "markdown"
    }
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, headers=headers, data=json.dumps(data).encode(encoding='utf-8'))
    print("推送状态码:", response.status_code)
    print("推送返回结果:", response.text)
else:
    print("错误：未检测到 PUSHPLUS_TOKEN 环境变量！")
