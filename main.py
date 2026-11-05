import tushare as ts
import os
import requests
import json

# 调试：确认环境变量是否传进来
token_len = len(os.environ.get('TUSHARE_TOKEN', ''))
print(f"检测到 TUSHARE_TOKEN 长度: {token_len}")

# 初始化 Tushare
ts.set_token(os.environ.get('TUSHARE_TOKEN'))
pro = ts.pro_api()

# 抓取数据
df = pro.daily(ts_code='000001.SZ', start_date='20240101', end_date='20240105')
print("数据预览：")
print(df)

# --- 推送结果到微信 (Pushplus) ---
token = os.environ.get('PUSHPLUS_TOKEN')

if token:
    # 优化1：把浮点数（价格、涨跌幅等）限制为保留2位小数，防止数字太长挤爆手机屏幕
    table_html = df.head(10).to_html(
        index=False, 
        border=1, 
        justify='center',
        float_format='%.2f'
    )
    
    url = "https://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": "📈 每日选股结果",
        "content": f"""
        <h3>数据抓取成功！</h3>
        <p>以下是前10条记录：</p>
        <!-- 优化2：加入CSS样式，强制表格内容不折行，并允许横向滑动 -->
        <div style="overflow-x: auto;">
        <style>
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 4px; white-space: nowrap; }}
        </style>
        {table_html}
        </div>
        <p><small>由 GitHub Actions 自动推送</small></p>
        """,
        "template": "html"
    }
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, headers=headers, data=json.dumps(data).encode('utf-8'))
    
    print("推送状态码:", response.status_code)
    print("推送返回结果:", response.text)
    
    result = response.json()
    if result.get("code") == 200:
        print("✅ Pushplus 推送成功！请检查微信。")
    else:
        print("❌ Pushplus 推送失败！原因:", result.get("msg"))
else:
    print("错误：未检测到 PUSHPLUS_TOKEN 环境变量！")
