# -*- coding: utf-8 -*-
"""
预判分析一键入口（支持任意指数）
================================
把"取行情 → 跑 chan-signal 引擎 → 读预判链 → 复盘上期 → 输出数据包"串成一个命令，
供 AI 生成"方向/区间/支撑/压力/置信度"的综合预判结论。

用法:
    python forecast_analyze.py                 # 默认 000001 上证综指
    python forecast_analyze.py 000300          # 沪深300
    python forecast_analyze.py 中证1000        # 中证1000（支持名称）
    python forecast_analyze.py 000905 --skip-engine   # 只取行情+复盘，不跑引擎（引擎已跑过时用）

输出: JSON 数据包（供 AI 消费）
{
  "code", "name", "ohlc": {...},           # 当日实际走势
  "engine": [...],                          # chan-signal 五周期买卖点
  "review": {...} or null,                  # 上期 pending 预判的机械复盘
  "prev_forecast": {...} or null            # 上期预判内容
}
"""
import sys, os, json, subprocess, datetime, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.expanduser("~/.workbuddy"))
from paths import PYTHON, SKILLS
PY = PYTHON
CHAN_DIR = os.path.join(SKILLS, "chan-signal__skillhub")
CHAIN = os.path.join(HERE, 'forecast_chain.json')

sys.path.insert(0, HERE)
from market_codes import resolve


def run_py(script, *args):
    """运行 python 脚本并返回 stdout"""
    r = subprocess.run([PY, script] + list(args), capture_output=True, text=True, encoding='utf-8')
    return r.stdout.strip()


def fetch_ohlc(code):
    out = run_py(os.path.join(HERE, 'get_daily_ohlc.py'), code, '1')
    try:
        return json.loads(out)
    except Exception:
        return {"error": out}


def _normalize_direction(d):
    """方向归一化：英文/中文 -> bullish/bearish/sideways"""
    s = str(d or '').strip().lower()
    if s in ('bullish', 'bull', '偏多', '看多', '震荡偏多', '偏强'):
        return 'bullish'
    if s in ('bearish', 'bear', '偏空', '看空', '震荡偏空', '偏弱'):
        return 'bearish'
    return 'sideways'


def _num(v):
    """兼容支撑/压力字段的两种形态：数字 或 {'primary': x, 'primary_basis': ...}"""
    if isinstance(v, dict):
        return v.get('primary') if v.get('primary') is not None else v.get('value')
    return v


def mechanical_review(prev, ohlc):
    """机械复盘：把上期预判 vs 实际 OHLC 逐项判定"""
    if not prev or 'error' in ohlc:
        return None
    high, low = ohlc.get('high'), ohlc.get('low')
    close = ohlc.get('close')
    if not all([high, low, close]):
        return None
    direction = _normalize_direction(prev.get('direction', ''))
    support = _num(prev.get('support'))
    resistance = _num(prev.get('resistance'))
    verdicts = {}

    # 方向判定（收盘涨跌幅符号 vs 预判方向）
    pct = ohlc.get('pct_chg', 0)
    if direction == 'sideways' and abs(pct) < 0.5:
        verdicts['direction'] = '✅ hit (sideways)'
    elif direction == 'bullish' and pct > 0:
        verdicts['direction'] = '✅ hit (bullish)'
    elif direction == 'bearish' and pct < 0:
        verdicts['direction'] = '✅ hit (bearish)'
    elif direction == 'bullish' and pct < 0:
        verdicts['direction'] = '❌ miss (forecast bullish, actual down)'
    elif direction == 'bearish' and pct > 0:
        verdicts['direction'] = '❌ miss (forecast bearish, actual up)'
    else:
        verdicts['direction'] = '⚠️ partial'

    # 支撑判定
    if support is not None:
        if low >= support:
            verdicts['support'] = f'✅ held (support {support}, low {low})'
        else:
            verdicts['support'] = f'❌ broken (support {support}, low {low})'

    # 压力判定
    if resistance is not None:
        if high <= resistance:
            verdicts['resistance'] = f'✅ held (resistance {resistance}, high {high})'
        else:
            verdicts['resistance'] = f'❌ broken (resistance {resistance}, high {high})'

    return verdicts


def fetch_history(tencent_code, count=60):
    """拉最近 count 根日线（腾讯 fqkline），返回 [{'date','close'},...] 升序"""
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
           f"param={tencent_code},day,,,{count},qfq")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    node = data["data"][tencent_code]
    kline = node.get("qfqday") or node.get("day") or []
    rows = []
    for r in kline:  # r: [date, open, close, high, low, volume, ...]
        rows.append({"date": r[0], "close": float(r[2])})
    return rows


def compute_tj_bypass(tencent_code):
    """TJ 旁路状态检测（backtest_tj_v2.py 回测已验证的两个短线辅助信号）。

    只标注、绝不进 v5 方向打分。依据回测结论：
    - 持续极强：日线 55 线上方连续加速 2 日 → 短线不追高（次日跌 46.6% vs 涨 32.8%）
    - 解除极弱：55 线下方减速 → 超跌反弹（越跌越买）
    无触发时 signal/note 为 None。
    """
    try:
        rows = fetch_history(tencent_code, 60)
    except Exception as e:
        return {"error": str(e)}
    if len(rows) < 56:
        return {"error": f"历史K线不足（{len(rows)}根 < 56）"}

    closes = [r["close"] for r in rows]
    n = len(closes)

    def ma(k, i):
        if i + 1 < k:
            return None
        return sum(closes[i - k + 1:i + 1]) / k

    states = []
    for i in range(n):
        m55 = ma(55, i)
        m55p = ma(55, i - 1)
        if m55 is None or m55p is None:
            states.append("nan")
            continue
        dev = (closes[i] - m55) / m55 * 100
        devp = (closes[i - 1] - m55p) / m55p * 100
        if closes[i] > m55 and dev > devp:
            states.append("极强")
        elif closes[i] < m55 and dev < devp:
            states.append("极弱")
        else:
            states.append("其他")

    s_now, s_prev = states[-1], states[-2]
    out = {
        "close": closes[-1],
        "ma20": round(ma(20, n - 1) or 0, 2),
        "ma55": round(ma(55, n - 1) or 0, 2),
        "state_now": s_now,
        "state_prev": s_prev,
    }
    if s_prev == "极强" and s_now == "极强":
        out["signal"] = "持续极强"
        out["note"] = "日线连续加速上涨（55线上方），短线不追高、警惕回踩中轨；仅旁路提示，不进方向打分"
    elif s_prev == "极弱" and s_now != "极弱":
        out["signal"] = "解除极弱"
        out["note"] = "55线下方减速，超跌反弹逻辑（越跌越买）；仅旁路提示，不进方向打分"
    else:
        out["signal"] = None
        out["note"] = None
    return out


def run_engine(code):
    out = run_py(os.path.join(CHAN_DIR, 'run_000001_chansignal.py'), '--code', code)
    # 从输出中找 JSON 路径
    json_path = None
    for line in out.split('\n'):
        if 'chansignal.json' in line and '已保存' in line:
            json_path = line.split('已保存:')[-1].strip()
    if json_path and os.path.exists(json_path):
        with open(json_path, encoding='utf-8') as f:
            return json.load(f)
    return None


def load_chain():
    if not os.path.exists(CHAIN):
        return []
    with open(CHAIN, encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get('records', [])
    return data if isinstance(data, list) else []


def save_chain(chain):
    with open(CHAIN, 'w', encoding='utf-8') as f:
        json.dump(chain, f, ensure_ascii=False, indent=2)


def main():
    code = '000001'
    skip_engine = False
    args = [a for a in sys.argv[1:]]
    if '--skip-engine' in args:
        skip_engine = True
        args.remove('--skip-engine')
    if args:
        code = args[0]

    resolved = resolve(code)
    if not resolved:
        print(json.dumps({"error": f"无法识别的标的: {code}"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    std_code = resolved['code']
    name = resolved['name']

    result = {'code': std_code, 'name': name, 'tencent': resolved['tencent'],
              'data_source': resolved['data_source']}

    # 1. 行情
    result['ohlc'] = fetch_ohlc(std_code)

    # 2. 引擎（可跳过）
    if not skip_engine:
        result['engine'] = run_engine(std_code)

    # 3. 预判链：读该标的最后一条 pending
    chain = load_chain()
    prev = None
    for rec in chain:
        if rec.get('code', '000001') == std_code and rec.get('status') == 'pending':
            prev = rec
    result['prev_forecast'] = prev

    # 4. 机械复盘（不落盘，交给 AI 综合判断后写回）
    if prev and 'error' not in result['ohlc']:
        result['review'] = mechanical_review(prev, result['ohlc'])

    # 5. TJ 旁路状态（只标注，不进 v5 方向打分）
    result['tj_bypass'] = compute_tj_bypass(resolved['tencent'])

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
