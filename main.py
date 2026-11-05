import os, time, json, tushare as ts, pandas as pd, requests

print("TUSHARE_TOKEN 长度:", len(os.environ.get('TUSHARE_TOKEN', '')))
pro = ts.pro_api(os.environ.get('TUSHARE_TOKEN'))

TODAY = time.strftime('%Y%m%d')
CACHE_DIR = '.cache'
os.makedirs(CACHE_DIR, exist_ok=True)

def fetch_with_cache(fn_name, cache_key, fetcher, max_age_hours=6, retries=3, sleep_sec=45):
    """
    带本地缓存 + 限频重试的通用拉取器
    - 缓存没过期 → 直接读本地，不调接口
    - 缓存过期/不存在 → 调接口，失败就休眠重试
    """
    path = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    # 1) 命中且未过期
    if os.path.exists(path):
        age_h = (time.time() - os.path.getmtime(path)) / 3600
        if age_h < max_age_hours:
            print(f"[缓存命中] {cache_key} (年龄{age_h:.1f}h)")
            return pd.read_pickle(path)
    # 2) 过期或没有 → 调接口，带重试
    for i in range(retries):
        try:
            df = fetcher()
            df.to_pickle(path)
            print(f"[接口拉取] {cache_key} 成功，已缓存")
            return df
        except Exception as e:
            msg = str(e)
            print(f"[限频/报错] {cache_key} 第{i+1}次失败: {msg[:80]}")
            # 如果是限频，按剩余时间睡；否则短睡
            wait = sleep_sec
            import re
            m = re.search(r'(\d+)次/(\d+)(小时|分钟|min)', msg)
            if m and '小时' in msg:
                wait = int(m.group(2)) * 60  # 按接口要求的小时数换算秒
            time.sleep(wait)
    # 3) 都失败 → 退而用旧缓存（哪怕过期），保证不崩
    if os.path.exists(path):
        print(f"[降级] {cache_key} 用旧缓存兜底")
        return pd.read_pickle(path)
    raise RuntimeError(f"{cache_key} 彻底失败且无缓存")

# ================= 1. 股票池（缓存，6小时） =================
basic = fetch_with_cache(
    'stock_basic', 'basic',
    lambda: pro.stock_basic(exchange='', list_status='L',
                            fields='ts_code,name,market,list_date,industry'),
    max_age_hours=6)

pool = basic[
    basic['ts_code'].str.match(r'^(60[0-3]|00[0-3])') &
    (~basic['name'].str.contains(r'ST|退|PT', na=False))
].copy()
pool['list_date'] = pd.to_datetime(pool['list_date'])
pool = pool[pool['list_date'] < pd.Timestamp.today() - pd.Timedelta(days=60)]
pool = pool[pool['industry'].notna()]
print("股票池:", len(pool))

# ================= 2. 当日行情 + 基础（缓存，2小时，盘中会变所以短点） =================
df = fetch_with_cache(
    'daily', f'daily_{TODAY}',
    lambda: pro.daily(trade_date=TODAY),
    max_age_hours=2)

try:
    bk = fetch_with_cache(
        'daily_basic', f'basic_{TODAY}',
        lambda: pro.daily_basic(trade_date=TODAY,
                                fields='ts_code,close,turnover_rate,volume_ratio,float_mv,total_mv'),
        max_age_hours=2)
    df = df.merge(bk, on='ts_code', how='left')
except Exception as e:
    print("daily_basic 缓存降级:", e)

# ================= 3. 涨停池（缓存，6小时） =================
limit_info = {}
today_limit = set()
def load_limit():
    start = (pd.Timestamp.today() - pd.Timedelta(days=32)).strftime('%Y%m%d')
    lp = pro.limit_list_d(start_date=start, end_date=TODAY)
    return lp[lp['limit_times'] >= 1]

try:
    lp_all = fetch_with_cache('limit_list', f'limit_{TODAY}', load_limit, max_age_hours=6)
    limit_info = (lp_all.sort_values('trade_date')
                  .groupby('ts_code')
                  .agg(limit_times=('limit_times', 'last'),
                       ldate=('trade_date', 'last')).to_dict('index'))
    today_limit = set(lp_all[lp_all['trade_date'] == TODAY]['ts_code'].tolist())
    print("涨停池:", len(limit_info), " 今日封板:", len(today_limit))
except Exception as e:
    print("涨停池缓存降级:", e)

# ================= 4. 行业强度（方案A，基于缓存的当日行情算） =================
df_tmp = df.copy()
df_tmp['industry'] = df_tmp['ts_code'].map(pool.set_index('ts_code')['industry'])
ind_grp = df_tmp.groupby('industry').agg(
    avg_pct=('pct_chg', 'mean'),
    up_num=('pct_chg', lambda s: (s >= 9.5).sum()),
    cnt=('ts_code', 'count')
).reset_index()
ind_grp = ind_grp[ind_grp['cnt'] >= 5]
ind_map = ind_grp.set_index('industry')

def industry_score(ind):
    if ind not in ind_map.index:
        return -1.0
    r = ind_map.loc[ind]
    if pd.isna(r['avg_pct']):
        return 0.0
    if r['avg_pct'] > 1.5 and r['up_num'] >= 2:
        return 2.5
    elif r['avg_pct'] > 0.5 and r['up_num'] >= 1:
        return 1.0
    elif r['avg_pct'] < 0:
        return -1.5
    else:
        return -0.5

print("强行业TOP5:")
print(ind_grp.sort_values('avg_pct', ascending=False).head(5)[['industry','avg_pct','up_num']].to_string(index=False))

# ================= 5. 逐只深度打分 =================
cand = df.merge(pool[['ts_code','name','industry']], on='ts_code', how='inner')
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
        # 单只日线也做短缓存（1小时），调条件狂点也不怕
        h = fetch_with_cache(
            'daily_hist', f'hist_{code}',
            lambda c=code: pro.daily(
                ts_code=c,
                start_date=(pd.Timestamp.today()-pd.Timedelta(days=40)).strftime('%Y%m%d'),
                end_date=TODAY).sort_values('trade_date').reset_index(drop=True),
            max_age_hours=1)
    except Exception:
        continue
    if len(h) < 20:
        continue

    last, prev = h.iloc[-1], h.iloc[-2]
    ma5, ma10, ma20 = h['close'].tail(5).mean(), h['close'].tail(10).mean(), h['close'].tail(20).mean()
    vol_ma5 = h['vol'].tail(5).mean()
    body = abs(last['close'] - last['open'])
    up_shadow = last['high'] - max(last['close'], last['open'])
    close_pos = last['close'] / last['high']

    # ---- 硬门槛 ----
    if last['close'] > 20: continue
    if body > 0 and up_shadow > body*0.4: continue
    if close_pos < 0.97: continue
    if last['vol'] > vol_ma5*3.5: continue
    recent = h.tail(6).iloc[:-1]
    if (recent['high'] - recent[['close','open']].max(axis=1)).gt(recent['close']*0.06).any(): continue
    if last['close'] >= h['close'].tail(20).min()*1.25: continue
    mv = getattr(r,'float_mv',None) or getattr(r,'total_mv',None)
    if mv is not None and not (8 <= mv <= 50): continue
    if code in today_limit: continue

    score, reason = 0.0, []

    # 回调不破涨停拉升线
    info = limit_info.get(code)
    if info:
        lhist = h[h['trade_date'] <= info['ldate']]
        if len(lhist):
            base = lhist.iloc[-1]; body_low = min(base['open'], base['close'])
            since = h[h.index > base.name]
            if len(since) and (since['close'] < body_low).any(): continue
            if len(since)>=3 and since['vol'].iloc[-1] < since['vol'].iloc[0]:
                score += 3.0; reason.append("缩量不破线")
            else:
                score += 1.5; reason.append("守线")
            if info.get('limit_times',9)==1: score += 1.0; reason.append("纯首板")
    else:
        continue

    if last['close'] <= 10: score += 2.0; reason.append("10元内")
    elif last['close'] <= 15: score += 1.0; reason.append("低价")

    if last['close'] > ma5 > ma10 > ma20: score += 2.0; reason.append("多头")
    elif last['close'] > ma20: score += 0.5

    if last['close'] >= h['close'].tail(20).max()*0.99: score += 1.5; reason.append("突破")
    if last['vol'] > vol_ma5*1.5: score += 1.0; reason.append("放量")
    if body > 0 and up_shadow < body*0.25: score += 1.0; reason.append("光头")

    iscore = industry_score(r.industry); score += iscore
    if iscore >= 2: reason.append(f"强板块[{r.industry}]")
    elif iscore < 0: reason.append(f"弱板块{iscore}")

    results.append({'code':code,'name':r.name,'ind':r.industry,
                    'close':round(last['close'],2),'pct':round(last['pct_chg'],2),
                    'vr':round(getattr(r,'volume_ratio',0),2),
                    'mv':round(mv,0) if mv else 0,
                    'score':round(score,1),'reason':'、'.join(reason)})

results = sorted(results, key=lambda x:-x['score'])[:3]

# ================= 6. 推送 =================
token = os.environ.get('PUSHPLUS_TOKEN')
if not token:
    print("未检测到 PUSHPLUS_TOKEN"); raise SystemExit(0)

if not results:
    content = "<h3>📭 今日无符合形态的首板候选</h3><p>已收紧：≤20元 · 8-50亿 · 强行业托底 · 不破拉升线。<br>空仓也是信号。</p>"
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
