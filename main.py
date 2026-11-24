import os, time, tushare as ts, pandas as pd, requests

print("TUSHARE_TOKEN 长度:", len(os.environ.get('TUSHARE_TOKEN','')))
pro = ts.pro_api(os.environ.get('TUSHARE_TOKEN'))
TODAY = time.strftime('%Y%m%d')
CACHE = '.cache'; os.makedirs(CACHE, exist_ok=True)

def cached(key, fetcher, hours=6):
    path = f'{CACHE}/{key}.pkl'
    if os.path.exists(path):
        age = (time.time()-os.path.getmtime(path))/3600
        if age < hours:
            print(f"[缓存] {key} 命中")
            return pd.read_pickle(path)
    try:
        df = fetcher(); df.to_pickle(path)
        print(f"[接口] {key} 拉取成功")
        return df
    except Exception as e:
        print(f"[报错] {key}: {str(e)[:60]}")
        if os.path.exists(path):
            return pd.read_pickle(path)
        raise

# ========= 1. 股票池（缓存，只拉一次） =========
basic = cached('basic', lambda: pro.stock_basic(
    exchange='', list_status='L', fields='ts_code,name,industry,list_date'), hours=24)
pool = basic[
    basic['ts_code'].str.match(r'^(60[0-3]|00[0-3])') &
    (~basic['name'].str.contains('ST|退|PT', na=False))
].copy()
pool['list_date'] = pd.to_datetime(pool['list_date'])
pool = pool[pool['list_date'] < pd.Timestamp.today()-pd.Timedelta(days=60)]
print("股票池:", len(pool))

# ========= 2. 当日行情 + 基础指标（全市场，一次拿全） =========
df = cached(f'daily_{TODAY}', lambda: pro.daily(trade_date=TODAY), hours=2)
try:
    bk = cached(f'basic_{TODAY}', lambda: pro.daily_basic(trade_date=TODAY,
        fields='ts_code,turnover_rate,volume_ratio,float_mv,total_mv'), hours=2)
    df = df.merge(bk, on='ts_code', how='left')
except Exception as e:
    print("daily_basic 不可用:", e)

df = df.merge(pool[['ts_code','name','industry']], on='ts_code', how='inner')

# ========= 3. 自己判断涨停（主板 pct_chg>=9.5 且收盘=最高） =========
df['is_limit'] = (df['pct_chg'] >= 9.5) & (abs(df['close']-df['high']) < 0.01)
limit_today = df[df['is_limit']].copy()
print("今日主板涨停(自算):", len(limit_today))

# 市场情绪：涨停家数
limit_cnt = len(limit_today)
if limit_cnt > 80:      mkt, mkt_rs = 1.0, "情绪高潮"
elif limit_cnt >= 50:   mkt, mkt_rs = 0.5, "情绪正常"
elif limit_cnt < 40:    mkt, mkt_rs = -1.5, "情绪低迷"
else:                   mkt, mkt_rs = 0.0, "情绪中性"

# 题材梯队：同行业涨停家数
ind_cnt = limit_today.groupby('industry')['ts_code'].count()
def ind_score(ind):
    if pd.isna(ind) or ind not in ind_cnt.index: return -0.8, "孤板"
    c = ind_cnt[ind]
    if c >= 3: return 2.0, f"梯队{c}家"
    if c == 2: return 1.2, "双龙"
    return -0.8, "孤板"

if len(limit_today)==0:
    raise SystemExit(0)

# ========= 4. 逐只：拉日线判连板 + 10分制打分 =========
rows = []
for r in limit_today.itertuples():
    code = r.ts_code
    h = cached(f'hist_{code}', lambda c=code: pro.daily(ts_code=c,
        start_date=(pd.Timestamp.today()-pd.Timedelta(days=45)).strftime('%Y%m%d'),
        end_date=TODAY).sort_values('trade_date').reset_index(drop=True), hours=1)
    if len(h) < 5: continue

    last = h.iloc[-1]
    # ---- 算连板数：往前每天是否涨停 ----
    lt = 0
    for i in range(len(h)-1, -1, -1):
        row = h.iloc[i]
        if row['pct_chg'] >= 9.5 and abs(row['close']-row['high']) < 0.01:
            lt += 1
        else:
            break
    if lt == 0: lt = 1

    s = 0.0; rs = []
    mv = getattr(r,'float_mv',None) or getattr(r,'total_mv',None)
    tr = getattr(r,'turnover_ratio',None)
    vol_ma5 = h['vol'].tail(6).iloc[:-1].mean()

    # ① 封板形态（用日线近似）0~2.0
    if last['open']==last['close']==last['high']==last['low']:
        s += 2.0; rs.append("一字板")
    elif abs(last['open']-last['high'])<0.01 and abs(last['close']-last['high'])<0.01:
        s += 1.6; rs.append("开盘秒板")
    elif abs(last['close']-last['high'])<0.01:
        s += 1.2; rs.append("光头板")
    elif last['low'] < last['open'] and abs(last['close']-last['high'])<0.01:
        s += 1.0; rs.append("换手板")
    else:
        s += 0.5; rs.append("普通板")

    # ② 量能质量（近似封板扎实度）0~1.5
    if vol_ma5 and last['vol'] < vol_ma5*0.8:
        s += 1.5; rs.append("缩量惜售")
    elif vol_ma5 and last['vol'] < vol_ma5*1.5:
        s += 1.0
    elif vol_ma5 and last['vol'] > vol_ma5*2.5:
        s -= 0.5; rs.append("爆量分歧")

    # ③ 换手健康 0~1.0（近似封单/筹码）
    if tr is not None:
        if 10 <= tr <= 25:     s += 1.0; rs.append("换手健康")
        elif 5 <= tr < 10:     s += 0.6
        elif 25 < tr <= 40:    s += 0.3
        elif tr > 40:          s -= 0.5; rs.append("换手过大")

    # ④ 题材梯队
    i_sc, i_rs = ind_score(getattr(r,'industry',None))
    s += i_sc; rs.append(i_rs)

    # ⑤ 市值弹性 0~1.0
    if mv:
        if 20 <= mv <= 50:     s += 1.0; rs.append("黄金市值")
        elif 8 <= mv < 20:     s += 0.7
        elif 50 < mv <= 100:   s += 0.4
        elif mv > 100:         s -= 0.3; rs.append("盘子大")
    if getattr(r,'close',0) > 20: s -= 0.3

    # ⑥ 晋级位置 0~1.5（板越高胜率越高）
    if lt >= 4:       s += 1.5; rs.append(f"{lt}板高标")
    elif lt == 3:     s += 1.3; rs.append("3板")
    elif lt == 2:     s += 0.9; rs.append("2板")
    else:             s += 0.4; rs.append("首板")

    # ⑦ 均线多头 0~1.0
    if len(h)>=20 and last['close']>h['close'].tail(5).mean()>h['close'].tail(20).mean():
        s += 1.0; rs.append("多头")

    # ⑧ 市场环境
    s += mkt

    rows.append({'code':code,'name':getattr(r,'name',code),
                 'close':round(last['close'],2),'lt':lt,
                 'mv':round(mv,0) if mv else 0,
                 'score':round(min(max(s,0),10),1),'reason':'、'.join(rs)})

top = sorted(rows, key=lambda x:-x['score'])[:3]

# ========= 5. 推送 =========
token = os.environ.get('PUSHPLUS_TOKEN')
if not token: raise SystemExit(0)

def grade(sc):
    if sc >= 8:   return "🟢 重仓可上"
    if sc >= 6.5: return "🟡 正常仓位"
    if sc >= 5:   return "🟠 轻仓试错"
    return "⚪ 空仓别上"

if not top:
    content = "<h3>📭 今日无连板候选</h3>"
else:
    body = ""
    for i,x in enumerate(top,1):
        body += f"""<tr><td>{i}</td><td>{x['name']}<br><small>{x['code']}</small></td>
        <td>{x['close']}</td><td>{x['lt']}板</td><td>{x['mv']}亿</td>
        <td><b>{x['score']}</b></td><td>{grade(x['score'])}</td><td>{x['reason']}</td></tr>"""
    content = f"""
    <h3>🔥 连板晋级评分 · {TODAY}</h3>
    <p><small>涨停{limit_cnt}家 · {mkt_rs}（无limit_list_d权限，封板时间/封单用日线近似）<br>
    评分：≥8重仓 / 6.5-8正常 / 5-6.5轻仓 / &lt;5空仓<br>
    历史统计 3进4约47%、4进5约52%，但次日期望收益为负，仅供形态参考</small></p>
    <div style="overflow-x:auto;">
    <style>table{{border-collapse:collapse;width:100%}}
    th,td{{border:1px solid #ddd;padding:6px;text-align:center;font-size:12px;white-space:normal;word-break:break-all}}
    th{{background:#f2f2f2}}</style>
    <table>
    <tr><th>#</th><th>股票</th><th>收盘</th><th>连板</th><th>市值</th><th>分</th><th>建议</th><th>理由</th></tr>
    {body}</table></div>"""

requests.post("https://www.pushplus.plus/send",
              headers={'Content-Type':'application/json'},
              data=json.dumps({"token":token,
                               "title":f"🔥 连板评分 · {TODAY} · {len(top)}只",
                               "content":content,"template":"html"}).encode('utf-8'))
print("推送完成")
