import tushare as ts
import os
import requests
import json
import pandas as pd
from datetime import datetime, timedelta

print("TUSHARE_TOKEN 长度:", len(os.environ.get('TUSHARE_TOKEN', '')))
ts.set_token(os.environ.get('TUSHARE_TOKEN'))
pro = ts.pro_api()

TODAY = datetime.now().strftime('%Y%m%d')
N = 30  # 回看窗口

# ---------- 1. 股票池 ----------
try:
    pool = pro.stock_basic(exchange='', list_status='L',
                           fields='ts_code,name,area,industry,list_date,market')
except Exception as e:
    print("stock_basic 失败:", e)
    raise SystemExit(1)

pool = pool[pool['ts_code'].str.match(r'^(60[0-3]|60[5-9]|00[0-3])\d{3}')]
pool = pool[~pool['name'].str.contains('ST|退|PT', na=False)]
pool = pool[pool['ts_code'].str[:2].isin(['60', '00'])]
pool = pool[pool['market'].isin(['主板', 'Main', 'main', 1, 2]) |
            (~pool['ts_code'].str.startswith(('30', '68', '8', '4')))]
pool = pool[pool['list_date'] < (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')]
print("股票池数量:", len(pool))

# ---------- 2. 行情 + 基础数据 ----------
df = pro.daily(trade_date=TODAY)
try:
    bk = pro.daily_basic(trade_date=TODAY,
                         fields='ts_code,turnover_rate,volume_ratio,float_mv,pe')
    df = df.merge(bk, on='ts_code', how='left')
except Exception as e:
    print("daily_basic 受限，降级:", e)

# ---------- 3. 涨停池（判定连板/首板） ----------
limit_times = {}
try:
    lp = pro.limit_list_d(trade_date=TODAY)
    limit_times = (lp[lp['limit_times'] >= 1]
                   .groupby('ts_code')['limit_times'].max().to_dict())
    print("当日涨停家数:", len(limit_times))
except Exception as e:
    print("limit_list_d 受限，首板判定降级为纯形态:", e)

# ---------- 4. 板块强弱（同花顺概念/行业日线） ----------
sector_boost = {}
try:
    th = pro.ths_daily(trade_date=TODAY,
                       fields='ts_code,close,pct_chg,up_num,down_num')
    th['pct_chg'] = pd.to_numeric(th['pct_chg'], errors='coerce')
    th = th.dropna(subset=['pct_chg'])
    # 近3日累计强度：用 today-1 ~ today-3 的 pct_chg 求和
    strong = []
    for code in th['ts_code'].unique():
        hist = pro.ths_daily(ts_code=code, start_date=(datetime.now()-timedelta(days=6)).strftime('%Y%m%d'),
                             end_date=(datetime.now()-timedelta(days=1)).strftime('%Y%m%d'),
                             fields='ts_code,trade_date,pct_chg')
        if len(hist) >= 2:
            momentum = hist['pct_chg'].astype(float).tail(3).sum()
            strong.append((code, momentum))
    if strong:
        s = pd.DataFrame(strong, columns=['sec', 'mom'])
        thr = s['mom'].quantile(0.80)
        sector_boost = {r.sec: min((r.mom - thr) / 3, 3.0) for r in s.itertuples() if r.mom > thr}
    print("强势板块数:", len(sector_boost))
except Exception as e:
    print("ths_daily 受限，关闭板块加成:", e)

# 个股 -> 板块映射（同花顺概念归属）
sec_map = {}
try:
    mm = pro.ths_member(ts_code=','.join(pool['ts_code'].tolist()))
    sec_map = (mm.groupby('ts_code')['ts_code_ths'].first().to_dict())
except Exception as e:
    print("ths_member 受限，板块映射跳过:", e)

# ---------- 5. 候选初筛 ----------
cand = df.merge(pool[['ts_code', 'name', 'industry']], on='ts_code', how='inner')
cand = cand[(cand['pct_chg'] >= 3) & (cand['pct_chg'] < 7)]   # 点火未涨停
if 'turnover_rate' in cand:
    cand = cand[(cand['turnover_rate'] >= 5) & (cand['turnover_rate'] <= 25)]
if 'volume_ratio' in cand:
    cand = cand[cand['volume_ratio'] > 1.5]
if 'float_mv' in cand:
    cand = cand[(cand['float_mv'] >= 35) & (cand['float_mv'] <= 150)]
cand = cand[~cand['ts_code'].isin(limit_times)]              # 今天没封板
cand['ts_code'].tolist()
print("初筛候选:", len(cand))

# ---------- 6. 逐只深度打分 ----------
results = []
for r in cand.itertuples():
    code = r.ts_code
    try:
        h = pro.daily(ts_code=code, start_date=(datetime.now()-timedelta(days=N+5)).strftime('%Y%m%d'),
                      end_date=TODAY)
        h = h.sort_values('trade_date').reset_index(drop=True)
    except Exception:
        continue
    if len(h) < 15:
        continue

    last = h.iloc[-1]
    prev = h.iloc[-2]
    ma5, ma10, ma20 = h['close'].tail(5).mean(), h['close'].tail(10).mean(), h['close'].tail(20).mean()
    vol_ma5 = h['vol'].tail(5).mean()

    # —— 回调不破涨停拉升线 ——
    up_days = h[(h['pct_chg'] >= 9.5) & (h['close'] > h['open'])]
    guard_ok = True
    pullback_shrink = False
    if len(up_days):
        base = up_days.iloc[-1]                       # 最近一次涨停阳线
        body_low = min(base['open'], base['close'])   # 实体底部 = 拉升线
        since = h[h.index > base.name]
        if len(since) >= 3 and (since['close'] < body_low).any():
            guard_ok = False                           # 跌破 = 结构坏
        # 缩量回调判定：涨停后量能逐级缩小
        if len(since) >= 3:
            post_vol = since['vol'].tolist()
            pullback_shrink = all(post_vol[i] <= post_vol[i-1]*1.05 for i in range(1, len(post_vol)))
    else:
        guard_ok = False                               # 窗口内无涨停，按你要求不收

    if not guard_ok:
        continue

    score = 0.0
    reason = []

    # 结构分
    score += 3.0; reason.append("不破前涨停拉升线")
    if pullback_shrink:
        score += 2.0; reason.append("缩量回调洗盘")

    # 均线
    if last['close'] > ma5 > ma10 > ma20:
        score += 2.5; reason.append("均线多头")
    elif last['close'] > ma20:
        score += 1.0

    # 平台突破：收盘创 20 日新高
    if last['close'] >= h['close'].tail(20).max() * 0.99:
        score += 2.0; reason.append("平台突破")

    # 量能
    if last['vol'] > vol_ma5 * 1.5:
        score += 1.5; reason.append("放量启动")
    if hasattr(r, 'volume_ratio') and r.volume_ratio > 2:
        score += 0.5

    # K线质量：实体长、上影短
    body = abs(last['close'] - last['open'])
    up_shadow = last['high'] - max(last['close'], last['open'])
    if body > 0 and up_shadow < body * 0.3:
        score += 1.0; reason.append("光头强势")

    # 低位启动：5日累计没大涨
    if h['pct_chg'].tail(5).sum() < 15:
        score += 1.0

    # —— 板块顺风 ——
    sec = sec_map.get(code)
    if sec and sec in sector_boost:
        score += sector_boost[sec]
        reason.append(f"强势板块+{sector_boost[sec]:.1f}")

    results.append({
        'code': code, 'name': r.name,
        'close': round(last['close'], 2),
        'pct': round(last['pct_chg'], 2),
        'vr': round(getattr(r, 'volume_ratio', 0), 2),
        'turn': round(getattr(r, 'turnover_rate', 0), 1),
        'score': round(score, 1),
        'reason': '、'.join(reason),
    })

results = sorted(results, key=lambda x: -x['score'])[:3]

# ---------- 7. 推送 ----------
token = os.environ.get('PUSHPLUS_TOKEN')
if not token:
    print("未检测到 PUSHPLUS_TOKEN"); raise SystemExit(0)

if not results:
    content = "<h3>📭 今日无符合形态的首板候选</h3><p>条件较严，属于正常。明天再战。</p>"
else:
    rows = ""
    for i, r in enumerate(results, 1):
        rows += f"""<tr>
        <td><b>{i}</b></td><td>{r['name']}<br><small>{r['code']}</small></td>
        <td>{r['close']}</td><td>+{r['pct']}%</td><td>{r['vr']}</td>
        <td>{r['score']}</td><td>{r['reason']}</td></tr>"""
    content = f"""
    <h3>🎯 明日首板候选 · {TODAY}</h3>
    <p><small>回调不破涨停拉升线 + 缩量洗盘 + 板块顺风 · 仅供形态参考，非投资建议</small></p>
    <div style="overflow-x:auto;">
    <style>table{{border-collapse:collapse;width:100%}}
    th,td{{border:1px solid #ddd;padding:5px;white-space:nowrap;font-size:13px}}
    th{{background:#f2f2f2}}</style>
    <table>
    <tr><th>#</th><th>股票</th><th>收盘</th><th>涨幅</th><th>量比</th><th>分</th><th>入选理由</th></tr>
    {rows}</table></div>"""

url = "https://www.pushplus.plus/send"
resp = requests.post(url, headers={'Content-Type': 'application/json'},
                     data=json.dumps({"token": token,
                                      "title": f"🎯 明日首板候选 · {TODAY}",
                                      "content": content, "template": "html"}).encode('utf-8'))
print("推送:", resp.status_code, resp.text)
