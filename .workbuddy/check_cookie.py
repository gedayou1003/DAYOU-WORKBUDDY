#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识星球 Cookie 校验 / 写入工具（2026-09-17 新增）

背景：`fetch_zsxq.py` 的 Cookie 通道（4 个星球）依赖 .workbuddy/zsxq_cookie.txt，
会话过期后接口返回 401/403，抓取侧 fail-fast 并输出 COOKIE_AUTH_FAILED=n。
本脚本用来把「更新 Cookie」这件事从手工试错变成一条命令。

用法（在项目根目录执行）：
  python .workbuddy/check_cookie.py                  # 校验当前 Cookie（不修改文件）
  python .workbuddy/check_cookie.py --from-clipboard # 从剪贴板读新 Cookie → 规范化写入 → 校验
  python .workbuddy/check_cookie.py --set "xxxx"     # 直接传入新 Cookie → 规范化写入 → 校验
  python .workbuddy/check_cookie.py --fix            # 仅规范化现有文件（去前缀/引号/换行）后再校验

退出码：0 = 全部星球鉴权通过；2 = 存在 401/403 或持续抖动；1 = 文件缺失/参数问题

⚠️ 关于 `succeeded=false`（2026-09-17 实测发现）：zsxq 接口在连发请求时会随机返回
   HTTP 200 + `succeeded:false` + `resp_data:{}`，**每次命中的星球不固定** —— 这是
   **限流抖动，不是鉴权失败**（鉴权失败是 401）。本脚本已内置 4 次退避重试 + 星球间
   1s 间隔，命中抖动时会标注「抖动 N 次后重试成功」，不要据此判断 Cookie 失效。

安全：只读写本地文件，不打印完整 Cookie 值（仅显示脱敏首尾）。
     本脚本经 git 同步；但它操作的 `zsxq_cookie.txt` 已在 .gitignore 内，**严禁跨机拷贝**
     （两台机器互相顶掉）。
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))

# 与 fetch_zsxq.py 保持单一数据源；导入失败则退回本文件内的副本
try:
    sys.path.insert(0, _HERE)
    from fetch_zsxq import COOKIE_FILE, COOKIE_GROUPS, UA
except Exception:  # 极端情况下仍可独立运行
    COOKIE_FILE = os.path.join(_HERE, "zsxq_cookie.txt")
    COOKIE_GROUPS = {
        "48841181481248": "大鹏鸟笔记",
        "48418411254128": "⭕ 短评&信息",
        "28888222154481": "180K Research",
        "51115885414844": "AI 产业链地图·Serenity速报",
    }
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def mask(s):
    """脱敏显示，便于确认换没换新值"""
    s = s or ""
    if len(s) <= 16:
        return s[:4] + "..." if len(s) > 4 else "***"
    return "%s...%s（%d 字符）" % (s[:8], s[-6:], len(s))


_QUOTES = ('"', "'", "\u201c", "\u201d", "\u2018", "\u2019")


def normalize(raw):
    """把用户从浏览器复制的内容规范成脚本要的形态

    容忍：BOM、首尾空白/换行、内部换行、`Cookie:` 前缀、外层引号、中文标点引号。
    产出：单行、无前缀、无引号的纯 cookie 值。

    注意：前缀与引号必须交替剥离到稳定态 —— 用户常见的 `Cookie: "xxx"` 形态里，
    先剥前缀才会露出引号（此顺序问题于 2026-09-17 实测发现并修正）。
    """
    if raw is None:
        return ""
    s = raw.replace("\ufeff", "")
    s = s.replace("\r", "\n")
    # 整段按行拼接（浏览器 DevTools 复制多行时常见）
    s = "; ".join(x.strip() for x in s.split("\n") if x.strip())
    s = s.strip()
    for _ in range(10):  # 交替剥离至稳定态
        before = s
        if s.lower().startswith("cookie:"):
            s = s[len("cookie:"):].strip()
        for q in _QUOTES:
            if len(s) >= 2 and s.startswith(q) and s.endswith(q):
                s = s[1:-1].strip()
                break
        if s == before:
            break
    return s.strip()


def read_clipboard():
    """Windows 剪贴板取文本"""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        return (r.stdout or "").strip()
    except Exception as e:
        print("[warn] 读取剪贴板失败：%r" % (e,))
        return ""


def write_cookie(value):
    os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
    with open(COOKIE_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(value)  # 纯文本、单行、无结尾换行
    print("已写入: %s" % COOKIE_FILE)


def probe(cookie, gid):
    """返回 (状态, 说明)。状态: ok / auth / flaky / err

    ⚠️ 实测发现（2026-09-17）：接口存在**限流抖动** —— 连发请求时会随机返回
    HTTP 200 + `succeeded:false` + `resp_data:{}`，且**每次命中的星球不同**。
    这不是鉴权失败（401 才是），退避重试即恢复。故此处内置 4 次退避重试，
    避免把抖动误报成「Cookie 失效」。
    """
    url = "https://api.zsxq.com/v2/groups/%s/topics?scope=all&count=3" % gid
    last = ""
    for attempt in range(4):
        req = urllib.request.Request(url, headers={
            "Cookie": cookie, "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://wx.zsxq.com", "Referer": "https://wx.zsxq.com/",
        })
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            if d.get("succeeded"):
                n = len(d.get("resp_data", {}).get("topics", []))
                extra = "" if attempt == 0 else "（抖动 %d 次后重试成功，非鉴权问题）" % attempt
                return "ok", "HTTP 200，最新一页 %d 条%s" % (n, extra)
            last = "HTTP 200 但 succeeded=false（接口限流抖动，非鉴权失败）"
            if attempt < 3:
                time.sleep(3 * (attempt + 1))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return "auth", "HTTP %d 鉴权失败（Cookie 已失效）" % e.code
            last = "HTTP %d" % e.code
            if attempt < 3:
                time.sleep(3 * (attempt + 1))
        except Exception as e:
            last = repr(e)[:90]
            if attempt < 3:
                time.sleep(3 * (attempt + 1))
    # 四种请求都试过仍不行：区分「一直抖动」与「网络不通」
    if last.startswith("HTTP 200"):
        return "flaky", last + "（退避重试 4 次仍不行，稍后重跑）"
    return "err", last


def validate(cookie, verbose=True):
    if not cookie:
        print("[FAIL] Cookie 为空 —— 文件 %s 不存在或内容为空" % COOKIE_FILE)
        return 1
    print("Cookie: %s" % mask(cookie))
    print()
    n_auth = n_flaky = n_err = n_ok = 0
    for gid, name in COOKIE_GROUPS.items():
        st, msg = probe(cookie, gid)
        flag = {"ok": "[ OK ]", "auth": "[401 ]", "flaky": "[抖动]", "err": "[ERR ]"}[st]
        print("%s %-26s %-10s %s" % (flag, name, gid, msg))
        if st == "ok":
            n_ok += 1
        elif st == "auth":
            n_auth += 1
        elif st == "flaky":
            n_flaky += 1
        else:
            n_err += 1
        time.sleep(1)  # 星球之间留间隔，降低触发限流抖动的概率
    print()
    if n_auth == 0 and n_flaky == 0 and n_err == 0:
        print("=> 全部 %d 个星球鉴权通过，Cookie 可用。" % len(COOKIE_GROUPS))
        return 0
    if n_auth:
        print("=> %d/%d 个星球 401，Cookie 已失效。请重新登录 wx.zsxq.com 后复制新的 Cookie。"
              % (n_auth, len(COOKIE_GROUPS)))
        return 2
    if n_flaky:
        print("=> %d 个星球持续返回 succeeded=false（限流抖动，非 Cookie 问题）——"
              "不影响鉴权结论，稍后重跑即可。" % n_flaky)
        return 2
    print("=> 存在网络/接口异常（非鉴权问题），稍后重试。")
    return 2


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--set", dest="value", default=None,
                    help="直接传入新的 Cookie 值")
    ap.add_argument("--from-clipboard", action="store_true",
                    help="从系统剪贴板读取新 Cookie")
    ap.add_argument("--fix", action="store_true",
                    help="规范化现有文件（去 Cookie: 前缀/引号/换行）后再校验")
    ap.add_argument("--no-write", action="store_true",
                    help="配合 --set/--from-clipboard：只校验不写文件")
    a = ap.parse_args()

    if not os.path.exists(COOKIE_FILE):
        print("[warn] 文件不存在，将创建：%s" % COOKIE_FILE)

    if a.value is not None or a.from_clipboard:
        raw = a.value if a.value is not None else read_clipboard()
        if not raw:
            print("[FAIL] 未取到内容（剪贴板为空？）")
            return 1
        newv = normalize(raw)
        print("输入原文: %s" % mask(raw.strip()))
        print("规范化后: %s" % mask(newv))
        if "zsxq_access_token" not in newv:
            print("[FAIL] 内容里没有 zsxq_access_token —— 复制的可能不是完整 Cookie，"
                  "请确认在 Network 面板复制的是 Request Headers 里的 Cookie 整行。")
            return 1
        if not a.no_write:
            write_cookie(newv)
        cookie = newv
    else:
        cookie = normalize(open(COOKIE_FILE, encoding="utf-8").read())
        if a.fix:
            write_cookie(cookie)
    print()
    return validate(cookie)


if __name__ == "__main__":
    sys.exit(main())
