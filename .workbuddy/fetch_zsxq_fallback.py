#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""晚间快报兜底抓取：Skill 通道 token 失效时，全部星球走 Cookie 直连官方 API。
窗口 = 当天 12:00 ~ 19:00（evening）。

2026-09-18 审计 P1-4 加固
-----------------------
改前：某星球退避重试后仍 0 条 → 静默继续；末尾**无条件覆盖主快照**并打印 `SAVED=`、
退出 0 —— 整星球漏抓被伪装成成功，且主快照不可恢复（既不在 git 又被备份排除）。
改后：失败星球计数 → 降级时不覆盖主快照、改写时间戳旁路文件；复用 `fetch_zsxq.save_snapshot()`
（原子写 + 回读断言 + meta），并把窗口标签改成 evening，避免 meta 记成晨报窗口。

退出码：0 正常 · 1 Cookie 文件缺失 · 2 降级（有星球 0 条 / 窗口内 0 条）
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
    except Exception:  # silent-ok: 解析失败返回 None，窗口过滤处另计条数并上报
        return None

def in_window(ct):
    dt = _parse_ct(ct)
    if dt is None:
        # 2026-09-23 加固：解析不了要出声（旧实现静默判 False 丢弃）。与 fetch_zsxq 同口径。
        _BAD_CT.append(str(ct))
        return False
    return WIN_START <= dt <= WIN_END


# 本轮窗口过滤中 create_time 解析失败的条目；写 meta 前同步给 fetch_zsxq._BAD_CT
_BAD_CT = []

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
    if not os.path.exists(COOKIE_FILE):
        print(f"[FAIL] 找不到 Cookie 文件：{COOKIE_FILE}", file=sys.stderr)
        return 1

    results, failed = [], []
    del _BAD_CT[:]                      # 每次运行从零起算
    for gid, name in ALL_GROUPS.items():
        topics = fetch_cookie(gid, name)
        cnt = 0
        for t in topics:
            n = norm_topic(t, name)
            if in_window(n["create_time"]):
                results.append(n)
                cnt += 1
        print(f"[cookie-all] {name}: {len(topics)}条, 窗口内 {cnt}条", file=sys.stderr)
        if not topics:                      # 退避 3 次仍 0 条 → 记入降级（旧实现静默继续）
            failed.append(gid)
        time.sleep(2)
    if _BAD_CT:
        print('[WARN] 窗口过滤：%d 条 create_time 无法解析（已按窗口外丢弃）：%s'
              % (len(_BAD_CT), _BAD_CT[:3]), file=sys.stderr)
    results.sort(key=lambda x: x["create_time"])
    seen, uniq = set(), []
    for x in results:
        if x["topic_id"] not in seen:
            seen.add(x["topic_id"])
            uniq.append(x)

    # 降级判定（2026-09-18 审计 P1-4）
    # 改前：无论成功失败都无条件覆盖主快照、打印 SAVED= 并退出 0 —— 整星球漏抓被伪装成成功。
    degraded = []
    if failed:
        degraded.append('退避重试后仍 0 条 %d 个星球（gid: %s）'
                        % (len(failed), ', '.join(sorted(failed))))
    if not uniq:
        degraded.append('时间窗口内 0 条')

    # 复用 fetch_zsxq 的快照守卫（降级不覆盖主快照 / 原子写 + 回读断言 / 写 meta），
    # 避免同一个「不可恢复覆盖」隐患在两个脚本里各留一份。
    # 窗口与档位标签必须改成**本脚本自己的**，否则 meta 会把晚间兜底记成晨报窗口。
    import fetch_zsxq as fz
    fz.WIN_START, fz.WIN_END = WIN_START, WIN_END
    fz._win_arg = 'evening'
    fz._BAD_CT[:] = _BAD_CT          # 让复用的 save_snapshot 把本轮的解析失败数一并写进 meta
    saved, is_main = fz.save_snapshot(uniq, degraded)

    print(f"TOTAL_WINDOW={len(uniq)}  IMAGES={sum(len(x['images']) for x in uniq)}  "
          f"FILES={sum(len(x['files']) for x in uniq)}")
    if is_main:
        print(f"SAVED={saved}")
    else:
        print(f"SAVED_BYPASS={saved}")
        print("MAIN_SNAPSHOT_UNCHANGED=%s  ← 本轮降级（%s），未用残缺数据覆盖主快照"
              % (fz.MAIN_SNAPSHOT, '；'.join(degraded)))
        print("[WARN] 主快照仍是上一次的完整内容，**不代表本轮结果**。", file=sys.stderr)

    # 退出码：与其他脚本统一（0 通过 · 1 ERROR · 2 WARN）
    return 2 if degraded else 0


if __name__ == "__main__":
    sys.exit(main())
