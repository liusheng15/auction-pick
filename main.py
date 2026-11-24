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

# ========= 1. 涨停池（含连板数，一个接口搞定，不碰 stock_basic） =========
lp = cached(f'limit_{TODAY}',
            lambda: pro.limit_list_d(trade_date=TODAY, limit_type='U'),
            hours=6)
lp = lp[lp['ts_code'].str.match(r'^(60[0-3]|00[0-3])')].copy()
if 'name' in lp.columns:
    lp = lp[~lp['name'].str.contains('ST|退|PT', na=False)]
print("今日主板涨停:", len(lp))
if len(lp)==0:
    raise SystemExit(0)

# ========= 2. 炸板池（算市场情绪） =========
try:
    zb = cached(f'zb_{TODAY}',
                lambda: pro.limit_list_d(trade_date=TODAY, limit_type='Z'),
                hours=6)
    zb_cnt = len(zb)
except Exception:
    zb_cnt = 0
limit_cnt = len(lp)
fail_rate = zb_cnt/(limit_cnt+zb_cnt)*100 if (limit_cnt+zb_cnt) else 50
print(f"涨停{limit_cnt} 炸板{zb_cnt} 炸板率{fail_rate:.0f}%")

# ========= 3. 市场环境分 =========
mkt = 0.0; mkt_reason = []
if limit_cnt > 80 and fail_rate < 20:   mkt = 1.0; mkt_reason.append("情绪高潮")
elif limit_cnt >= 50 and fail_rate < 30: mkt = 0.5; mkt_reason.append("情绪正常")
elif limit_cnt < 40:                     mkt = -1.5; mkt_reason.append("情绪低迷")
elif fail_rate > 30:                     mkt = -1.0; mkt_reason.append("炸板率高")

# ========= 4. 题材梯队（用涨停池自身 industry 字段） =========
ind_cnt = lp.groupby('industry')['ts_code'].count() if 'industry' in lp.columns else pd.Series(dtype=int)
def ind_score(ind):
    if pd.isna(ind) or ind not in ind_cnt.index: return -0.8, "孤板"
    c = ind_cnt[ind]
    if c >= 3: return 2.0, f"梯队{c}家"
    if c == 2: return 1.2, "双龙"
    return -0.8, "孤板"

# ========= 5. 逐只 10 分制打分 =========
rows = []
for r in lp.itertuples():
    s = 0.0; rs = []
    mv = getattr(r,'float_mv',None) or getattr(r,'total_mv',None)
    close = getattr(r,'close',0) or 0
    tr = getattr(r,'turnover_ratio',None)
    lt = int(getattr(r,'limit_times',1) or 1)

    # ① 封板时间 0~2.0
    ft = str(getattr(r,'first_time','') or '150000')
    ft = ft.zfill(6) if ft.isdigit() else '150000'
    if ft == '092500':        s += 2.0; rs.append("一字板")
    elif ft <= '093500':      s += 1.8; rs.append("秒板")
    elif ft <= '103000':      s += 1.4; rs.append("早盘封")
    elif ft <= '140000':      s += 0.6; rs.append("午后板")
    else:                     s += 0.2; rs.append("尾盘板")

    # ② 炸板次数 0~1.5
    ob = int(getattr(r,'open_times',0) or 0)
    if ob == 0:      s += 1.5; rs.append("零炸板")
    elif ob == 1:    s += 1.0
    elif ob == 2:    s += 0.4
    else:            s -= 0.5; rs.append(f"炸{ob}次")

    # ③ 封单厚度 0~1.5
    fd = getattr(r,'fd_amount',0) or 0
    if mv and fd:
        ratio = fd/(mv*1e4)*100 if mv>0 else 0   # fd单位元，float_mv单位万元
        if ratio >= 3:    s += 1.5; rs.append("封单极厚")
        elif ratio >= 1:  s += 1.0; rs.append("封单厚")
        elif ratio < 0.2: s -= 0.5; rs.append("封单弱")

    # ④ 题材梯队
    i_sc, i_rs = ind_score(getattr(r,'industry',None))
    s += i_sc; rs.append(i_rs)

    # ⑤ 换手健康 0~1.0
    if tr is not None:
        if 10 <= tr <= 25:     s += 1.0; rs.append("换手健康")
        elif 5 <= tr < 10:     s += 0.6
        elif 25 < tr <= 40:    s += 0.3
        elif tr > 40:          s -= 0.5; rs.append("换手过大")
        else:                  s += 0.1

    # ⑥ 市值弹性 0~1.0
    if mv:
        if 20 <= mv <= 50:     s += 1.0; rs.append("黄金市值")
        elif 8 <= mv < 20:     s += 0.7
        elif 50 < mv <= 100:   s += 0.4
        elif mv > 100:         s += 0.0; rs.append("盘子大")
    if close and close > 20:   s -= 0.3

    # ⑦ 晋级位置 0~1.0
    if lt >= 4:       s += 1.0; rs.append(f"{lt}进{lt+1}胜率最高")
    elif lt == 3:     s += 1.0; rs.append("3进4")
    elif lt == 2:     s += 0.7; rs.append("2进3")
    else:             s += 0.4; rs.append("1进2")

    # ⑧ 市场环境
    s += mkt

    rows.append({'code':r.ts_code,'name':getattr(r,'name',r.ts_code),
                 'close':round(close,2),'lt':lt,
                 'mv':round(mv,0) if mv else 0,
                 'score':round(min(s,10),1),'reason':'、'.join(rs)})

top = sorted(rows, key=lambda x:-x['score'])[:3]

# ========= 6. 推送 =========
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
    <p><small>涨停{limit_cnt}家 · 炸板率{fail_rate:.0f}% · {' '.join(mkt_reason) if mkt_reason else '情绪中性'}<br>
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
