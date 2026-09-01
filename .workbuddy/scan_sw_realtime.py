# -*- coding: utf-8 -*-
"""申万一级行业「实时」强弱榜 —— akshare index_realtime_sw（唯一数据源）。

背景（2026-09-01，东财妙想弃用）：
- 原东财妙想（mx-finance-data）反复 API Key 风控（403），已弃用。
- 实测同花顺 thsdk：ths_industry() 是「同花顺行业 90 个」分类（非申万一级），
  wencai_nlp("申万行业排名") 被理解成「申万宏源」个股，均不适合替代。
- 实测申万 sw-industry-index skill：index_hist_sw 是历史日线（收盘后更新），非盘中实时。
- akshare index_realtime_sw 返回 31 个申万一级行业「最新价/昨收盘」，可算盘中实时涨跌幅，
  完美替代东财妙想，故扶正为唯一主源。

输出：backtest_data/scan_result_sw_realtime.json + 终端打印实时强弱榜

用法：python .workbuddy/run.py scan_sw_realtime.py
依赖：akshare（venv 已装）
"""
import os, json, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    from scan_ths import SW_NAMES
except Exception:
    SW_NAMES = {}

SW_LIST = [SW_NAMES[k] for k in sorted(SW_NAMES)] if SW_NAMES else [
    "农林牧渔","基础化工","钢铁","有色金属","电子","家用电器","食品饮料","纺织服饰",
    "轻工制造","医药生物","公用事业","交通运输","房地产","商贸零售","社会服务","综合",
    "建筑材料","建筑装饰","电力设备","国防军工","计算机","传媒","通信","银行","非银金融",
    "汽车","机械设备","煤炭","石油石化","环保","美容护理",
]


def fetch_realtime():
    """akshare 申万一级 31 行业盘中实时涨跌幅，返回 items 列表 [{name, pct}]"""
    import akshare as ak
    df = ak.index_realtime_sw(symbol='一级行业')
    items = []
    for _, row in df.iterrows():
        name = row['指数名称']
        prev = float(row['昨收盘']); cur = float(row['最新价'])
        pct = round((cur - prev) / prev * 100, 2)
        items.append({'name': name, 'pct': pct})
    items.sort(key=lambda x: -x['pct'])
    return items


def main():
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    source = "akshare-shenwan-realtime"
    data = {}
    for x in fetch_realtime():
        data[x['name']] = f"{x['pct']:+.2f}%"

    items = []
    for sw in SW_LIST:
        pct = data.get(sw)
        if pct is None:
            continue
        try:
            v = float(pct.replace("%", "").strip())
        except Exception:
            continue
        items.append({"name": sw, "pct": v})
    items.sort(key=lambda x: -x["pct"])

    out = {
        "source": source,
        "ts": ts,
        "count": len(items),
        "missing": [n for n in SW_LIST if n not in data],
        "industries": items,
    }
    os.makedirs(os.path.join(HERE, "backtest_data"), exist_ok=True)
    with open(os.path.join(HERE, "backtest_data", "scan_result_sw_realtime.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n===== 申万一级行业实时强弱榜（{ts}，source={source}）=====")
    print(f"  领涨 TOP5：")
    for x in items[:5]:
        print(f"    {x['name']:6s} {x['pct']:+.2f}%")
    print(f"  领跌 TOP5：")
    for x in items[-5:]:
        print(f"    {x['name']:6s} {x['pct']:+.2f}%")
    print(f"  缺失: {out['missing']}")
    print(f"结果已保存 backtest_data/scan_result_sw_realtime.json（{len(items)} 个行业）")


if __name__ == "__main__":
    main()
