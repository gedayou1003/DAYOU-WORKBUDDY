#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""星球内容窗口补档器（2026-09-17 新增）

用途：Cookie / 通道故障导致某期报告缺数据时，把「该报告窗口内实际存在的星球内容」
原样补录成档案，避免内容永久丢失。

触发场景：`fetch_zsxq.py` 报 `COOKIE_AUTH_FAILED=n`，报告成稿后 Cookie 才修好 ——
此时报告不能重跑（预判已落链、时点已过），但缺的内容应该留档。

与 `fetch_zsxq.py` 的区别：
  - fetch_zsxq 是「报告流水线输入」（写入 zsxq_fetch_raw.json，按当前档位窗口过滤）
  - 本脚本是「事后补档」（任意窗口、任意输出路径，不碰流水线产物）

用法（项目根目录）：
  # 补录晨报窗口（前一日 16:00 ~ 现在）
  python .workbuddy/backfill_zsxq_window.py

  # 指定窗口
  python .workbuddy/backfill_zsxq_window.py --since "2026-09-16 16:00" --until "2026-09-17 08:35"

  # 指定输出 / 带 JSON 原始数据
  python .workbuddy/backfill_zsxq_window.py --out outputs/补档_x.md --json-out .workbuddy/_x.json

  # 也补 skill 通道三球
  python .workbuddy/backfill_zsxq_window.py --groups cookie,skill

退出码：0 = 至少一个星球取数成功；2 = 全部失败
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

try:
    sys.path.insert(0, _HERE)
    from fetch_zsxq import COOKIE_FILE, COOKIE_GROUPS, SKILL_GROUPS, UA
except Exception:
    COOKIE_FILE = os.path.join(_HERE, "zsxq_cookie.txt")
    COOKIE_GROUPS = {
        "48841181481248": "大鹏鸟笔记",
        "48418411254128": "\u23ed 短评&信息",
        "28888222154481": "180K Research",
        "51115885414844": "AI \u4ea7\u4e1a\u94fe\u5730\u56fe\u00b7Serenity\u901f\u62a5",
    }
    SKILL_GROUPS = {
        "48888151228258": "\u536b\u65af\u674e\u7684\u6295\u7814\u7b14\u8bb0",
        "28855811424141": "\u23ed \u57fa\u4e1a\u957f\u9752+",
        "88512145458842": "Truth and Justice",
    }
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _cookie():
    return open(COOKIE_FILE, encoding="utf-8").read().strip()


def parse_dt(s, default):
    """宽松解析 'YYYY-MM-DD HH:MM' / ISO；返回带 CST 的 datetime"""
    if not s:
        return default
    s = s.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
            if fmt == "%Y-%m-%d":
                d = d.replace(hour=23 if default is None else 0, minute=59 if default is None else 0)
            return d.replace(tzinfo=CST)
        except ValueError:  # silent-ok: 多格式逐一尝试，本格式不匹配即试下一个
            continue
    # 兜底：交给 fromisoformat
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=CST)
    except Exception:
        raise SystemExit("[FAIL] 无法解析时间: %r（示例：2026-09-16 16:00）" % s)


def ct_of(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=CST)
    except Exception:  # silent-ok: 解析失败返回 None，窗口筛选处另计条数并打印
        return None


def strip_markup(s):
    """清理 <e .../> 标签（hashtag / 人名等）与残余 HTML，保留可读文本"""
    s = re.sub(r"<e[^>]*title=\"([^\"]*)\"[^>]*/?>",
               lambda m: urllib.parse.unquote(m.group(1)) + " ", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def get(url, headers, tries=4):
    """带退避重试的 GET。HTTP 200 + succeeded=false 视为限流抖动（见 fetch_zsxq 注释）"""
    for att in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
            if d.get("succeeded"):
                return d
            if att < tries - 1:
                time.sleep(3 * (att + 1))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return {"__auth_failed__": e.code}
            if att < tries - 1:
                time.sleep(3 * (att + 1))
        except Exception:
            if att < tries - 1:
                time.sleep(3 * (att + 1))
    return None


def fetch_group(gid, name, since, until, max_pages=5, count=20):
    """分页拉取直到早于 since。返回 (topics, error)"""
    headers = {
        "Cookie": _cookie(), "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://wx.zsxq.com", "Referer": "https://wx.zsxq.com/",
    }
    out, seen, end_time, err = [], set(), None, None
    for _ in range(max_pages):
        url = "https://api.zsxq.com/v2/groups/%s/topics?scope=all&count=%d" % (gid, count)
        if end_time:
            url += "&end_time=" + urllib.parse.quote(str(end_time))
        d = get(url, headers)
        if d is None:
            err = "取数失败（重试 4 次）"
            break
        if "__auth_failed__" in d:
            err = "HTTP %d 鉴权失败（Cookie 已失效）" % d["__auth_failed__"]
            break
        ts = d.get("resp_data", {}).get("topics", [])
        if not ts:
            break
        fresh = [t for t in ts if t.get("topic_id") not in seen]
        if not fresh:
            break
        for t in fresh:
            seen.add(t.get("topic_id"))
        out.extend(fresh)
        oldest = ct_of(ts[-1].get("create_time", ""))
        if oldest is None or oldest < since:
            break
        end_time = ts[-1].get("create_time", "")
        time.sleep(1.5)
    # 窗口筛选（2026-09-23 加固）：旧写法是
    #     [t for t in out if (ct_of(...) or since) >= since and (ct_of(...) or until) <= until]
    # —— 解析失败时 `None or since` 使两侧条件恒真，即**静默判成「窗口内」一律保留**，
    # 且同一条被 ct_of 解析两次。现改为显式循环：解析一次、保留原口径（宁多不少），
    # 但把解析不了的条数记下来打印 —— 否则「窗口外条目混进来」永远没人知道。
    picked, unparsed = [], []
    for t in out:
        ct = ct_of(t.get("create_time", ""))
        if ct is None:
            unparsed.append(str(t.get("create_time", "")))
            ct = since
        if since <= ct <= until:
            picked.append(t)
    if unparsed:
        print('[WARN] 窗口筛选：%d 条 create_time 无法解析（按「保留」处理，可能混入窗口外条目）：%s'
              % (len(unparsed), unparsed[:3]), file=sys.stderr)
    picked.sort(key=lambda t: t.get("create_time", ""))
    return picked, err


def extract_images(body):
    urls = []
    for im in (body.get("images", []) or []):
        u = (im.get("original") or im.get("large") or im.get("thumbnail") or {}).get("url", "")
        if u:
            urls.append(u.split("?")[0])
    return urls


def norm(t, gname):
    body = t.get("talk") or t.get("q&a") or t.get("task") or t.get("solution") or {}
    if not isinstance(body, dict):
        body = {}
    return {
        "group": gname,
        "topic_id": t.get("topic_id"),
        "type": t.get("type", "talk"),
        "time": str(t.get("create_time", ""))[:19],
        "text": strip_markup(body.get("text", "")),
        "images": extract_images(body),
        "files": [{"name": f.get("name", ""), "size": f.get("size", 0)}
                  for f in (body.get("files", []) or [])],
    }


def render_md(items, since, until, title):
    L = ["# %s" % title, "",
         "> **窗口**：%s ~ %s（CST）" % (since.strftime("%Y-%m-%d %H:%M"),
                                        until.strftime("%Y-%m-%d %H:%M")),
         "> 原样摘录，未做解读。", "",
         "| 星球 | 条数 |", "|---|---|"]
    cnt = Counter(x["group"] for x in items)
    for k, v in cnt.items():
        L.append("| %s | %d |" % (k, v))
    L += ["| **合计** | **%d** |" % len(items), "", "---", ""]
    cur = None
    for i, x in enumerate(items, 1):
        if x["group"] != cur:
            cur = x["group"]
            L += ["## %s" % cur, ""]
        L += ["### %d. [%s] topic_id `%s`" % (i, x["time"][5:16], x["topic_id"]), ""]
        L.append(x["text"] if x["text"] else "*（正文为图片/附件，无文字内容）*")
        L.append("")
        if x["files"]:
            L.append("**附件 %d 个**：" % len(x["files"]))
            for f in x["files"]:
                L.append("- `%s`（%.1f MB）" % (f["name"], (f["size"] or 0) / 1048576))
            L.append("")
        if x["images"]:
            L.append("**配图 %d 张**（原图 URL）：" % len(x["images"]))
            for u in x["images"][:12]:
                L.append("- %s" % u)
            L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="窗口起点，如 '2026-09-16 16:00'（默认：前一日16:00）")
    ap.add_argument("--until", default=None, help="窗口终点（默认：现在）")
    ap.add_argument("--groups", default="cookie", help="cookie / skill / cookie,skill")
    ap.add_argument("--out", default=None, help="Markdown 输出路径")
    ap.add_argument("--json-out", default=None, help="额外写出 JSON 路径")
    ap.add_argument("--label", default=None, help="标题里的档位说明")
    ap.add_argument("--max-pages", type=int, default=5)
    a = ap.parse_args()

    now = datetime.now(CST)
    default_since = datetime.fromisoformat(
        (now - timedelta(days=1)).strftime("%Y-%m-%d") + "T16:00:00+08:00")
    since = parse_dt(a.since, default_since)
    until = parse_dt(a.until, now) if a.until else now
    if since >= until:
        print("[FAIL] 窗口起点晚于或等于终点"); return 1

    want = [g.strip() for g in a.groups.split(",") if g.strip()]
    targets = []
    if "cookie" in want:
        targets += [(g, n, "cookie") for g, n in COOKIE_GROUPS.items()]
    if "skill" in want:
        targets += [(g, n, "skill") for g, n in SKILL_GROUPS.items()]

    print("窗口: %s ~ %s" % (since.strftime("%Y-%m-%d %H:%M"), until.strftime("%Y-%m-%d %H:%M")))
    print("目标: %d 个星球\n" % len(targets))

    items, ok_n, fail = [], 0, []
    for gid, name, chan in targets:
        if chan == "skill":
            # skill 通道走 zsxq-cli，窗口内条数由 CLI 返回，这里只记总量提示
            print("[skip] %-26s skill 通道请用 fetch_zsxq.py（本脚本专做 cookie 补档）" % name)
            continue
        ts, err = fetch_group(gid, name, since, until, a.max_pages)
        if err:
            fail.append((name, err))
            print("[FAIL] %-26s %s" % (name, err))
        else:
            ok_n += 1
            print("[ OK ] %-26s 窗口内 %d 条" % (name, len(ts)))
            if not ts:
                newest = None
                d = get("https://api.zsxq.com/v2/groups/%s/topics?scope=all&count=1" % gid,
                        {"Cookie": _cookie(), "User-Agent": UA,
                         "Accept": "application/json, text/plain, */*",
                         "Origin": "https://wx.zsxq.com", "Referer": "https://wx.zsxq.com/"})
                if d and d.get("resp_data", {}).get("topics"):
                    newest = d["resp_data"]["topics"][0].get("create_time", "")[:19]
                print("        └ 该球窗口内 0 条%s" % ("；最新帖 %s（早于窗口，非故障）" % newest if newest else ""))
        for t in ts:
            items.append(norm(t, name))
        time.sleep(2)

    if not items and not ok_n:
        print("\n=> 全部星球取数失败，未生成档案。")
        return 2

    items.sort(key=lambda x: x["time"])
    label = a.label or "Cookie 断档补档"
    out = a.out or os.path.join(_ROOT, "outputs",
                                "补档_星球窗口内容_%s.md" % now.strftime("%Y-%m-%d"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    md = render_md(items, since, until,
                   "补档 · %s · %s" % (label, now.strftime("%Y-%m-%d")))
    open(out, "w", encoding="utf-8").write(md)
    print("\n共 %d 条 → %s" % (len(items), out))

    if a.json_out:
        os.makedirs(os.path.dirname(a.json_out) or ".", exist_ok=True)
        json.dump(items, open(a.json_out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("JSON → %s" % a.json_out)

    if fail:
        print("\n失败星球:")
        for n, e in fail:
            print("  - %s: %s" % (n, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
