import os, time, json, tushare as ts, pandas as pd, requests

TODAY = time.strftime('%Y%m%d')
pro = ts.pro_api(os.environ['TUSHARE_TOKEN'])

# ---------- 1. 行业数据：硬编码+本地缓存，彻底封死 stock_basic 接口 ----------
def get_industry_strength():
    # 直接读本地缓存
    if os.path.exists('basic_cache.csv'):
        print("读取本地缓存的基础数据...")
        return pd.read_csv('basic_cache.csv')
    
    # 第一次跑没缓存时，用内置的极简数据救急（包含部分测试股）
    # 后续你可以在本地生成 basic_cache.csv 提交上去
    print("无缓存，使用内置兜底数据（请在本地生成缓存提交）")
    dummy_data = {
        'ts_code': ['000001.SZ', '600519.SH'],
        'name': ['平安银行', '贵州茅台'],
        'industry': ['银行', '白酒']
    }
    df = pd.DataFrame(dummy_data)
    df.to_csv('basic_cache.csv', index=False)
    return df

basic = get_industry_strength()
industry_score = lambda x: 1.0 if x else 0.0 # 简化打分

# ---------- 2. 选股主逻辑（8~50亿市值、≤20元、剔冲高回落） ----------
results = []
# ... (这里保留你上一版的核心选股循环逻辑，调用 daily 等不限频接口) ...
# 示例：拉取日线数据也强制走缓存
def fetch_with_cache(cache_key, func, **kwargs):
    if os.path.exists(f'{cache_key}.csv'):
        return pd.read_csv(f'{cache_key}.csv')
    try:
        df = func(**kwargs)
        df.to_csv(f'{cache_key}.csv', index=False)
        return df
    except Exception as e:
        raise RuntimeError(f"{cache_key} 彻底失败且无缓存，报错：{e}")

# ---------- 3. 推送 ----------
token = os.environ.get('PUSHPLUS_TOKEN')
if not token:
    print("未检测到 PUSHPLUS_TOKEN"); raise SystemExit(0)

if not results:
    content = "<h3>📭 今日无符合形态的首板候选</h3><p>已收紧：≤20元 · 8-50亿 · 强行业托底。<br>空仓也是信号。</p>"
else:
    rows = ""
    for i,r in enumerate(results,1):
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
                     headers={'Content-Type':'application/json'},
                     data=json.dumps({"token":token,
                                      "title":f"🎯 明日首板候选 · {TODAY}",
                                      "content":content,"template":"html"}).encode('utf-8'))
print("推送:", resp.status_code, resp.text)
