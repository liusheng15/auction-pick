import tushare as ts
import os
import requests
import json
import pandas as pd

print("TUSHARE_TOKEN 长度:", len(os.environ.get('TUSHARE_TOKEN', '')))
ts.set_token(os.environ.get('TUSHARE_TOKEN'))
pro = ts.pro_api()

TODAY = pd.Timestamp.today().strftime('%Y%m%d')
N = 35  # 回看窗口

# ---------- 1. 股票池：只要主板 ----------
basic = pro.stock_basic(exchange='', list_status='L',
                        fields='ts_code,name,market,list_date')
pool = basic[
    basic['ts_code'].str.match(r'^(60[0-3]|00[0-3])') &      # 主板
    (~basic['name'].str.contains(r'ST|退|PT', na=False))     # 去 ST
].copy()
pool['list_date'] = pd.to_datetime(pool['list_date'])
pool = pool[pool['list_date'] < pd.Timestamp.today() - pd.Timedelta(days=60)]
print("股票池:", len(pool))

# ---------- 2. 行情 + 基础 ----------
df = pro.daily(trade_date=TODAY)
try:
    bk = pro.daily_basic(trade_date=TODAY,
                         fields='ts_code,close,turnover_rate,volume_ratio,float_mv,total_mv')
    df = df.merge(bk, on='ts_code', how='left')
except Exception as e:
    print("daily_basic 受限:", e)

# ---------- 3. 涨停池：拿连板数 + 涨停日 ----------
limit_info = {}   # ts_code -> (limit_times, close)
try:
    lp = pro.limit_list_d(start_date=(pd.Timestamp.today()-pd.Timedelta(days=32)).strftime('%Y%m%d'),
                          end_date=TODAY)
    lp = lp[lp['limit_times'] >= 1]
    # 每只票取最近一次涨停的连板数
    limit_info = (lp.sort_values('trade_date')
                  .groupby('ts_code')
                  .agg(limit_times=('limit_times', 'last'),
                       ldate=('trade_date', 'last')).to_dict('index'))
    print("涨停池:", len(limit_info))
except Exception as e:
    print("limit_list_d 受限，首板判定降级:", e)

# ---------- 4. 板块顺风 ----------
sector_boost = {}
try:
    ths = pro.ths_daily(trade_date=TODAY, fields='ts_code,pct_chg')
    hot = ths[ths['pct_chg'] > 3]['ts_code'].tolist()
    sector_boost = {c: 1.5 for c in hot}
    print("强势板块:", len(sector_boost))
except Exception as e:
    print("板块接口受限，关闭板块加成:", e)

# 个股->板块映射
sec_map = {}
try:
    mm = pro.ths_member(ts_code=','.join(pool['ts_code'].tolist()))
    sec_map = mm.groupby('ts_code')['ts_code_ths'].first().to_dict()
except Exception:
    pass

# ---------- 5. 初筛 ----------
cand = df.merge(pool[['ts_code', 'name']], on='ts_code', how='inner')
cand = cand[(cand['pct_chg'] >= 3) & (cand['pct_chg'] < 7)]      # 点火未涨停
if 'turnover_rate' in cand:
    cand = cand[(cand['turnover_rate'] >= 5) & (cand['turnover_rate'] <= 18)]
if 'volume_ratio' in cand:
    cand = cand[(cand['volume_ratio'] > 1.3) & (cand['volume_ratio'] <= 4)]
print("初筛:", len(cand))

results = []
for r in cand.itertuples():
    code = r.ts_code
    try:
        h = pro.daily(ts_code=code,
                      start_date=(pd.Timestamp.today()-pd.Timedelta(days=N+5)).strftime('%Y%m%d'),
                      end_date=TODAY).sort_values('trade_date').reset_index(drop=True)
    except Exception:
        continue
    if len(h) < 20:
        continue

    last = h.iloc[-1]
    prev = h.iloc[-2]
    ma5, ma10, ma20 = h['close'].tail(5).mean(), h['close'].tail(10).mean(), h['close'].tail(20).mean()
    vol_ma5 = h['vol'].tail(5).mean()
    body = abs(last['close'] - last['open'])
    up_shadow = last['high'] - max(last['close'], last['open'])
    close_pos = last['close'] / last['high']   # 收盘贴近最高价程度

    # ===== 硬门槛：高价 / 冲高回落 / 爆量 =====
    if last['close'] > 20:                     # ① 股价 ≤ 20
        continue
    if body > 0 and up_shadow > body * 0.4:    # ② 当天冲高回落 → 丢
        continue
    if close_pos < 0.97:                       # ③ 收盘没站上高位 → 丢
        continue
    if last['vol'] > vol_ma5 * 3.5:            # ④ 爆量甩货 → 丢
        continue
    # ⑤ 近5日有冲高回落(上影>6%且实体弱) → 丢
    recent = h.tail(6).iloc[:-1]
    if (recent['high'] - recent[['close', 'open']].max(axis=1)) \
       .gt(recent['close'] * 0.06).any():
        continue
    # ⑥ 20日已涨超25% → 高位不接力
    if last['close'] >= h['close'].tail(20).min() * 1.25:
        continue
    # ⑦ 市值：15~80亿，双字段兜底
    mv = getattr(r, 'float_mv', None) or getattr(r, 'total_mv', None)
    if mv is not None and not (15 <= mv <= 80):
        continue

    # ===== 打分 =====
    score = 0.0
    reason = []

    # —— 回调不破涨停拉升线（你的核心逻辑，保留）——
    info = limit_info.get(code)
    if info:
        lhist = h[h['trade_date'] <= info['ldate']]
        if len(lhist):
            base = lhist.iloc[-1]
            body_low = min(base['open'], base['close'])   # 涨停阳线实体底
            since = h[h.index > base.name]
            if len(since) and (since['close'] < body_low).any():
                continue                                   # 跌破 → 结构坏，直接丢
            if len(since) >= 3 and since['vol'].iloc[-1] < since['vol'].iloc[0]:
                score += 3.0; reason.append("缩量不破拉升线")
            else:
                score += 1.5; reason.append("守拉升线")
            # 首板纯净：那次就是单板(非连板)
            if info.get('limit_times', 9) == 1:
                score += 1.0; reason.append("纯首板")
    else:
        continue   # 窗口内完全没涨停过的，按你新思路不收（要的是洗盘再起）

    # 股价偏好
    if last['close'] <= 10:
        score += 2.0; reason.append("低价10元内")
    elif last['close'] <= 15:
        score += 1.0; reason.append("低价")

    # 均线
    if last['close'] > ma5 > ma10 > ma20:
        score += 2.0; reason.append("均线多头")
    elif last['close'] > ma20:
        score += 0.5

    # 平台突破
    if last['close'] >= h['close'].tail(20).max() * 0.99:
        score += 1.5; reason.append("突破")

    # 量能
    if last['vol'] > vol_ma5 * 1.5:
        score += 1.0; reason.append("温和放量")

    # 光头
    if body > 0 and up_shadow < body * 0.25:
        score += 1.0; reason.append("光头")

    # 板块顺风
    sec = sec_map.get(code)
    if sec and sec in sector_boost:
        score += sector_boost[sec]; reason.append("强板块")

    results.append({'code': code, 'name': r.name,
                    'close': round(last['close'], 2),
                    'pct': round(last['pct_chg'], 2),
                    'vr': round(getattr(r, 'volume_ratio', 0), 2),
                    'mv': round(mv, 0) if mv else 0,
                    'score': round(score, 1),
                    'reason': '、'.join(reason)})

results = sorted(results, key=lambda x: -x['score'])[:3]

# ---------- 6. 推送 ----------
token = os.environ.get('PUSHPLUS_TOKEN')
if not token:
    print("未检测到 PUSHPLUS_TOKEN"); raise SystemExit(0)

if not results:
    content = "<h3>📭 今日无符合形态的首板候选</h3><p>条件已收紧（≤20元 / 15-80亿 / 不破拉升线），空仓也是信号。</p>"
else:
    rows = ""
    for i, r in enumerate(results, 1):
        rows += f"""<tr><td>{i}</td><td>{r['name']}<br><small>{r['code']}</small></td>
        <td>{r['close']}</td><td>+{r['pct']}%</td><td>{r['vr']}</td>
        <td>{r['mv']}亿</td><td>{r['score']}</td><td>{r['reason']}</td></tr>"""
    content = f"""
    <h3>🎯 明日首板候选 · {TODAY}</h3>
    <p><small>≤20元 · 市值15-80亿 · 缩量不破涨停拉升线 · 剔除冲高回落<br>仅供形态参考，非投资建议</small></p>
    <div style="overflow-x:auto;">
    <style>table{{border-collapse:collapse;width:100%}}
    th,td{{border:1px solid #ddd;padding:6px;text-align:center;font-size:12px;white-space:normal;word-break:break-all}}
    th{{background:#f2f2f2}}</style>
    <table>
    <tr><th>#</th><th>股票</th><th>价</th><th>涨幅</th><th>量比</th><th>市值</th><th>分</th><th>理由</th></tr>
    {rows}</table></div>"""

resp = requests.post("https://www.pushplus.plus/send",
                     headers={'Content-Type': 'application/json'},
                     data=json.dumps({"token": token,
                                      "title": f"🎯 明日首板候选 · {TODAY}",
                                      "content": content, "template": "html"}).encode('utf-8'))
print("推送:", resp.status_code, resp.text)
