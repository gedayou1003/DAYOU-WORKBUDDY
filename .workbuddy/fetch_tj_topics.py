#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉取 TRUTH AND JUSTICE 星球（88512145458842）历史帖子，保存原始内容，供回测对齐技术分析观点"""
import json, os, time, urllib.request, urllib.parse

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
    all_topics, seen, end_time = [], set(), None
    for _ in range(15):  # 最多 15 页 = 300 条
        try:
            d = fetch_page(end_time)
        except Exception as e:
            print(f"[err] {e}")
            break
        if not d.get("succeeded"):
            err = d.get('error')
            if isinstance(err, dict):
                err = err.get('message', 'unknown')
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
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    print(f"已保存 {len(items)} 条 -> {OUT}")
    if items:
        print(f"时间范围: {items[0]['create_time']} ~ {items[-1]['create_time']}")

if __name__ == "__main__":
    main()
