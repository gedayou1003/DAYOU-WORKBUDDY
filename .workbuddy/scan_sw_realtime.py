# -*- coding: utf-8 -*-
"""申万一级行业「实时」强弱榜 —— 东方财富妙想（mx-finance-data）封装。

替代/补充 scan_ths.py 的滞后数据源（同花顺 T+1）：
- 东财妙想能识别「申万」分类，返回「XX(申万)(指数)」实时涨跌幅（时间戳到当前分钟）
- 本脚本一次批量查 29 个申万一级行业 + 单独查「机械设备」（批量会被漏）
- 「综合」兜底分类名称太泛，东财识别不出，标为缺失
- 输出：backtest_data/scan_result_sw_realtime.json + 终端打印实时强弱榜

用法：
    python .workbuddy/scan_sw_realtime.py
依赖：httpx（已装 venv）；东财妙想 skill ~/.workbuddy/skills/mx-finance-data
"""
import subprocess, os, json, glob, sys, re
import pandas as pd

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

PY = os.path.expanduser("~/.workbuddy/binaries/python/envs/default/Scripts/python.exe")
GET_DATA = os.path.expanduser("~/.workbuddy/skills/mx-finance-data/scripts/get_data.py")
PROJECT_ROOT = os.path.dirname(HERE)   # .workbuddy 的上一级 = 项目根目录
OUT_DIR = os.path.join(PROJECT_ROOT, "miaoxiang", "mx_finance_data")

SKIP = {"综合", "机械设备"}   # 综合识别不出；机械设备单独查
BATCH = [n for n in SW_LIST if n not in SKIP]
SOLO = ["机械设备"]


def call_mx(names):
    """调用东财妙想，返回最新生成的 xlsx 路径"""
    os.makedirs(OUT_DIR, exist_ok=True)
    q = "查询" + "、".join("申万" + n for n in names) + "行业的涨跌幅"
    before = set(glob.glob(os.path.join(OUT_DIR, "*.xlsx")))
    subprocess.run([PY, GET_DATA, "--query", q, "--indicators", "涨跌幅"],
                   capture_output=True, text=True, timeout=180, cwd=PROJECT_ROOT)
    after = set(glob.glob(os.path.join(OUT_DIR, "*.xlsx")))
    new = sorted(after - before)
    return new[-1] if new else None


def fetch_akshare_fallback():
    """东财妙想失败（API Key 风控等）时的 akshare 兜底：
    index_realtime_sw 拿申万一级 31 行业收盘涨跌幅，返回 items 列表。"""
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


def parse_realtime(xlsx_path):
    """解析 xlsx 里「当前的涨跌幅」sheet，返回 {行业名: 涨跌幅%, 时间戳}
    兼容两种格式：长表（列名「涨跌幅」，行=行业名+值）与宽表（列名=行业名，行=涨跌幅+值，单实体查时出现）
    """
    xl = pd.ExcelFile(xlsx_path)
    result, ts = {}, None
    for sn in xl.sheet_names:
        if "当前的涨跌幅" not in sn:
            continue
        df = pd.read_excel(xlsx_path, sheet_name=sn)
        cols = list(df.columns)
        if not cols:
            continue
        if str(cols[0]).strip() == "涨跌幅":
            # 长表：列=["涨跌幅", 时间戳]，行=[行业名, pct]
            if len(cols) >= 2:
                ts = str(cols[1])
            for _, row in df.iterrows():
                name_raw = str(row.iloc[0])
                pct = str(row.iloc[1])
                for sw in SW_LIST:
                    if sw in name_raw and sw != "综合":
                        result[sw] = pct
                        break
        else:
            # 宽表：列=[行业名, 时间戳]，行=["涨跌幅", pct]
            if len(cols) >= 2:
                ts = str(cols[1])
            name_raw = str(cols[0])
            pct = None
            for _, row in df.iterrows():
                if str(row.iloc[0]).strip() == "涨跌幅":
                    pct = str(row.iloc[1])
                    break
            if pct:
                for sw in SW_LIST:
                    if sw in name_raw and sw != "综合":
                        result[sw] = pct
                        break
    return result, ts


def main():
    data, ts, source = {}, None, "eastmoney-miaoxiang"
    # 1) 批量查 29 个（东财妙想）
    p = call_mx(BATCH)
    if p:
        r, t = parse_realtime(p)
        data.update(r)
        ts = t or ts
        print(f"[批量] 拿到 {len(r)} 个行业")
    else:
        print("[批量] ❌ 东财妙想未生成 xlsx（API Key 风控?），fallback akshare")
        import datetime
        for x in fetch_akshare_fallback():
            data[x['name']] = f"{x['pct']:+.2f}%"
        ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        source = "akshare-shenwan-close"

    # 2) 单独查机械设备（仅东财成功时，akshare 兜底已全覆盖）
    if source == "eastmoney-miaoxiang":
        p2 = call_mx(SOLO)
        if p2:
            r2, t2 = parse_realtime(p2)
            data.update(r2)
            ts = t2 or ts
            print(f"[单独] 机械设备 = {r2.get('机械设备', '缺失')}")

    # 3) 排序 + 输出
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

    print(f"\n===== 申万一级行业实时强弱榜（{ts}）=====")
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
