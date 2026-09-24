# -*- coding: utf-8 -*-
"""dragonball_p2_data.py —— DRAGONBALL 融合 P2 数据接入（打通数据源，实际取数算指标）。

把 P2 三个融合点接到真实数据：
  P2-10 双级差体系 B：腾讯 fqkline 取日线/周线 → aggregate_double 聚合双日/双周
  P2-12 尾指数：日线收益率 → hill_tail_index 估 ξ（V_tail=1/ξ）
  P2-11 集中度：akshare 取 31 个申万一级行业当日成交额 → concentration 算 Σwi²

用法：
  $PY .workbuddy/dragonball_p2_data.py                 # 全部（含申万行业，约 30s）
  $PY .workbuddy/dragonball_p2_data.py --skip-industry  # 跳过申万行业（快）
退出码：0 正常 · 1 核心数据（行情）取不到 · 2 部分降级（如行业取数失败）
"""
import json
import os
import sys
import urllib.request

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dragonball_signals import aggregate_double, hill_tail_index, concentration

UA = {'User-Agent': 'Mozilla/5.0'}


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=20).read().decode('utf-8'))


def fetch_kline(period, count):
    """腾讯 fqkline 取日线/周线。返回 [{date,open,close,high,low,vol}] 升序。"""
    d = _get(f'https://ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,{period},,,{count},qfq')
    node = d.get('data', {}).get('sh000001', {})
    rows = node.get(period) or node.get('qfq' + period) or []
    out = [{'date': r[0], 'open': float(r[1]), 'close': float(r[2]),
            'high': float(r[3]), 'low': float(r[4]), 'vol': float(r[5]) if len(r) > 5 else 0}
           for r in rows]
    out.sort(key=lambda x: x['date'])
    return out


def fetch_industry_amount():
    """akshare 取 31 个申万一级行业当日成交额（amount）。返回 [amount, ...]。"""
    import akshare as ak
    amounts = []
    codes = ["801010", "801030", "801040", "801050", "801080", "801110", "801120",
             "801130", "801140", "801150", "801160", "801170", "801180", "801200",
             "801210", "801230", "801710", "801720", "801730", "801740", "801750",
             "801760", "801770", "801780", "801790", "801880", "801890", "801950",
             "801960", "801970", "801980"]
    for code in codes:
        try:
            df = ak.index_hist_sw(symbol=code, period='day')
            df.columns = ['code', 'date', 'close', 'open', 'high', 'low', 'volume', 'amount']
            if len(df) and df.iloc[-1]['amount'] is not None:
                amounts.append(float(df.iloc[-1]['amount']))
        except Exception:
            continue
    return amounts


def main():
    skip_ind = '--skip-industry' in sys.argv

    # 1. 行情（日线 + 周线）
    try:
        day = fetch_kline('day', 400)
        week = fetch_kline('week', 200)
    except Exception as e:
        print('[FAIL] 行情取不到：%s' % e, file=sys.stderr)
        return 1

    result = {
        'day_n': len(day),
        'week_n': len(week),
    }

    # 2. 双日/双周（体系 B）
    dbl = aggregate_double(day)
    dbw = aggregate_double(week)
    result['双日'] = {'n': len(dbl), 'last_date': dbl[-1]['date'] if dbl else None}
    result['双周'] = {'n': len(dbw), 'last_date': dbw[-1]['date'] if dbw else None}

    # 3. 尾指数（日线收益率）
    closes = [r['close'] for r in day]
    rets = [(closes[i] - closes[i - 1]) / closes[i - 1] * 100 for i in range(1, len(closes))]
    result['尾指数'] = hill_tail_index(rets)

    # 4. 集中度（申万行业成交额）
    if not skip_ind:
        try:
            amounts = fetch_industry_amount()
            result['集中度'] = concentration(amounts)
            result['集中度']['industry_n'] = len(amounts)
        except Exception as e:
            result['集中度'] = {'error': str(e)}
    else:
        result['集中度'] = {'skipped': True}

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    if not skip_ind and 'error' in result.get('集中度', {}):
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
