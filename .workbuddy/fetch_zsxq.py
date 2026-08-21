#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量拉取知识星球主题并筛选时间窗口内容 (Skill通道 + Cookie通道)
v2：新增图片原图下载 + PDF/文件附件信息记录，确保晨报内容详尽不丢图
"""
import json, subprocess, urllib.request, os, sys, time
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

# 时间窗口：优先级 环境变量 > --window 参数 > 默认 morning（前一天16:00 ~ 当天9:00）
# 三档：morning(前一天16:00~9:00) / noon(9:00~12:30) / afternoon(12:30~16:00)
_win_arg = None
if "--window" in sys.argv:
    try:
        _win_arg = sys.argv[sys.argv.index("--window") + 1]
    except IndexError:
        pass

def _resolve_window():
    # 1) 环境变量覆盖（手动回测用）
    if os.environ.get("ZSXQ_WIN_START") and os.environ.get("ZSXQ_WIN_END"):
        return (datetime.fromisoformat(os.environ["ZSXQ_WIN_START"]),
                datetime.fromisoformat(os.environ["ZSXQ_WIN_END"]))
    today = datetime.now(CST).strftime("%Y-%m-%d")
    prev = (datetime.now(CST) - timedelta(days=1)).strftime("%Y-%m-%d")
    # 2) --window 参数
    if _win_arg == "noon":    # 午间：当天 9:00 ~ 12:30
        return (datetime.fromisoformat(f"{today}T09:00:00+08:00"),
                datetime.fromisoformat(f"{today}T12:30:00+08:00"))
    if _win_arg == "afternoon": # 下午：当天 12:30 ~ 16:00
        return (datetime.fromisoformat(f"{today}T12:30:00+08:00"),
                datetime.fromisoformat(f"{today}T16:00:00+08:00"))
    if _win_arg == "evening":   # 晚间：当天 12:00 ~ 19:00（2026-08-21 补齐，此前会误退回 morning）
        return (datetime.fromisoformat(f"{today}T12:00:00+08:00"),
                datetime.fromisoformat(f"{today}T19:00:00+08:00"))
    # 3) 默认 morning：前一天 16:00 ~ 当天 9:00
    return (datetime.fromisoformat(f"{prev}T16:00:00+08:00"),
            datetime.fromisoformat(f"{today}T09:00:00+08:00"))

WIN_START, WIN_END = _resolve_window()

SKILL_GROUPS = {
    "48888151228258": "卫斯李的投研笔记",
    "28855811424141": "⭕ 基业长青+",
    "88512145458842": "Truth and Justice",
    "51285445548824": "口罩哥的星球",
}
COOKIE_GROUPS = {
    "48841181481248": "大鹏鸟笔记",
    "48418411254128": "⭕ 短评&信息",
    "88888558554112": "信息平权",
    "28858555421441": "投行圈子~私密交流圈",
    "28888222154481": "180K Research",
    "51115885414844": "AI 产业链地图·Serenity速报",
}

_HERE = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(_HERE, "zsxq_cookie.txt")
IMG_DIR = os.path.join(_HERE, "zsxq_images")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

def _cookie():
    return open(COOKIE_FILE, encoding="utf-8").read().strip()

def fetch_skill(gid, limit=30):
    """通过 zsxq-cli 读取，带分页直到覆盖窗口（重度发帖星球单页30条可能不够）"""
    cli = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "npm", "zsxq-cli.cmd")
    all_topics, seen, end_time = [], set(), None
    while True:
        cmd = [cli, "group", "+topics", "--group-id", gid, "--limit", str(limit), "--json"]
        if end_time:
            cmd += ["--end-time", end_time]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        try:
            d = json.loads(r.stdout)
        except Exception as e:
            print(f"[skill-err {gid}] {e} :: {r.stderr[:200]}", file=sys.stderr)
            break
        topics = d.get("topics_brief", [])
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
            break  # 已翻到窗口开始之前
        end_time = topics[-1].get("create_time", "")
    return all_topics

def fetch_cookie(gid, count=20):
    """通过 Cookie 直连官方 API（带分页 + 重试与限流规避）"""
    cookie = _cookie()
    all_topics, seen, end_time = [], set(), None
    while True:
        url = f"https://api.zsxq.com/v2/groups/{gid}/topics?scope=all&count={count}"
        if end_time:
            url += f"&end_time={end_time}"
        topics = None
        for attempt in range(3):
            req = urllib.request.Request(url, headers={
                "Cookie": cookie, "User-Agent": UA, "Accept": "application/json, text/plain, */*",
                "Origin": "https://wx.zsxq.com", "Referer": "https://wx.zsxq.com/",
            })
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
            break  # 已翻到窗口开始之前
        end_time = topics[-1].get("create_time", "")
    return all_topics

def _download_image(url, save_path):
    """下载图片，失败返回 None"""
    try:
        req = urllib.request.Request(url, headers={
            "Cookie": _cookie(), "User-Agent": UA, "Referer": "https://wx.zsxq.com/"})
        data = urllib.request.urlopen(req, timeout=30).read()
        if len(data) < 1000:  # 太小可能是错误页
            return None
        with open(save_path, "wb") as f:
            f.write(data)
        return save_path
    except Exception as e:
        print(f"[img-err] {url[:80]} :: {e}", file=sys.stderr)
        return None

def extract_images(body, topic_id):
    """提取帖子图片并下载原图，返回本地路径列表"""
    imgs = body.get("images", []) if isinstance(body, dict) else []
    if not imgs:
        return []
    os.makedirs(IMG_DIR, exist_ok=True)
    local_paths = []
    for i, img in enumerate(imgs):
        # 优先 original 原图，其次 large，最后 thumbnail
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
        time.sleep(0.5)
    return local_paths

def extract_files(body):
    """提取文件/PDF 附件信息（不下载，仅记录元数据）"""
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
    """统一主题结构：兼容 Skill(brief扁平) 与 Cookie(嵌套) 两种格式"""
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
    # Skill 通道（zsxq-cli topics_brief）：images/files 在顶层而非 talk 内，需兜底
    # Cookie 通道（官方 API）：images/files 嵌套在 talk 内，body 已取到则不会误触发
    if not images:
        images = extract_images(t, t.get("topic_id"))
    if not files:
        files = extract_files(t)
    ct = t.get("create_time", "")
    return {"group": group_name, "gid": t.get("group", {}).get("group_id", ""),
            "topic_id": t.get("topic_id"), "type": ttype, "text": text,
            "create_time": ct, "images": images, "files": files}

def _parse_ct(ct):
    """把 create_time 字符串解析为带 CST 时区的 datetime，失败返回 None"""
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

def main():
    results = []
    for gid, name in SKILL_GROUPS.items():
        topics = fetch_skill(gid)
        for t in topics:
            n = norm_topic(t, name)
            if in_window(n["create_time"]):
                results.append(n)
        print(f"[skill] {name}: {len(topics)}条, 窗口内 {sum(1 for t in topics if in_window(t.get('create_time','')))}条", file=sys.stderr)
        time.sleep(3)
    for gid, name in COOKIE_GROUPS.items():
        topics = fetch_cookie(gid)
        for t in topics:
            n = norm_topic(t, name)
            if in_window(n["create_time"]):
                results.append(n)
        print(f"[cookie] {name}: {len(topics)}条, 窗口内 {sum(1 for t in topics if in_window(t.get('create_time','')))}条", file=sys.stderr)
        time.sleep(5)
    results.sort(key=lambda x: x["create_time"])
    # 去重（按 topic_id）
    seen, uniq = set(), []
    for x in results:
        tid = x["topic_id"]
        if tid not in seen:
            seen.add(tid)
            uniq.append(x)
    results = uniq
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".workbuddy", "zsxq_fetch_raw.json")
    with open(os.path.normpath(out), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    n_img = sum(len(x["images"]) for x in results)
    n_file = sum(len(x["files"]) for x in results)
    print(f"TOTAL_WINDOW={len(results)}  IMAGES={n_img}  FILES={n_file}")
    print(f"SAVED={os.path.normpath(out)}")

if __name__ == "__main__":
    main()
