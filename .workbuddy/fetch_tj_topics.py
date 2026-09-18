#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉取目标星球（88512145458842）历史帖子，保存原始内容，供回测对齐技术分析观点。

2026-09-18 审计 P1-4 加固
-----------------------
改前：请求异常 / 接口返回失败 → `break` 后**照旧写文件并打印「已保存 N 条」、退出 0** ——
半截数据被当成完整历史落盘，且目标文件在 gitignore 里、覆盖后不可恢复。
改后：出错或 0 条 → **不覆盖既有回测数据**，改写带时间戳的旁路文件；退出码 2。

退出码：0 正常 · 1 Cookie 文件缺失 · 2 降级（请求异常 / 接口失败 / 0 条）
"""
import json, os, sys, time, urllib.request, urllib.parse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(HERE, "zsxq_cookie.txt")
OUT = os.path.join(HERE, "backtest_data", "tj_topics.json")
GID = "88512145458842"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

def cookie():
    return open(COOKIE_FILE, encoding="utf-8").read().strip()

def fetch_page(end_time=None):
    url = f"https://api.zsxq.com/v2/groups/{GID}/topics?scope=all&count=20"
    if end_time:
        url += f"&end_time={urllib.parse.quote(end_time)}"
    req = urllib.request.Request(url, headers={
        "Cookie": cookie(), "User-Agent": UA, "Accept": "application/json, text/plain, */*",
        "Origin": "https://wx.zsxq.com", "Referer": "https://wx.zsxq.com/",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    if not os.path.exists(COOKIE_FILE):
        print(f"[FAIL] 找不到 Cookie 文件：{COOKIE_FILE}")
        return 1

    all_topics, seen, end_time = [], set(), None
    errors = []
    for _ in range(15):  # 最多 15 页 = 300 条
        try:
            d = fetch_page(end_time)
        except Exception as e:
            errors.append(f'请求异常：{e}')
            print(f"[err] {e}")
            break
        if not d.get("succeeded"):
            err = d.get('error')
            if isinstance(err, dict):
                err = err.get('message', 'unknown')
            errors.append(f'接口返回失败：{err}')
            print(f"[fail] {err}")
            break
        topics = d.get("resp_data", {}).get("topics", [])
        if not topics:
            break
        new = [t for t in topics if t.get("topic_id") not in seen]
        if not new:
            break
        for t in new:
            seen.add(t.get("topic_id"))
        all_topics.extend(new)
        # 提取正文
        end_time = topics[-1].get("create_time", "")
        time.sleep(1)
    print(f"拉取 {len(all_topics)} 条")

    # 提取精简字段
    items = []
    for t in all_topics:
        body = t.get("talk") or t.get("q&a") or t.get("solution") or {}
        text = (t.get("content") or "") or (body.get("text") if isinstance(body, dict) else "") or ""
        items.append({
            "topic_id": t.get("topic_id"),
            "create_time": t.get("create_time"),
            "text": text,
        })
    items.sort(key=lambda x: x["create_time"])

    degraded = []
    if errors:
        degraded += errors
    if not items:
        degraded.append('拉取到 0 条')

    if degraded:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        bypass = os.path.join(os.path.dirname(OUT), f'tj_topics_degraded_{stamp}.json')
        with open(bypass, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
        print(f'[WARN] 本轮降级（{ "；".join(degraded) }）：已跳过覆盖 {OUT}')
        print(f'       本轮 {len(items)} 条落在旁路文件：{bypass}')
        return 2

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    with open(tmp, encoding='utf-8') as f:
        if len(json.load(f)) != len(items):
            os.remove(tmp)
            raise RuntimeError('回读断言失败：写入 %d 条与读回不一致' % len(items))
    os.replace(tmp, OUT)
    print(f"已保存 {len(items)} 条 -> {OUT}")
    print(f"时间范围: {items[0]['create_time']} ~ {items[-1]['create_time']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
