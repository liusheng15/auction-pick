import os
import requests
import tushare as ts

# ================= 配置区 =================
TUSHARE_TOKEN = "6c965d2da7f6f8793b953b5a4be60612fcda8bcdd55c8134d3384140"   # ← 改成你自己的 Tushare Token
PUSHPLUS_TOKEN = "f694582d3e5046bca8a989f91b27ed04"  # ← 改成你自己的 PushPlus Token
# ===========================================

# 初始化 Tushare
pro = ts.pro_api(TUSHARE_TOKEN)

def get_auction_data():
    # 这里以获取股票竞价快照为例，实际可根据需求调整
    df = pro.daily(ts_code='000001.SZ', start_date='20240101', end_date='20240105')
print(df)

        trade_date='20250218', 
        fields='ts_code,trade_date,vol,price,amount,turnover_rate,volume_ratio'
    )
    return df.to_string()

def send_pushplus(content):
    url = 'http://www.pushplus.plus/send'
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": "每日拍卖数据播报",
        "content": content
    }
    requests.post(url, json=data)

if __name__ == "__main__":
    data = get_auction_data()
    send_pushplus(data)
    print("执行完毕，已推送")
