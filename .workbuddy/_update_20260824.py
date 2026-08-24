#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-08-24 8:30 晨报（最新代码重跑）— 复盘 + 新预判"""
import json, os
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
NOW = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
TODAY = "2026-08-24"
TOMORROW = "2026-08-25"
WKD = "周二"  # 8/25 是周二

PROJ = os.path.dirname(os.path.abspath(__file__))
FC = os.path.join(PROJ, "forecast_chain.json")
CC = os.path.join(PROJ, "consensus_chain.json")

ACTUAL = {"open": 3902.7, "high": 3910.24, "low": 3867.43, "close": 3874.99, "pct": -0.77, "prev_close": 3905.2}

def review_close():
    """复盘 8-21-close（上周五预测今天）"""
    fcc = json.load(open(FC, encoding="utf-8"))
    recs = fcc if isinstance(fcc, list) else fcc.get("records", [])
    r = next((x for x in recs if x["id"] == "2026-08-21-close"), None)
    if not r: return
    r["status"] = "verified"
    r["review"] = {
        "verified_at": NOW,
        "actual": ACTUAL,
        "direction": "❌ 相反（预测偏多，实际-0.77%下跌）",
        "range": "⚠️ 偏移（预测3884-3930，实际3867-3910，向下偏移17点）",
        "support": "❌ 跌破（预测3883.79，实际最低3867.43，跌破约16点）",
        "resistance": "✅ 未触及（预测3927.85，实际最高3910.24）",
        "bias_type": ["方向错误（偏多→偏空）", "支撑跌破（3883→3867）", "区间向下偏移", "压力位未触及"],
        "foreseeable": "部分可预料",
        "foresee_reason": "15F 带宽极度收口已是变盘前兆，预判选了「偏多」剧本未选「方向不明」，是剧本选择错误；支撑跌破为 3883 整数心理位失守引发技术止损盘"
    }
    json.dump(fcc, open(FC, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("✅ 8-21-close 已复盘")

def review_morning():
    """复盘 8-24-morning（今早预测今天）"""
    fcc = json.load(open(FC, encoding="utf-8"))
    recs = fcc if isinstance(fcc, list) else fcc.get("records", [])
    r = next((x for x in recs if x["id"] == "2026-08-24-morning"), None)
    if not r: return
    r["status"] = "verified"
    r["review"] = {
        "verified_at": NOW,
        "actual": ACTUAL,
        "direction": "❌ 相反（预测震荡偏多，实际下跌-0.77%）",
        "range": "⚠️ 偏移（预测3884-3930，实际3867-3910，向下偏移）",
        "support": "❌ 跌破（预测3883.79，实际3867.43，跌破约16点）",
        "resistance": "✅ 未触及（预测3927.85，实际3910.24）",
        "bias_type": ["方向错误", "支撑跌破", "区间向下偏移", "压力位未触及"],
        "foreseeable": "部分可预料",
        "foresee_reason": "confidence 原文已标「中等」+「15F极度收口变盘在即」；变盘方向选错，未给「方向不明」备选"
    }
    json.dump(fcc, open(FC, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("✅ 8-24-morning 已复盘")

def add_new_forecast():
    """追加新预判（8-25 周二）"""
    fcc = json.load(open(FC, encoding="utf-8"))
    recs = fcc if isinstance(fcc, list) else fcc.get("records", [])
    new = {
        "id": "2026-08-24-morning-v2",
        "report_type": "晨报（8:30 最新代码重跑版）",
        "created_at": NOW,
        "target": f"{TOMORROW}（{WKD}）",
        "direction": "偏空（破位下行后低位震荡，弱势未改）",
        "range": "3858-3900",
        "support": 3867.43,
        "support_basis": "今日最低 3867.43（-0.97% 心理整数位）+ 15F 前低 3860 区域，跌破看 3850 整数关",
        "resistance": 3898.75,
        "resistance_basis": "5F 一卖@3898.75（+0.61%）+ 60F 一卖@3911.08（+0.93%）= 双压力区；3911 是今日冲高回落位",
        "confidence": "中等偏低（今日已破位+大级别周线一卖@3968 趋势向下，弱势惯性；唯一缓冲：5F/15F 极低位有反弹动能）",
        "evidence": {
            "engineA": "日线观望-0.112/down + 60F观望-0.196/sideways + 15F观望-0.091/sideways + 5F观望-0.198/sideways — 全级别观望偏空",
            "engineB": "日线一卖@3847 + 周线一卖@3968 + 60F一卖三卖@3911（强压力） + 15F三买@3895.91（已破失效） + 5F一卖@3898.75",
            "actual_today": "开3902.7 高3910.24 低3867.43 收3874.99（-0.77%），跌破支撑3883.79 16点"
        },
        "summary": "今日已破位下行（-0.77% 跌破支撑），明早延续低位震荡为主；下沿看 3867/3850，上沿 3898/3911 反压较重。操作上反弹不追、破位不抄，区间内高抛低吸为主。",
        "status": "pending"
    }
    recs.append(new)
    if isinstance(fcc, list):
        out = recs
    else:
        out = fcc
        out["records"] = recs
    json.dump(out, open(FC, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"✅ 已追加新预判: {new['id']}（预测 {TOMORROW}）")

def review_consensus():
    """复盘共识链 8-24-morning（事件类不参与复盘，但更新状态）"""
    cc = json.load(open(CC, encoding="utf-8"))
    recs = cc if isinstance(cc, list) else cc.get("records", [])
    r = next((x for x in recs if x["id"] == "2026-08-24-morning"), None)
    if not r: return
    r["status"] = "verified"
    r["review"] = {
        "verified_at": NOW,
        "note": "本期共识为事件类（长存IPO/AI算力/6G等），不参与走势兑现验证；仅作存档。所有 topic.type='event' 标记为'已记录'。"
    }
    json.dump(cc, open(CC, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("✅ 共识链 8-24-morning 已标记为已复盘（事件类）")

if __name__ == "__main__":
    review_close()
    review_morning()
    add_new_forecast()
    review_consensus()
    print("\n=== 完成 ===")
