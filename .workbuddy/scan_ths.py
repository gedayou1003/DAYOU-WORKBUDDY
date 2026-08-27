# -*- coding: utf-8 -*-
"""多标的扫描 v2：同花顺行业(实时OHLC,8-24) + 宽基指数/恒生(腾讯,8-25)
按「方向明确度 × 波动幅度」选出高确定性+高波动标的"""
import sys, os, json, warnings, time
warnings.filterwarnings('ignore')
import pandas as pd
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.expanduser("~/.workbuddy/skills/chan-signal__skillhub")
sys.path.insert(0, os.path.join(SKILL, 'scripts'))
sys.path.insert(0, HERE)
from chan_signal import run_engine, build_analysis, calc_macd

# 申万一级 31 大类的干净名称
SW_NAMES = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁", "801050": "有色金属",
    "801080": "电子", "801110": "家用电器", "801120": "食品饮料", "801130": "纺织服饰",
    "801140": "轻工制造", "801150": "医药生物", "801160": "公用事业", "801170": "交通运输",
    "801180": "房地产", "801200": "商贸零售", "801210": "社会服务", "801230": "综合",
    "801710": "建筑材料", "801720": "建筑装饰", "801730": "电力设备", "801740": "国防军工",
    "801750": "计算机", "801760": "传媒", "801770": "通信", "801780": "银行",
    "801790": "非银金融", "801880": "汽车", "801890": "机械设备", "801950": "煤炭",
    "801960": "石油石化", "801970": "环保", "801980": "美容护理",
}

# 同花顺 90 细分行业 → 申万一级大类映射
THS_TO_SW = {
    # 农林牧渔
    "种植业与林业": "801010", "农产品加工": "801010", "养殖业": "801010",
    # 基础化工
    "化学原料": "801030", "农化制品": "801030", "化学制品": "801030",
    "塑料制品": "801030", "橡胶制品": "801030", "化学纤维": "801030",
    # 钢铁
    "钢铁": "801040",
    # 有色金属
    "工业金属": "801050", "小金属": "801050", "能源金属": "801050", "贵金属": "801050", "金属新材料": "801050",
    # 电子
    "消费电子": "801080", "光学光电子": "801080", "元件": "801080", "其他电子": "801080",
    "半导体": "801080", "电子化学品": "801080",
    # 家用电器
    "小家电": "801110", "黑色家电": "801110", "白色家电": "801110", "厨卫电器": "801110",
    # 食品饮料
    "饮料制造": "801120", "食品加工制造": "801120", "白酒": "801120",
    # 纺织服饰
    "纺织制造": "801130", "服装家纺": "801130",
    # 轻工制造
    "造纸": "801140", "包装印刷": "801140", "家居用品": "801140",
    # 医药生物
    "医药商业": "801150", "中药": "801150", "医疗服务": "801150", "化学制药": "801150",
    "生物制品": "801150", "医疗器械": "801150",
    # 公用事业
    "燃气": "801160", "电力": "801160",
    # 交通运输
    "物流": "801170", "公路铁路运输": "801170", "机场航运": "801170", "港口航运": "801170",
    # 房地产
    "房地产": "801180",
    # 商贸零售
    "零售": "801200", "互联网电商": "801200", "贸易": "801200",
    # 社会服务
    "旅游及酒店": "801210", "教育": "801210", "其他社会服务": "801210",
    # 综合
    "综合": "801230",
    # 建筑材料
    "建筑材料": "801710", "非金属材料": "801710",
    # 建筑装饰
    "建筑装饰": "801720",
    # 电力设备
    "电机": "801730", "风电设备": "801730", "电网设备": "801730", "其他电源设备": "801730",
    "光伏设备": "801730", "电池": "801730",
    # 国防军工
    "军工装备": "801740", "军工电子": "801740",
    # 计算机
    "软件开发": "801750", "IT服务": "801750", "计算机设备": "801750",
    # 传媒
    "影视院线": "801760", "文化传媒": "801760", "游戏": "801760",
    # 通信
    "通信服务": "801770", "通信设备": "801770",
    # 银行
    "银行": "801780",
    # 非银金融
    "多元金融": "801790", "保险": "801790", "证券": "801790",
    # 汽车
    "汽车零部件": "801880", "汽车整车": "801880", "汽车服务及其他": "801880",
    # 机械设备
    "通用设备": "801890", "自动化设备": "801890", "轨交设备": "801890", "专用设备": "801890", "工程机械": "801890",
    # 煤炭
    "煤炭开采加工": "801950",
    # 石油石化
    "油气开采及服务": "801960", "石油加工贸易": "801960",
    # 环保
    "环境治理": "801970", "环保设备": "801970",
    # 美容护理
    "美容护理": "801980",
}

UA = {'User-Agent': 'Mozilla/5.0'}
def tencent_get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read().decode('utf-8'))

def fetch_tencent(code, period='day', count=250):
    u = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},{period},,,{count},qfq'
    d = tencent_get(u)
    data = d.get('data', {}).get(code, {})
    rows = data.get('qfqday') or data.get('qfqweek') or data.get('day') or data.get('week') or []
    if not rows:
        return None
    df = pd.DataFrame([r[:6] for r in rows], columns=['date','open','close','high','low','vol'])
    for c in ['open','close','high','low']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['amount'] = df['vol']
    return df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)

def fetch_ths(name):
    """同花顺行业指数 OHLC（akshare，完整开高低收，T+1 最新）"""
    import akshare as ak
    from datetime import date, timedelta
    end_date = date.today().strftime('%Y%m%d')
    start_date = (date.today() - timedelta(days=400)).strftime('%Y%m%d')
    raw = ak.stock_board_industry_index_ths(symbol=name, start_date=start_date, end_date=end_date)
    df = pd.DataFrame({
        'date': pd.to_datetime(raw['日期']),
        'open': raw['开盘价'].astype(float), 'close': raw['收盘价'].astype(float),
        'high': raw['最高价'].astype(float), 'low': raw['最低价'].astype(float),
        'vol': raw['成交量'].astype(float), 'amount': raw['成交额'].astype(float),
    })
    return df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)

def score_one(code, name, df):
    if df is None or len(df) < 40:
        return None
    try:
        engine = run_engine(df)
        a = build_analysis(code, df, engine, 9, recent_bars=0)
    except Exception as e:
        return {'error': str(e)}
    trend = a['structure'].get('current_trend')
    trend_score = 2 if trend == '向上' else (-2 if trend == '向下' else 0)
    cutoff = (pd.Timestamp.now() - pd.Timedelta(days=30)).strftime('%Y-%m-%d')
    sigs = [s for s in a.get('signals', []) if (s.get('date','') or '') >= cutoff]
    sig_score = 0
    sig_name = '—'
    if sigs:
        s0 = sigs[0]
        w = 2
        if s0.get('confidence', 0.5) < 0.6:
            w *= 0.5
        sig_score = w if s0['type'] == 'buy' else -w
        sig_name = f"{s0.get('name')}@{s0.get('price')}(conf{s0.get('confidence')})"
    macd = calc_macd(df)
    dif = float(macd['macd'].iloc[-1]); dea = float(macd['macd_signal'].iloc[-1])
    macd_score = 1 if dif > dea else -1
    total = trend_score + sig_score + macd_score
    close = float(df['close'].iloc[-1])
    h20 = float(df['high'].tail(20).max()); l20 = float(df['low'].tail(20).min())
    vol = (h20 - l20) / close * 100
    last_date = str(df['date'].iloc[-1])[:10]
    return {
        'name': name, 'code': code, 'close': close, 'last_date': last_date,
        'trend': trend, 'direction': total, 'volatility': round(vol, 2), 'sig': sig_name,
    }

def aggregate_sw(results_ths):
    """把 90 个同花顺细分行业聚合到 31 个申万一级大类：方向取成员均值、振幅取均值、趋势取多数。"""
    from collections import defaultdict
    groups = defaultdict(list)
    for r in results_ths:
        code = THS_TO_SW.get(r['name'])
        if code:
            groups[code].append(r)
    sw_agg = []
    for code, members in groups.items():
        n = len(members)
        avg_dir = sum(m['direction'] for m in members) / n
        avg_vol = sum(m['volatility'] for m in members) / n
        ups = sum(1 for m in members if m['trend'] == '向上')
        downs = sum(1 for m in members if m['trend'] == '向下')
        trend = '向上' if ups > downs else ('向下' if downs > ups else '交织')
        sw_agg.append({
            'name': SW_NAMES.get(code, code), 'sw_code': code, 'members': n,
            'direction': round(avg_dir, 1), 'volatility': round(avg_vol, 2),
            'score': round(abs(avg_dir) * avg_vol, 2), 'trend': trend,
        })
    sw_agg.sort(key=lambda x: x['score'], reverse=True)
    return sw_agg


def main():
    # 缓存：缠论方向分是 T+1 慢变量，当天已跑过则复用，不重算（省 90 次 akshare + 90 次引擎）
    cache_path = os.path.join(HERE, 'backtest_data', 'scan_result_ths.json')
    if os.path.exists(cache_path):
        mt = os.path.getmtime(cache_path)
        if time.strftime('%Y-%m-%d', time.localtime(mt)) == time.strftime('%Y-%m-%d'):
            print(f'[缓存] scan_result_ths.json 今天已生成（{time.strftime("%H:%M", time.localtime(mt))}），跳过重算')
            return

    import akshare as ak
    results_ths = []
    results_idx = []

    # 同花顺行业列表
    try:
        ind = ak.stock_board_industry_summary_ths()
        ths_names = ind['板块'].tolist()
    except Exception as e:
        print(f'同花顺行业列表失败: {e}')
        ths_names = []

    print(f'=== 同花顺行业扫描（{len(ths_names)} 个，akshare ths，最新 8-24）===')
    for i, name in enumerate(ths_names):
        try:
            df = fetch_ths(name)
            r = score_one('ths_'+name, name, df)
            if r and 'error' not in r:
                results_ths.append(r)
                print(f"  [{i+1}/{len(ths_names)}] {name}: 方向{r['direction']:+.1f} 振幅{r['volatility']}% 趋势{r['trend']}")
        except Exception as e:
            print(f"  [{i+1}/{len(ths_names)}] {name}: 失败 {str(e)[:30]}")

    print('\n=== 宽基指数 + 恒生（腾讯，实时 8-25）===')
    idx_list = [
        ('sh000300', '沪深300'), ('sh000016', '上证50'),
        ('sh000852', '中证1000'), ('hkHSI', '恒生指数'),
    ]
    for tc, name in idx_list:
        try:
            df = fetch_tencent(tc, 'day')
            r = score_one(tc, name, df)
            if r and 'error' not in r:
                results_idx.append(r)
                print(f"  {name}: 方向{r['direction']:+.1f} 振幅{r['volatility']}% 趋势{r['trend']} 信号[{r['sig']}]")
        except Exception as e:
            print(f"  {name}: 失败 {str(e)[:40]}")

    for lst in (results_ths, results_idx):
        for r in lst:
            r['score'] = round(abs(r['direction']) * r['volatility'], 2)
    results_ths.sort(key=lambda x: x['score'], reverse=True)
    results_idx.sort(key=lambda x: x['score'], reverse=True)

    sw_agg = aggregate_sw(results_ths)
    print('\n===== 申万一级大类 TOP 15（|方向|×振幅 降序，方向=成员均值）=====')
    for r in sw_agg[:15]:
        print(f"  {r['name']:8s} 方向{r['direction']:+.1f} 振幅{r['volatility']}% 综合{r['score']} 成员{r['members']} 趋势{r['trend']}")

    print('\n\n===== 同花顺行业 TOP 15（|方向|×振幅 降序）=====')
    for r in results_ths[:15]:
        print(f"  {r['name']:10s} 方向{r['direction']:+.1f} 振幅{r['volatility']}% 综合{r['score']} 信号[{r['sig']}]")
    print('\n===== 宽基/恒生 TOP =====')
    for r in results_idx:
        print(f"  {r['name']:8s} 方向{r['direction']:+.1f} 振幅{r['volatility']}% 综合{r['score']} 信号[{r['sig']}]")

    out = {'ths': results_ths, 'index': results_idx, 'sw_agg': sw_agg}
    os.makedirs(os.path.join(HERE, 'backtest_data'), exist_ok=True)
    with open(os.path.join(HERE, 'backtest_data', 'scan_result_ths.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n结果已保存 backtest_data/scan_result_ths.json")

if __name__ == '__main__':
    main()
