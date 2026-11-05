import tushare as ts
import os
import requests
import json
import pandas as pd

print("TUSHARE_TOKEN 长度:", len(os.environ.get('TUSHARE_TOKEN', '')))
ts.set_token(os.environ.get('TUSHARE_TOKEN'))
pro = ts.pro_api()

TODAY = pd.Timestamp.today().strftime('%Y%m%d')
N = 35

# ---------- 1. 股票池：主板 + 行业字段 ----------
basic = pro.stock_basic(exchange='', list_status='L',
                        fields='ts_code,name,market,list_date,industry')
pool = basic[
    basic['ts_code'].str.match(r'^(60[0-3]|00[0-3])') &
    (~basic['name'].str.contains(r'ST|退|PT', na=False))
].copy()
pool['list_date'] = pd.to_datetime(pool['list_date'])
pool = pool[pool['list_date'] < pd.Timestamp.today() - pd.Timedelta(days=60)]
# 去掉行业缺失的
pool = pool[pool['industry'].notna()]
print("股票池:", len(pool))

# ---------- 2. 行情 + 基础 ----------
df = pro.daily(trade_date=TODAY)
try:
    bk = pro.daily_basic(trade_date=TODAY,
                         fields='ts_code,close,turnover_rate,volume_ratio,float_mv,total_mv')
    df = df.merge(bk, on='ts_code', how='left')
except Exception as e:
    print("daily_basic 受限:", e)

# ---------- 3. 涨停池 ----------
limit_info = {}
today_limit = set()
try:
    lp = pro.limit_list_d(start_date=(pd.Timestamp.today()-pd.Timedelta(days=32)).strftime('%Y%m%d'),
                          end_date=TODAY)
    lp = lp[lp['limit_times'] >= 1]
    limit_info = (lp.sort_values('trade_date')
                  .groupby('ts_code')
                  .agg(limit_times=('limit_times', 'last'),
                       ldate=('trade_date', 'last')).to_dict('index'))
    today_limit = set(lp[lp['trade_date'] == TODAY]['ts_code'].tolist())
    print("涨停池:", len(limit_info), " 今日涨停:", len(today_limit))
except Exception as e:
    print("limit_list_d 受限，首板判定降级:", e)

# ---------- 4. 行业强度（方案A核心） ----------
# 4.1 当天全行业个股涨跌
df['industry'] = df['ts_code'].map(pool.set_index('ts_code')['industry'])
ind_grp = df.groupby('industry').agg(
    avg_pct=('pct_chg', 'mean'),      # 行业平均涨幅
    up_num=('pct_chg', lambda s: (s >= 9.5).sum()),   # 行业当日封板家数
    cnt=('ts_code', 'count')
)
# 只认有点规模的行业（≥5只票，防妖股行业虚高）
ind_grp = ind_grp[ind_grp['cnt'] >= 5]

def industry_score(ind):
    """强行业加分，弱行业扣分"""
    if ind not in ind_grp.index:
        return -1.0
    r = ind_grp.loc[ind]
    if pd.isna(r['avg_pct']):
        return 0.0
    s = 0.0
    if r['avg_pct'] > 1.5 and r['up_num'] >= 2:      # 强板块：平均涨+封2板以上
        s += 2.5
    elif r['avg_pct'] > 0.5 and r['up_num'] >= 1:    # 中等
        s += 1.0
    elif r['avg_pct'] < 0:                           # 弱板块：整体在跌
        s -= 1.5
    else:
        s -= 0.5                                     # 没涨停撑腰，微罚
    return round(s, 1)

print("强行业TOP5:")
print(ind_grp.sort_values('avg_pct', ascending=False).head(5)[['avg_pct','up_num']])

# ---------- 5. 初筛 ----------
cand = df.merge(pool[['ts_code', 'name', 'industry']], on='ts_code', how='inner')
cand = cand[(cand['pct_chg'] >= 3) & (cand['pct_chg'] < 7)]
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
    close_pos = last['close'] / last['high']

    # ===== 硬门槛 =====
    if last['close'] > 20:                     # 股价≤20
        continue
    if body > 0 and up_shadow > body * 0.4:    # 剔冲高回落
        continue
    if close_pos < 0.97:                       # 收不回高位
        continue
    if last['vol'] > vol_ma5 * 3.5:            # 爆量甩货
        continue
    recent = h.tail(6).iloc[:-1]
    if (recent['high'] - recent[['close','open']].max(axis=1)) \
       .gt(recent['close']*0.06).any():        # 近5日长上影
        continue
    if last['close'] >= h['close'].tail(20).min()*1.25:  # 20日涨超25%高位
        continue
    mv = getattr(r, 'float_mv', None) or getattr(r, 'total_mv', None)
    if mv is not None and not (8 <= mv <= 50): # 市值8~50亿
        continue
    if code in today_limit:                    # 今天已封板的不算候选
        continue

    score = 0.0
    reason = []

    # —— 回调不破涨停拉升线（核心）——
    info = limit_info.get(code)
    if info:
        lhist = h[h['trade_date'] <= info['ldate']]
        if len(lhist):
            base = lhist.iloc[-1]
            body_low = min(base['open'], base['close'])
            since = h[h.index > base.name]
            if len(since) and (since['close'] < body_low).any():
                continue
            if len(since) >= 3 and since['vol'].iloc[-1] < since['vol'].iloc[0]:
                score += 3.0; reason.append("缩量不破线")
            else:
                score += 1.5; reason.append("守线")
            if info.get('limit_times', 9) == 1:
                score += 1.0; reason.append("纯首板")
    else:
        continue

    # 股价偏好
    if last['close'] <= 10:
        score += 2.0; reason.append("10元内")
    elif last['close'] <= 15:
        score += 1.0; reason.append("低价")

    # 均线
    if last['close'] > ma5 > ma10 > ma20:
        score += 2.0; reason.append("多头")
    elif last['close'] > ma20:
        score += 0.5

    # 突破
    if last['close'] >= h['close'].tail(20).max()*0.99:
        score += 1.5; reason.append("突破")

    # 温和放量
    if last['vol'] > vol_ma5*1.5:
        score += 1.0; reason.append("放量")

    # 光头
    if body > 0 and up_shadow < body*0.25:
        score += 1.0; reason.append("光头")

    # —— 行业强度（A方案）——
    iscore = industry_score(r.industry)
    score += iscore
    if iscore >= 2:
        reason.append(f"强板块[{r.industry}]")
    elif iscore < 0:
        reason.append(f"弱板块-{abs(iscore)}")

    results.append({'code': code, 'name': r.name, 'ind': r.industry,
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
    content = "<h3>📭 今日无符合形态的首板候选</h3><p>已收紧：≤20元 · 8-50亿 · 强行业托底 · 不破拉升线。<br>空仓也是信号，别硬凑。</p>"
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
