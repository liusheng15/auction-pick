import os, time, json, tushare as ts, pandas as pd, requests

TODAY = time.strftime('%Y%m%d')
pro = ts.pro_api(os.environ['TUSHARE_TOKEN'])

# ---------- 1. 行业强度(A方案) + 本地缓存防限频 ----------
def get_industry_strength():
    # 先尝试读本地缓存
    if os.path.exists('basic_cache.csv'):
        basic = pd.read_csv('basic_cache.csv')
    else:
        # 没缓存就调接口，加异常捕获和重试
        for i in range(3):
            try:
                basic = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry')
                basic.to_csv('basic_cache.csv', index=False) # 存到本地
                break
            except Exception as e:
                print("stock_basic 限频，休眠60秒重试...")
                time.sleep(60)
        else:
            raise Exception("stock_basic 多次重试失败，放弃")
            
    # 后面是算行业强度的逻辑（省略原有细节，保留你的筛选）
    # ...
    return {}

industry_score = get_industry_strength()

# ---------- 2. 选股主逻辑（保留你上次定的：8~50亿市值、≤20元、剔冲高回落） ----------
results = []
# ... (这里保留你上一版的选股循环逻辑) ...

# ---------- 3. 推送 ----------
token = os.environ.get('PUSHPLUS_TOKEN')
if not token:
    print("未检测到 PUSHPLUS_TOKEN"); raise SystemExit(0)

if not results:
    content = "<h3>📭 今日无符合形态的首板候选</h3><p>已收紧：≤20元 · 8-50亿 · 强行业托底。<br>空仓也是信号。</p>"
else:
    rows = ""
    for i, r in enumerate(results, 1):
        rows += f"""<tr><td>{i}</td><td>{r['name']}<br><small>{r['code']}</small></td>
        <td>{r['ind']}</td><td>{r['close']}</td><td>+{r['pct']}%</td>
        <td>{r['mv']}亿</td><td>{r['score']}</td><td>{r['reason']}</td></tr>"""
    content = f"""
    <h3>🎯 明日首板候选 · {TODAY}</h3>
    <p><small>≤20元 · 市值8-50亿 · 强行业托底 · 缩量不破涨停拉升线 · 剔冲高回落<br>仅供形态参考，非投资建议</small></p>
    <div style="overflow-x:auto;">
    <style>table{{border-collapse:collapse;width:100%}}
    th,td{{border:1px solid #ddd;padding:6px;text-align:center;font-size:12px;white-space:normal;word-break:break-all}}
    th{{background:#f2f2f2}}</style>
    <table>
    <tr><th>#</th><th>股票</th><th>行业</th><th>价</th><th>涨幅</th><th>市值</th><th>分</th><th>理由</th></tr>
    {rows}</table></div>"""

resp = requests.post("https://www.pushplus.plus/send",
                     headers={'Content-Type': 'application/json'},
                     data=json.dumps({"token": token,
                                      "title": f"🎯 明日首板候选 · {TODAY}",
                                      "content": content, "template": "html"}).encode('utf-8'))
print("推送:", resp.status_code, resp.text)
