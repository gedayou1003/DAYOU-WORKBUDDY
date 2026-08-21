# -*- coding: utf-8 -*-
"""
获取指数/标的当日（最近交易日）OHLC，供"预判复盘"对比实际走势使用。
支持任意腾讯可用的宽基指数（通过 market_codes 注册表解析）。

用法:
    python get_daily_ohlc.py [code] [days]
    code: 标准代码或名称，如 000001 / 000300 / 沪深300 / sh000905 / 中证1000（默认 000001 上证综指）
    days: 往回取几个交易日（默认 1=最近交易日）

输出: JSON {code, name, date, open, high, low, close, prev_close, pct_chg, source}
"""
import sys, json, datetime, urllib.request, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from market_codes import resolve

UA = {'User-Agent': 'Mozilla/5.0'}


def fetch_daily_ohlc(tencent_code, days=1):
    """腾讯 fqkline 日线，取最近 N 个交易日（最后一个为最近交易日）"""
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
           f"param={tencent_code},day,,,60,qfq")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    node = data["data"][tencent_code]
    kline = node.get("qfqday") or node.get("day") or []
    if not kline:
        raise RuntimeError(f"腾讯接口未返回K线数据 ({tencent_code})")
    rows = kline[-days:] if days > 0 else kline
    out = []
    for r in rows:
        # r: [date, open, close, high, low, volume, ...]
        dt = r[0]
        o, c, h, l = float(r[1]), float(r[2]), float(r[3]), float(r[4])
        out.append({"date": dt, "open": o, "high": h, "low": l, "close": c})
    result = out[-1]
    # prev_close 取完整 kline 的倒数第二根（而非切片后 rows 的倒数第二根），
    # 否则 days=1 时 rows 只有 1 根，prev_close/pct_chg 会缺失
    if len(kline) >= 2:
        prev_close = float(kline[-2][2])  # kline 行格式 [date, open, close, high, low, ...]
        result["prev_close"] = prev_close
        result["pct_chg"] = round((result["close"] - prev_close) / prev_close * 100, 2)
    return result


if __name__ == "__main__":
    # 参数解析：第一个参数是 code（可省略），第二个是 days（可省略）
    code_arg = "000001"
    days = 1
    if len(sys.argv) > 1:
        code_arg = sys.argv[1]
    if len(sys.argv) > 2:
        try:
            days = int(sys.argv[2])
        except ValueError:
            pass

    resolved = resolve(code_arg)
    if not resolved:
        print(json.dumps({"error": f"无法识别的标的: {code_arg}", "source": "market_codes"},
                         ensure_ascii=False))
        sys.exit(1)
    if not resolved["tencent"]:
        print(json.dumps({"error": f"{resolved['name']} 腾讯接口暂不支持（数据源: {resolved['data_source']}）",
                          "code": resolved["code"], "source": "market_codes"},
                         ensure_ascii=False))
        sys.exit(1)

    try:
        r = fetch_daily_ohlc(resolved["tencent"], days)
        r["code"] = resolved["code"]
        r["name"] = resolved["name"]
        r["source"] = "tencent_fqkline"
        r["fetch_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(json.dumps(r, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e), "code": resolved["code"],
                          "name": resolved["name"], "source": "tencent_fqkline"},
                         ensure_ascii=False))
