import os, time, json, traceback, tushare as ts, pandas as pd, requests

print("TUSHARE_TOKEN 长度:", len(os.environ.get('TUSHARE_TOKEN','')))
print("版本: 20261125-v7 (浅缩进·无外层try·手机友好)")
pro = ts.pro_api(os.environ.get('TUSHARE_TOKEN'))
TODAY = time.strftime('%Y%m%d')
CACHE = '.cache'; os.makedirs(CACHE, exist_ok=True)

INDUSTRY_MAP = {
"000001.SZ":"银行","000002.SZ":"房地产","000063.SZ":"通信设备","000066.SZ":"计算机设备",
"000100.SZ":"光学光电子","000157.SZ":"工程机械","000333.SZ":"白色家电","000338.SZ":"汽车零部件",
"000425.SZ":"工程机械","000538.SZ":"中药","000568.SZ":"白酒","000596.SZ":"白酒",
"000625.SZ":"汽车整车","000651.SZ":"白色家电","000661.SZ":"生物制品","000708.SZ":"钢铁",
"000725.SZ":"光学光电子","000768.SZ":"军工","000776.SZ":"证券","000786.SZ":"建筑材料",
"000792.SZ":"化肥","000800.SZ":"汽车整车","000813.SZ":"化学制药","000825.SZ":"钢铁",
"000858.SZ":"白酒","000876.SZ":"农牧饲渔","000895.SZ":"食品加工","000938.SZ":"计算机设备",
"000963.SZ":"化学制药","001979.SZ":"房地产","002001.SZ":"化学制药","002008.SZ":"通用设备",
"002007.SZ":"生物制品","002027.SZ":"文化传媒","002030.SZ":"医疗器械","002049.SZ":"半导体",
"002050.SZ":"汽车零部件","002064.SZ":"化学制品","002074.SZ":"电池","002081.SZ":"装修装饰",
"002092.SZ":"化学原料","002129.SZ":"光伏设备","002142.SZ":"银行","002153.SZ":"软件服务",
"002156.SZ":"半导体","002157.SZ":"农牧饲渔","002179.SZ":"军工电子","002180.SZ":"计算机设备",
"002185.SZ":"半导体","002202.SZ":"风电设备","002214.SZ":"军工电子","002230.SZ":"软件服务",
"002236.SZ":"计算机设备","002241.SZ":"消费电子","002252.SZ":"生物制品","002271.SZ":"建筑材料",
"002273.SZ":"光学光电子","002304.SZ":"白酒","002311.SZ":"农牧饲渔","002312.SZ":"化学制品",
"002352.SZ":"物流","002371.SZ":"半导体","002384.SZ":"电子元件","002402.SZ":"消费电子",
"002405.SZ":"软件服务","002410.SZ":"软件服务","002415.SZ":"计算机设备","002422.SZ":"化学制药",
"002430.SZ":"专用设备","002436.SZ":"半导体","002456.SZ":"光学光电子","002460.SZ":"能源金属",
"002463.SZ":"半导体","002475.SZ":"消费电子","002493.SZ":"石化","002497.SZ":"化学制品",
"002508.SZ":"厨卫电器","002517.SZ":"游戏","002555.SZ":"游戏","002558.SZ":"游戏",
"002568.SZ":"饮料乳品","002572.SZ":"家居用品","002594.SZ":"汽车整车","002600.SZ":"消费电子",
"002601.SZ":"化学原料","002602.SZ":"游戏","002603.SZ":"中药","002625.SZ":"军工",
"002648.SZ":"化学原料","002653.SZ":"化学制药","002714.SZ":"农牧饲渔","002736.SZ":"证券",
"002739.SZ":"影视院线","002745.SZ":"光学光电子","002773.SZ":"化学制药","002812.SZ":"电池",
"002821.SZ":"医疗研发外包","002831.SZ":"包装印刷","002841.SZ":"消费电子","002847.SZ":"休闲食品",
"002850.SZ":"电池","002851.SZ":"电源设备","002920.SZ":"汽车零部件","002938.SZ":"半导体",
"002966.SZ":"银行","002970.SZ":"计算机设备","002973.SZ":"环保","002975.SZ":"自动化设备",
"002977.SZ":"军工电子","002979.SZ":"自动化设备","002981.SZ":"消费电子","002983.SZ":"光学光电子",
"002985.SZ":"军工","002987.SZ":"软件服务","002988.SZ":"工业金属","002990.SZ":"计算机设备",
"002991.SZ":"休闲食品","002993.SZ":"消费电子","002996.SZ":"工业金属","002997.SZ":"汽车零部件",
"003000.SZ":"休闲食品","003001.SZ":"专业工程","003002.SZ":"化学制品","003003.SZ":"包装印刷",
"003005.SZ":"软件服务","003006.SZ":"个护用品","003009.SZ":"航天装备","003010.SZ":"互联网电商",
"003012.SZ":"建筑材料","003015.SZ":"光学光电子","003021.SZ":"自动化设备","003022.SZ":"化学原料",
"003024.SZ":"医疗器械","003025.SZ":"通用设备","003026.SZ":"半导体","003028.SZ":"消费电子",
"600000.SH":"银行","600009.SH":"机场航运","600010.SH":"钢铁","600011.SH":"电力",
"600015.SH":"银行","600016.SH":"银行","600018.SH":"港口航运","600019.SH":"钢铁",
"600021.SH":"电力","600025.SH":"电力","600028.SH":"石化","600029.SH":"机场航运",
"600030.SH":"证券","600031.SH":"工程机械","600036.SH":"银行","600038.SH":"军工",
"600039.SH":"工程建设","600048.SH":"房地产","600050.SH":"通信服务","600055.SH":"医疗器械",
"600057.SH":"物流","600059.SH":"饮料乳品","600060.SH":"家电","600061.SH":"多元金融",
"600062.SH":"化学制药","600066.SH":"汽车整车","600072.SH":"船舶制造","600079.SH":"化学制药",
"600085.SH":"中药","600089.SH":"电网设备","600096.SH":"化肥","600100.SH":"计算机设备",
"600104.SH":"汽车整车","600109.SH":"证券","600111.SH":"小金属","600115.SH":"机场航运",
"600118.SH":"航天装备","600126.SH":"钢铁","600129.SH":"中药","600132.SH":"饮料乳品",
"600150.SH":"船舶制造","600153.SH":"物流","600160.SH":"化学制品","600161.SH":"生物制品",
"600166.SH":"汽车整车","600170.SH":"工程建设","600171.SH":"半导体","600176.SH":"玻璃玻纤",
"600177.SH":"服装家纺","600183.SH":"半导体","600188.SH":"煤炭","600196.SH":"化学制药",
"600197.SH":"白酒","600199.SH":"白酒","600201.SH":"生物制品","600206.SH":"半导体",
"600210.SH":"包装印刷","600216.SH":"化学制药","600219.SH":"工业金属","600221.SH":"机场航运",
"600233.SH":"物流","600236.SH":"电力","600252.SH":"中药","600256.SH":"石化",
"600258.SH":"酒店餐饮","600259.SH":"小金属","600276.SH":"化学制药","600282.SH":"钢铁",
"600298.SH":"食品加工","600309.SH":"化学制品","600312.SH":"电网设备","600315.SH":"个护用品",
"600316.SH":"军工","600320.SH":"工程机械","600323.SH":"环保","600329.SH":"中药",
"600332.SH":"中药","600346.SH":"石化","600348.SH":"煤炭","600352.SH":"化学制品",
"600362.SH":"有色","600369.SH":"证券","600372.SH":"军工电子","600376.SH":"房地产",
"600380.SH":"化学制药","600383.SH":"房地产","600388.SH":"环保","600398.SH":"服装家纺",
"600406.SH":"电网设备","600409.SH":"化学制品","600415.SH":"零售","600418.SH":"汽车整车",
"600426.SH":"化学制品","600436.SH":"中药","600438.SH":"光伏设备","600446.SH":"软件服务",
"600460.SH":"半导体","600475.SH":"环保","600480.SH":"汽车零部件","600482.SH":"船舶制造",
"600487.SH":"通信设备","600498.SH":"通信设备","600519.SH":"白酒","600522.SH":"通信设备",
"600528.SH":"工程机械","600535.SH":"中药","600536.SH":"软件服务","600547.SH":"有色",
"600549.SH":"小金属","600570.SH":"软件服务","600584.SH":"半导体","600585.SH":"建筑材料",
"600588.SH":"软件服务","600598.SH":"农牧饲渔","600600.SH":"饮料乳品","600612.SH":"珠宝首饰",
"600660.SH":"汽车零部件","600663.SH":"房地产","600690.SH":"家电","600702.SH":"白酒",
"600703.SH":"半导体","600718.SH":"软件服务","600732.SH":"光伏设备","600733.SH":"汽车整车",
"600741.SH":"汽车零部件","600745.SH":"半导体","600754.SH":"酒店餐饮","600760.SH":"军工",
"600761.SH":"工程机械","600763.SH":"医疗服务","600779.SH":"白酒","600795.SH":"电力",
"600809.SH":"白酒","600812.SH":"化学制药","600837.SH":"证券","600839.SH":"家电",
"600859.SH":"零售","600887.SH":"饮料乳品","600893.SH":"航天装备","600900.SH":"电力",
"600905.SH":"风电设备","601088.SH":"煤炭","601111.SH":"机场航运","601138.SH":"消费电子",
"601166.SH":"银行","601211.SH":"证券","601225.SH":"煤炭","601288.SH":"银行",
"601318.SH":"保险","601328.SH":"银行","601336.SH":"保险","601360.SH":"软件服务",
"601398.SH":"银行","601601.SH":"保险","601628.SH":"保险","601633.SH":"汽车整车",
"601668.SH":"工程建设","601688.SH":"证券","601698.SH":"航天装备","601766.SH":"轨道交通",
"601800.SH":"工程建设","601857.SH":"石化","601888.SH":"旅游零售","601899.SH":"有色",
"601939.SH":"银行","601988.SH":"银行","601989.SH":"船舶制造","603000.SH":"文化传媒",
"603019.SH":"计算机设备","603027.SH":"食品加工","603039.SH":"软件服务","603086.SH":"农药",
"603096.SH":"文化传媒","603156.SH":"饮料乳品","603160.SH":"半导体","603185.SH":"光伏设备",
"603198.SH":"白酒","603259.SH":"医疗研发外包","603288.SH":"食品加工","603290.SH":"半导体",
"603345.SH":"食品加工","603369.SH":"白酒","603444.SH":"游戏","603486.SH":"家电",
"603501.SH":"半导体","603517.SH":"休闲食品","603588.SH":"环保","603596.SH":"汽车零部件",
"603605.SH":"个护用品","603606.SH":"电网设备","603613.SH":"互联网服务","603659.SH":"电池",
"603666.SH":"军工","603678.SH":"军工电子","603686.SH":"环保","603799.SH":"小金属",
"603806.SH":"光伏设备","603816.SH":"家居用品","603833.SH":"家居用品","603858.SH":"中药",
"603866.SH":"休闲食品","603882.SH":"医疗服务","603883.SH":"医药商业","603885.SH":"机场航运",
"603893.SH":"半导体","603899.SH":"文娱用品","603920.SH":"半导体","603927.SH":"软件服务",
"603960.SH":"汽车整车","603986.SH":"半导体","603993.SH":"小金属","603997.SH":"汽车零部件",
"603998.SH":"中药",
}

def cached(key, fetcher, hours=6):
    path = f'{CACHE}/{key}.pkl'
    if os.path.exists(path):
        age = (time.time()-os.path.getmtime(path))/3600
        if age < hours:
            print(f"[缓存] {key} 命中")
            return pd.read_pickle(path)
    last_err = None
    for attempt in range(4):
        try:
            time.sleep(1.5)
            df = fetcher()
            df.to_pickle(path)
            print(f"[接口] {key} 拉取成功")
            return df
        except Exception as e:
            last_err = e
            if '频率超限' in str(e) or '次/分' in str(e):
                print(f"[限频] {key} 第{attempt+1}次，睡20秒重试")
                time.sleep(20)
            else:
                break
    print(f"[失败] {key}: {str(last_err)[:60]}")
    if os.path.exists(path):
        print(f"[降级] {key} 用旧缓存")
        return pd.read_pickle(path)
    raise last_err

# ===== 1. 当日行情 + 基础指标 =====
df = cached(f'daily_{TODAY}', lambda: pro.daily(trade_date=TODAY), hours=2)
try:
    bk = cached(f'basic_{TODAY}', lambda: pro.daily_basic(trade_date=TODAY,
        fields='ts_code,turnover_rate,volume_ratio,float_mv,total_mv'), hours=2)
    df = df.merge(bk, on='ts_code', how='left')
except Exception as e:
    print("daily_basic 不可用:", e)

# ===== 2. 筛主板（沪60x + 深00x）+ 挂行业 =====
df['is_main'] = df['ts_code'].str.match(r'^(60[0-3]|00[0-3])')
df = df[df['is_main']].copy()
df['industry'] = df['ts_code'].map(INDUSTRY_MAP)
print("主板股票数:", len(df), " 有行业标签:", int(df['industry'].notna().sum()))

# ===== 3. 自算涨停 =====
df['is_limit'] = (df['pct_chg'] >= 9.5) & (abs(df['close']-df['high']) < 0.01)
limit_today = df[df['is_limit']].copy()
print("今日主板涨停(自算):", len(limit_today))
limit_cnt = len(limit_today)
if limit_cnt > 80:
    mkt, mkt_rs = 1.0, "情绪高潮"
elif limit_cnt >= 50:
    mkt, mkt_rs = 0.5, "情绪正常"
elif limit_cnt < 40:
    mkt, mkt_rs = -1.5, "情绪低迷"
else:
    mkt, mkt_rs = 0.0, "情绪中性"

# ===== 4. 行业梯队 =====
ind_cnt = limit_today.dropna(subset=['industry']).groupby('industry')['ts_code'].count()
def ind_score(ind):
    if pd.isna(ind) or ind not in ind_cnt.index:
        return 0.0, "无梯队数据"
    c = int(ind_cnt[ind])
    if c >= 3:
        return 2.0, f"梯队{c}家"
    if c == 2:
        return 1.2, "双龙"
    return -0.8, "孤板"
print("涨停梯队TOP:", dict(ind_cnt.sort_values(ascending=False).head(5)))

# ===== 5. 逐只打分 =====
rows = []
if len(limit_today) == 0:
    print("今日无涨停数据（可能盘中/非交易日），正常退出")
for r in limit_today.itertuples():
    code = r.ts_code
    try:
        h = cached(f'hist_{code}', lambda c=code: pro.daily(ts_code=c,
            start_date=(pd.Timestamp.today()-pd.Timedelta(days=45)).strftime('%Y%m%d'),
            end_date=TODAY).sort_values('trade_date').reset_index(drop=True), hours=1)
        if len(h) < 5:
            continue
        last = h.iloc[-1]

        lt = 0
        for i in range(len(h)-1, -1, -1):
            row = h.iloc[i]
            if row['pct_chg'] >= 9.5 and abs(row['close']-row['high']) < 0.01:
                lt += 1
            else:
                break
        if lt == 0:
            lt = 1

        s = 0.0
        rs = []
        mv = getattr(r, 'float_mv', None) or getattr(r, 'total_mv', None)
        tr = getattr(r, 'turnover_rate', None)
        cl = getattr(r, 'close', 0)
        try:
            vol_ma5 = h['vol'].tail(6).iloc[:-1].mean()
        except Exception:
            vol_ma5 = None

        if last['open']==last['close']==last['high']==last['low']:
            s += 2.0; rs.append("一字板")
        elif abs(last['open']-last['high'])<0.01 and abs(last['close']-last['high'])<0.01:
            s += 1.6; rs.append("开盘秒板")
        elif abs(last['close']-last['high'])<0.01:
            s += 1.2; rs.append("光头板")
        else:
            s += 0.5; rs.append("普通板")

        if vol_ma5:
            if last['vol'] < vol_ma5*0.8:
                s += 1.5; rs.append("缩量惜售")
            elif last['vol'] < vol_ma5*1.5:
                s += 1.0
            elif last['vol'] > vol_ma5*2.5:
                s -= 0.5; rs.append("爆量分歧")

        if tr is not None and not pd.isna(tr):
            if 10 <= tr <= 25:
                s += 1.0; rs.append("换手健康")
            elif 5 <= tr < 10:
                s += 0.6
            elif 25 < tr <= 40:
                s += 0.3
            elif tr > 40:
                s -= 0.5; rs.append("换手过大")

        i_sc, i_rs = ind_score(getattr(r, 'industry', None))
        s += i_sc; rs.append(i_rs)

        if mv is not None and not pd.isna(mv):
            if 20 <= mv <= 50:
                s += 1.0; rs.append("黄金市值")
            elif 8 <= mv < 20:
                s += 0.7
            elif 50 <= mv <= 100:
                s += 0.4
            elif mv > 100:
                s -= 0.3; rs.append("盘子大")
        if cl and cl > 20:
            s -= 0.3

        if lt >= 4:
            s += 1.5; rs.append(f"{lt}板高标")
        elif lt == 3:
            s += 1.3; rs.append("3板")
        elif lt == 2:
            s += 0.9; rs.append("2板")
        else:
            s += 0.4; rs.append("首板")

        if len(h) >= 20 and last['close'] > h['close'].tail(5).mean() > h['close'].tail(20).mean():
            s += 1.0; rs.append("多头")

        s += mkt

        rows.append({'code': code, 'ind': getattr(r, 'industry', None),
                     'close': round(float(cl), 2), 'lt': lt,
                     'mv': round(float(mv)) if (mv is not None and not pd.isna(mv)) else 0,
                     'score': round(min(max(s, 0), 10), 1), 'reason': '、'.join(rs)})
        time.sleep(1.2)
    except Exception as e:
        print(f"[跳过] {code}: {str(e)[:50]}")
        continue

print("打分完成, 候选数:", len(rows))
top = sorted(rows, key=lambda x: -x['score'])[:3]

# ===== 6. 推送 =====
token = os.environ.get('PUSHPLUS_TOKEN')
print("PUSHPLUS_TOKEN 长度:", len(token) if token else 0)
if not token:
    print("!! 未配置 PUSHPLUS_TOKEN")

def grade(sc):
    if sc >= 8:
        return "🟢 重仓可上"
    if sc >= 6.5:
        return "🟡 正常仓位"
    if sc >= 5:
        return "🟠 轻仓试错"
    return "⚪ 空仓别上"

if token:
    try:
        if not top:
            content = "<h3>📭 今日无连板候选</h3>"
        else:
            rows_html = ""
            for i, x in enumerate(top, 1):
                nm = x['ind'] if (x['ind'] and not pd.isna(x['ind'])) else x['code']
                rows_html += (
                    f"<tr><td>{i}</td><td>{nm}<br><small>{x['code']}</small></td>"
                    f"<td>{x['close']}</td><td>{x['lt']}板</td><td>{x['mv']}亿</td>"
                    f"<td><b>{x['score']}</b></td><td>{grade(x['score'])}</td>"
                    f"<td>{x['reason']}</td></tr>"
                )
            content = (
                f"<h3>🔥 连板晋级评分 · {TODAY}</h3>"
                f"<p><small>涨停{limit_cnt}家 · {mkt_rs}｜候选{len(rows)}只｜非投资建议</small></p>"
                f"<table style='border-collapse:collapse;width:100%'>"
                f"<tr style='background:#f2f2f2'>"
                f"<th style='border:1px solid #ddd;padding:6px'>#</th>"
                f"<th style='border:1px solid #ddd;padding:6px'>股票/行业</th>"
                f"<th style='border:1px solid #ddd;padding:6px'>收盘</th>"
                f"<th style='border:1px solid #ddd;padding:6px'>连板</th>"
                f"<th style='border:1px solid #ddd;padding:6px'>市值</th>"
                f"<th style='border:1px solid #ddd;padding:6px'>分</th>"
                f"<th style='border:1px solid #ddd;padding:6px'>建议</th>"
                f"<th style='border:1px solid #ddd;padding:6px'>理由</th></tr>"
                f"{rows_html}</table>"
            )
        resp = requests.post("https://www.pushplus.plus/send",
            headers={'Content-Type': 'application/json'},
            data=json.dumps({"token": token,
                             "title": f"🔥 连板评分 · {TODAY} · {len(top)}只",
                             "content": content, "template": "html"}).encode('utf-8'),
            timeout=15)
        print("状态码:", resp.status_code)
        print("返回内容:", resp.text[:200])
    except Exception as pe:
        print("!!! 推送环节报错 !!!")
        traceback.print_exc()

print("==== 全部完成 ====")
