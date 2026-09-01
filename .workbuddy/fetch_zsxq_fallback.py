#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""晚间快报兜底抓取：Skill 通道 token 失效时，全部星球走 Cookie 直连官方 API。
窗口 = 当天 12:00 ~ 19:00（evening）。
"""
import json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
_HERE = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(_HERE, "zsxq_cookie.txt")
IMG_DIR = os.path.join(_HERE, "zsxq_images")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

ALL_GROUPS = {
    "48888151228258": "卫斯李的投研笔记",
    "28855811424141": "⭕ 基业长青+",
    "88512145458842": "Truth and Justice",
    "48841181481248": "大鹏鸟笔记",
    "48418411254128": "⭕ 短评&信息",
    "28888222154481": "180K Research",
    "51115885414844": "AI 产业链地图·Serenity速报",
}

def _window():
    if os.environ.get("ZSXQ_WIN_START") and os.environ.get("ZSXQ_WIN_END"):
        return (datetime.fromisoformat(os.environ["ZSXQ_WIN_START"]),
                datetime.fromisoformat(os.environ["ZSXQ_WIN_END"]))
    today = datetime.now(CST).strftime("%Y-%m-%d")
    return (datetime.fromisoformat(f"{today}T12:00:00+08:00"),
            datetime.fromisoformat(f"{today}T19:00:00+08:00"))

WIN_START, WIN_END = _window()

def _cookie():
    return open(COOKIE_FILE, encoding="utf-8").read().strip()

def _parse_ct(ct):
    try:
        dt = datetime.fromisoformat(str(ct).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=CST)
        else:
            dt = dt.astimezone(CST)
        return dt
    except Exception:
        return None

def in_window(ct):
    dt = _parse_ct(ct)
    return WIN_START <= dt <= WIN_END if dt else False

def _download_image(url, save_path):
    try:
        req = urllib.request.Request(url, headers={
            "Cookie": _cookie(), "User-Agent": UA, "Referer": "https://wx.zsxq.com/"})
        data = urllib.request.urlopen(req, timeout=30).read()
        if len(data) < 1000:
            return None
        with open(save_path, "wb") as f:
            f.write(data)
        return save_path
    except Exception as e:
        print(f"[img-err] {url[:80]} :: {e}", file=sys.stderr)
        return None

def extract_images(body, topic_id):
    imgs = body.get("images", []) if isinstance(body, dict) else []
    if not imgs:
        return []
    os.makedirs(IMG_DIR, exist_ok=True)
    local_paths = []
    for i, img in enumerate(imgs):
        url = ""
        for key in ("original", "large", "thumbnail"):
            node = img.get(key) or {}
            url = node.get("url", "")
            if url:
                break
        if not url:
            continue
        ext = img.get("type", "jpg")
        save_path = os.path.join(IMG_DIR, f"{topic_id}_{i}.{ext}")
        p = _download_image(url, save_path)
        if p:
            local_paths.append(p)
        time.sleep(0.3)
    return local_paths

def extract_files(body):
    files = body.get("files", []) if isinstance(body, dict) else []
    out = []
    for f in files:
        out.append({
            "file_id": f.get("file_id"),
            "name": f.get("name", ""),
            "size": f.get("size", 0),
            "download_count": f.get("download_count", 0),
        })
    return out

def norm_topic(t, group_name):
    ttype = t.get("type", "talk")
    text = t.get("content", "") or ""
    body = t.get("talk") or t.get("q&a") or t.get("task") or t.get("solution") or {}
    if isinstance(body, dict):
        if not text:
            text = body.get("text", "")
        images = extract_images(body, t.get("topic_id"))
        files = extract_files(body)
    else:
        images, files = [], []
    return {"group": group_name, "gid": t.get("group", {}).get("group_id", ""),
            "topic_id": t.get("topic_id"), "type": ttype, "text": text,
            "create_time": t.get("create_time", ""),
            "images": images, "files": files}

def fetch_cookie(gid, name):
    cookie = _cookie()
    all_topics, seen, end_time = [], set(), None
    while True:
        url = f"https://api.zsxq.com/v2/groups/{gid}/topics?scope=all&count=20"
        if end_time:
            url += f"&end_time={end_time}"
        topics = None
        for attempt in range(3):
            req = urllib.request.Request(url, headers={
                "Cookie": cookie, "User-Agent": UA, "Accept": "application/json, text/plain, */*",
                "Origin": "https://wx.zsxq.com", "Referer": "https://wx.zsxq.com/"})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    d = json.loads(resp.read().decode("utf-8"))
                if d.get("succeeded"):
                    topics = d.get("resp_data", {}).get("topics", [])
                    break
                time.sleep(3 + attempt * 2)
            except Exception as e:
                print(f"[cookie-err {gid}] try{attempt}: {e}", file=sys.stderr)
                time.sleep(3 + attempt * 2)
        if not topics:
            break
        new = [t for t in topics if t.get("topic_id") not in seen]
        if not new:
            break
        for t in new:
            seen.add(t.get("topic_id"))
        all_topics.extend(new)
        oldest = _parse_ct(topics[-1].get("create_time", ""))
        if oldest is None or oldest < WIN_START:
            break
        end_time = topics[-1].get("create_time", "")
    return all_topics

def main():
    results = []
    for gid, name in ALL_GROUPS.items():
        topics = fetch_cookie(gid, name)
        cnt = 0
        for t in topics:
            n = norm_topic(t, name)
            if in_window(n["create_time"]):
                results.append(n)
                cnt += 1
        print(f"[cookie-all] {name}: {len(topics)}条, 窗口内 {cnt}条", file=sys.stderr)
        time.sleep(2)
    results.sort(key=lambda x: x["create_time"])
    seen, uniq = set(), []
    for x in results:
        if x["topic_id"] not in seen:
            seen.add(x["topic_id"])
            uniq.append(x)
    out = os.path.join(_HERE, "zsxq_fetch_raw.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(uniq, f, ensure_ascii=False, indent=1)
    print(f"TOTAL_WINDOW={len(uniq)}  IMAGES={sum(len(x['images']) for x in uniq)}  FILES={sum(len(x['files']) for x in uniq)}")
    print(f"SAVED={out}")

if __name__ == "__main__":
    main()
