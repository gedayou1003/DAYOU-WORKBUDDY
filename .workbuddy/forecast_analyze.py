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

退出码（2026-09-23 起，与 check_layout / fetch_zsxq 统一口径）:
    0 = 通过（数据包完整）
    1 = ERROR：行情未取到，数据包不可用于预判（ohlc.error 非空）
    2 = WARN：降级但可用（如引擎未取到 → data 里有 engine_error）
调用方（AI / 脚本）看退出码即可分辨「包是完整的」与「包缺核心输入」。
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
import qt_api      # 腾讯接口多域名 failover（2026-09-18：web.ifzq.gtimg.cn 被代理拦）
from dragonball_signals import classify_macd_state  # DRAGONBALL 融合 P0（2026-09-24）


def run_py(script, *args):
    """运行 python 脚本，返回 (stdout, 退出码, stderr 尾巴)。

    2026-09-23：旧实现只返回 stdout —— 子脚本失败时退出码与被 capture 的 stderr
    全被丢掉，调用方只能拿到一个空字符串，**「脚本崩了」与「本来就没输出」不可区分**
    （第五原则：失败模式必须出声）。
    """
    r = subprocess.run([PY, script] + list(args), capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    err = ((r.stderr or '').strip() or (r.stdout or '').strip())[-300:]
    return (r.stdout or '').strip(), r.returncode, err


def fetch_ohlc(code):
    """取日线行情。失败时返回 {"error": 原因}，原因里带退出码与 stderr。

    2026-09-23：旧实现把 stdout 原样塞进 error 字段 —— 子脚本 rc≠0 且没往 stdout
    写东西时，error 是空串，数据包里只剩 `"ohlc": {"error": ""}`，看不出任何原因。
    """
    out, rc, err = run_py(os.path.join(HERE, 'get_daily_ohlc.py'), code, '1')
    if rc != 0 and not out:
        return {"error": "get_daily_ohlc.py 退出码 %d：%s" % (rc, err or '(无输出)')}
    try:
        d = json.loads(out)
    except Exception as e:
        return {"error": "行情输出不是 JSON（%r）：%s" % (e, (err or out)[:200])}
    if rc != 0 and isinstance(d, dict) and 'error' not in d:
        # rc≠0 却给了看似正常的行情：不静默采信，就地标注（下同 error 判定口径）
        d['error'] = "get_daily_ohlc.py 退出码 %d（数据可能不完整）：%s" % (rc, err[:160])
    return d


def _normalize_direction(d):
    """方向归一化：英文/中文 -> bullish/bearish/sideways

    注意：direction 字段实际常带后缀（如「震荡偏多（v5 -2 方向不明偏多）」「偏空（Bearish）」），
    必须用子串匹配而非精确匹配，否则带后缀的方向会全部落回 sideways。
    """
    s = str(d or '').strip().lower()
    if any(k in s for k in ('偏多', '看多', '偏强', 'bullish', 'bull')):
        return 'bullish'
    if any(k in s for k in ('偏空', '看空', '偏弱', 'bearish', 'bear')):
        return 'bearish'
    return 'sideways'


def _num(v):
    """兼容支撑/压力字段的两种形态：数字 或 {'primary': x, 'primary_basis': ...}"""
    if isinstance(v, dict):
        return v.get('primary') if v.get('primary') is not None else v.get('value')
    return v


def _direction_verdict(direction, pct):
    """单口径方向判定：涨跌幅符号 vs 预判方向"""
    if direction == 'sideways' and abs(pct) < 0.5:
        return '✅ hit (sideways)'
    elif direction == 'bullish' and pct > 0:
        return '✅ hit (bullish)'
    elif direction == 'bearish' and pct < 0:
        return '✅ hit (bearish)'
    elif direction == 'bullish' and pct < 0:
        return '❌ miss (forecast bullish, actual down)'
    elif direction == 'bearish' and pct > 0:
        return '❌ miss (forecast bearish, actual up)'
    else:
        return '⚠️ partial'


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

    # 方向判定：双口径
    #   direction          = 收盘 vs 前收盘（全天净方向，含高低开跳空）
    #   direction_intraday = 开盘 vs 收盘（日内真实方向，剔除跳空）
    pct = ohlc.get('pct_chg', 0)
    verdicts['direction'] = _direction_verdict(direction, pct)
    open_p = ohlc.get('open')
    if open_p is not None and open_p != 0:
        intraday_pct = round((close - open_p) / open_p * 100, 2)
        verdicts['direction_intraday'] = _direction_verdict(direction, intraday_pct)
        # 高低开导致的「全天 vs 日内」方向背离（低开高走 / 高开低走）
        if (pct > 0) != (intraday_pct > 0):
            gap = ohlc.get('gap_type', '跳空')
            verdicts['gap_note'] = (f'⚠️ {gap}导致背离：全天 {pct:+.2f}% vs 日内 {intraday_pct:+.2f}%，'
                                    f'收盘方向受跳空干扰，日内真实方向为 {"涨" if intraday_pct > 0 else "跌"}')

    # 支撑判定（v5 第六节：区分真假破位——盘中破但收盘收回 = 假破位/下跌衰竭）
    if support is not None:
        if low >= support:
            verdicts['support'] = f'✅ held (support {support}, low {low})'
        elif close >= support:
            verdicts['support'] = f'⚠️ 假破位 (support {support}, 盘中低 {low} 跌破但收盘 {close} 收回)'
        else:
            verdicts['support'] = f'❌ broken (support {support}, low {low}, close {close})'

    # 压力判定（v5 第六节：区分真假突破——盘中突破但收盘回落 = 假突破，不追多）
    if resistance is not None:
        if high <= resistance:
            verdicts['resistance'] = f'✅ held (resistance {resistance}, high {high})'
        elif close <= resistance:
            verdicts['resistance'] = f'⚠️ 假突破 (resistance {resistance}, 盘中高 {high} 突破但收盘 {close} 回落)'
        else:
            verdicts['resistance'] = f'❌ broken (resistance {resistance}, high {high}, close {close})'

    return verdicts


def fetch_history(tencent_code, count=60):
    """拉最近 count 根日线（腾讯 fqkline），返回 [{'date','close'},...] 升序"""
    data, _src = qt_api.get_json(
        f"/appstock/app/fqkline/get?param={tencent_code},day,,,{count},qfq", timeout=15)
    node = data["data"][tencent_code]
    kline = node.get("qfqday") or node.get("day") or []
    rows = []
    for r in kline:  # r: [date, open, close, high, low, volume, ...]
        rows.append({"date": r[0], "close": float(r[2])})
    return rows


def _macd(closes):
    """EMA12/EMA26 → DIF，EMA9 → DEA（与 calc_tech.py 同口径）。返回 (dif, dea)。"""
    def _ema(vals, n):
        k = 2 / (n + 1)
        e = vals[0]
        out = [e]
        for v in vals[1:]:
            e = v * k + e * (1 - k)
            out.append(e)
        return out
    e12 = _ema(closes, 12)
    e26 = _ema(closes, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = _ema(dif, 9)
    return dif, dea


def compute_tj_bypass(tencent_code):
    """DRAGON BALL模型 旁路状态检测（backtest_tj_v2.py 回测已验证的两个短线辅助信号）。

    只标注、绝不进 v5 方向打分。依据回测结论：
    - 持续极强：日线 55 线上方连续加速 2 日 → 短线不追高（次日跌 46.6% vs 涨 32.8%）
    - 解除极弱：55 线下方减速 → 超跌反弹（越跌越买）
    无触发时 signal/note 为 None。

    2026-09-24 融合 P0：新增 `macd_state` / `macd_state_side`（篇4 的 MACD 六态「稳定性」
    分类）。注意与上面 `state_now`（价格相对 55 线的「加速/减速」动量口径）**语义不同**——
    前者刻画趋势持续性（DIF/DEA 符号），后者刻画价格动量，二者并存、不互相覆盖。
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

    # 篇4 MACD 六态（稳定性分类，与上面的动量口径独立）
    dif, dea = _macd(closes)
    mstate = classify_macd_state(dif[-1], dea[-1])

    out = {
        "close": closes[-1],
        "ma20": round(ma(20, n - 1) or 0, 2),
        "ma55": round(ma(55, n - 1) or 0, 2),
        "state_now": s_now,
        "state_prev": s_prev,
        "macd_state": mstate['state'],
        "macd_state_side": mstate['side'],
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


def build_gap_context(ohlc, prev):
    """高低开上下文：今日跳空 + 上期支撑/压力位相对昨收/今开的双锚点。

    目的：开盘跳空会让"相对现价百分比"失真（现价锚点从昨收跳到今开），
    显式给出两个锚点的百分比，供 AI 复盘/写报告时修正。
    """
    if not ohlc or 'error' in ohlc:
        return None
    ctx = {
        'gap_pct': ohlc.get('gap_pct'),
        'gap': ohlc.get('gap'),
        'gap_type': ohlc.get('gap_type'),
        'open': ohlc.get('open'),
        'prev_close': ohlc.get('prev_close'),
    }
    open_p = ohlc.get('open')
    prev_close = ohlc.get('prev_close')
    if prev and open_p is not None and prev_close is not None:
        anchors = {}
        for key in ('support', 'resistance'):
            v = _num(prev.get(key))
            if v is not None:
                anchors[key] = {
                    'price': v,
                    'vs_prev_close_pct': round((v - prev_close) / prev_close * 100, 2),
                    'vs_open_pct': round((v - open_p) / open_p * 100, 2),
                }
        ctx['anchors'] = anchors
    return ctx


def _engine_json_path(code):
    """推算 chan-signal 引擎的 JSON 产物路径。

    引擎固定写到 `<技能目录>/output/<CODE>_<YYYYMMDD>_chansignal.json`（见
    `run_000001_chansignal.py` 的 `out = os.path.join(HERE, 'output', ...)`），
    路径**完全可推算**，不需要问 stdout。

    旧实现靠解析 stdout 里的「已保存:」文案取路径 —— 引擎改一句日志文案、
    或改成别的措辞，就静默返回 None，预判数据包会缺掉整块引擎结果而无人察觉
    （脚本地图 §四 待办 #8）。2026-09-17 改为直接推算 + 目录兜底。
    """
    day = datetime.datetime.now().strftime('%Y%m%d')
    std = code
    try:
        info = resolve(code)
        if info:
            std = info['code']
    except Exception:  # silent-ok: 注册表解析失败则按原样代号继续，最终取不到文件会返回 None 交上层报错
        pass
    d = os.path.join(CHAN_DIR, 'output')
    exact = os.path.join(d, '%s_%s_chansignal.json' % (std, day))
    if os.path.exists(exact):
        return exact
    # 兜底：注册表解析结果与引擎内部不一致时，按 CODE 片段取当日最新一份
    if os.path.isdir(d):
        cands = [os.path.join(d, f) for f in os.listdir(d)
                 if f.endswith('_chansignal.json') and ('_%s_' % std) in f]
        if cands:
            return max(cands, key=os.path.getmtime)
    return None


def run_engine(code):
    """跑 chan-signal 引擎并读回 JSON。返回 (data, error)。

    **读不到数据时必须显式报错**：旧实现在「引擎崩溃」和「文案变了」两种情况下
    都静默返回 None，调用方拿到 engine=None 却无从判断原因。
    另：以 `cwd=CHAN_DIR` 启动，消除引擎对工作目录的隐式依赖
    （脚本地图 §四 待办 #10：在项目根跑会报 `[Errno 2] No such file`，
    而文件其实存在，报错误导）。
    """
    try:
        r = subprocess.run([PY, os.path.join(CHAN_DIR, 'run_000001_chansignal.py'),
                            '--code', code],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', cwd=CHAN_DIR)
    except Exception as e:
        return None, '引擎启动失败：%r' % e
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or '')[-300:].replace('\n', ' ')
        return None, '引擎退出码 %d：%s' % (r.returncode, tail)
    p = _engine_json_path(code)
    if not p:
        return None, ('引擎已正常退出，但推算不到 JSON 产物 —— 检查 %s/output/ 下'
                      '是否有当日 %s 文件（引擎输出路径约定可能已变更）'
                      % (os.path.basename(CHAN_DIR), code))
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f), None
    except Exception as e:
        return None, '引擎 JSON 解析失败（%s）：%r' % (p, e)


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
        eng, eng_err = run_engine(std_code)
        result['engine'] = eng
        if eng_err:
            # 显式报错而非静默 None：调用方/AI 需知道「引擎没跑出来」还是「引擎没信号」
            result['engine_error'] = eng_err
            print('⚠️ 引擎未取到数据：%s' % eng_err, file=sys.stderr)

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

    # 5. DRAGON BALL模型 旁路状态（只标注，不进 v5 方向打分）
    result['tj_bypass'] = compute_tj_bypass(resolved['tencent'])

    # 6. 高低开上下文（双锚点：相对昨收 / 相对今开）
    result['gap_context'] = build_gap_context(result['ohlc'], prev)

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    # 退出码语义（2026-09-23 新增；与 check_layout / fetch_zsxq 统一口径：
    #   0=通过 · 1=ERROR（核心输入缺失）· 2=WARN（降级但仍可用））
    # 旧实现 main() 没有返回值 → 行情取不到时照样打印数据包并退出 0，
    # 「整包没有行情」与「一切正常」在退出码上完全一样（第一原则·无退出码语义）。
    # 注意口径：本脚本是「一键数据包」，行情缺失=包不可用 → 1；
    # 引擎缺失（engine_error）时行情/链/复盘仍在 → 只算降级 → 2。
    if isinstance(result.get('ohlc'), dict) and 'error' in result['ohlc']:
        print('[FAIL] 行情未取到，数据包不可用于预判：%s'
              % result['ohlc']['error'], file=sys.stderr)
        return 1
    if result.get('engine_error'):
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
