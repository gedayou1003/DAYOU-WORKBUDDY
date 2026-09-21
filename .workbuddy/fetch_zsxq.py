#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量拉取知识星球主题并筛选时间窗口内容 (Skill通道 + Cookie通道)
v2：新增图片原图下载 + PDF/文件附件信息记录，确保晨报内容详尽不丢图
"""
import json, subprocess, urllib.request, urllib.error, os, shutil, sys, time
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

# 时间窗口铁律（2026-08-26 用户明确，自检必查项）：
#   - 8点自动（默认 morning）：前一天16:00 ~ 当前时刻（8点跑时≈前一天16:00~8:00）
#   - 手动跑：必须取「8:00 ~ 当前时刻」最新内容，用 --window noon（8:00~now）
#   - 结束时间一律用「当前时刻 now」，禁止写死（否则手动延迟跑会漏掉预设时间之后的内容，如 T&J 12:36）
#   - 优先级：环境变量 ZSXQ_WIN_START/END > --window 参数 > 默认 morning
# 窗口取值白名单（2026-09-21 加固）。
# 旧实现的两个静默回退都会让**窗口悄悄变窄且零提示**：
#   ① `--window` 后面没跟值 → IndexError 被 `except: pass` 吞掉 → _win_arg=None；
#   ② `--window nooon` 拼错 → 下面三个 if 全不匹配 → 落回默认 morning。
# 两者都退回「前一天 16:00 ~ now」，与「漏掉整个周末」属同一族事故（2026-09-21 真实发生）。
# 现在非法取值一律显式报错退出，绝不静默回退。
WINDOWS = ("morning", "noon", "afternoon", "evening")
_win_arg = None
if "--window" in sys.argv:
    _wi = sys.argv.index("--window")
    if _wi + 1 >= len(sys.argv):
        sys.stderr.write("[FAIL] --window 缺少取值（可选：%s）\n" % " / ".join(WINDOWS))
        sys.exit(1)
    _win_arg = sys.argv[_wi + 1]
    if _win_arg not in WINDOWS:
        sys.stderr.write("[FAIL] 未知窗口 %r（可选：%s）\n"
                         % (_win_arg, " / ".join(WINDOWS)))
        sys.exit(1)

def _resolve_window():
    # 1) 环境变量覆盖（手动回测用）
    if os.environ.get("ZSXQ_WIN_START") and os.environ.get("ZSXQ_WIN_END"):
        return (datetime.fromisoformat(os.environ["ZSXQ_WIN_START"]),
                datetime.fromisoformat(os.environ["ZSXQ_WIN_END"]))
    now = datetime.now(CST)
    today = now.strftime("%Y-%m-%d")
    prev = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    # 2) --window 参数（结束时间统一用「当前时间」，避免手动延迟跑漏掉预设时间之后的内容，如 T&J 12:36）
    if _win_arg == "noon":    # 午间：当天 8:00 ~ 当前时间
        return (datetime.fromisoformat(f"{today}T08:00:00+08:00"), now)
    if _win_arg == "afternoon": # 下午：当天 12:30 ~ 当前时间
        return (datetime.fromisoformat(f"{today}T12:30:00+08:00"), now)
    if _win_arg == "evening":   # 晚间：当天 12:00 ~ 当前时间
        return (datetime.fromisoformat(f"{today}T12:00:00+08:00"), now)
    if _win_arg == "morning":   # 晨报：前一天 16:00 ~ 当前时间（显式指定）
        return (datetime.fromisoformat(f"{prev}T16:00:00+08:00"), now)
    # 3) 未传 --window → 默认 morning：前一天 16:00 ~ 当前时间
    #    注：_win_arg 现在有白名单兜底，走到这里只可能是「确实没传」，
    #    不会再出现「传了但拼错却静默落回默认」的情况。
    return (datetime.fromisoformat(f"{prev}T16:00:00+08:00"), now)

WIN_START, WIN_END = _resolve_window()

SKILL_GROUPS = {
    "48888151228258": "卫斯李的投研笔记",
    "28855811424141": "⭕ 基业长青+",
    "88512145458842": "Truth and Justice",
}
COOKIE_GROUPS = {
    "48841181481248": "大鹏鸟笔记",
    "48418411254128": "⭕ 短评&信息",
    "28888222154481": "180K Research",
    "51115885414844": "AI 产业链地图·Serenity速报",
}

_HERE = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(_HERE, "zsxq_cookie.txt")
IMG_DIR = os.path.join(_HERE, "zsxq_images")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# 本轮已确认 Cookie 鉴权失败的星球 gid（401/403 fail-fast 去重，避免重复提示与重复请求）
auth_failed = set()
# 本轮「限流抖动」且退避重试后仍无数据的星球 gid（区别于鉴权失败，2026-09-17 新增）
flaky_failed = set()

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
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=90)
        except subprocess.TimeoutExpired:
            print(f"[skill-err {gid}] zsxq-cli 超时(>90s)，本星球本次跳过", file=sys.stderr)
            break
        except Exception as e:
            print(f"[skill-err {gid}] {e}", file=sys.stderr)
            break
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
    """通过 Cookie 直连官方 API（带分页 + 重试与限流规避）

    401/403 鉴权失败不重试（fail-fast，2026-09-16 维护改动）：
      旧逻辑对 401 也重试 3 次 —— 鉴权失败重试必然同样失败，每期白跑 12 次请求
      （4 星球 × 3 次），连续 4 期共 48 次无效请求。现改为遇 401/403 立即终止该星球，
      且同一轮抓取内只提示一次（auth_failed 去重），仅 5xx / 超时保留重试。

    HTTP 200 + succeeded=false 视为**限流抖动**（2026-09-17 维护改动）：
      实测该响应在连发请求时随机命中不同星球、退避后即恢复，与 Cookie 有效性无关。
      旧逻辑此处静默重试、耗尽后直接返回 0 条**且不打印任何日志** —— 报告会静默缺数据。
      现改为：每次抖动打 [cookie-flaky]、退避 3/6/9s（共 4 次）、
      耗尽仍无数据则记入 flaky_failed 并在收尾输出 COOKIE_FLAKY_FAILED=n。
    """
    if gid in auth_failed:
        print(f"[cookie-skip {gid}] 本轮已确认 Cookie 失效，跳过该星球（不重复提示）", file=sys.stderr)
        return []
    cookie = _cookie()
    all_topics, seen, end_time = [], set(), None
    while True:
        url = f"https://api.zsxq.com/v2/groups/{gid}/topics?scope=all&count={count}"
        if end_time:
            url += f"&end_time={end_time}"
        topics = None
        for attempt in range(4):
            req = urllib.request.Request(url, headers={
                "Cookie": cookie, "User-Agent": UA, "Accept": "application/json, text/plain, */*",
                "Origin": "https://wx.zsxq.com", "Referer": "https://wx.zsxq.com/",
            })
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    d = json.loads(resp.read().decode("utf-8"))
                if d.get("succeeded"):
                    topics = d.get("resp_data", {}).get("topics", [])
                    if attempt:
                        print(f"[cookie-retry-ok {gid}] 抖动 {attempt} 次后成功（非鉴权问题）",
                              file=sys.stderr)
                    break
                # HTTP 200 + succeeded=false：接口限流抖动（2026-09-17 实测，命中的星球随机、
                # 退避即恢复）。**旧逻辑此处静默重试，重试耗尽后直接返回 0 条且不打任何日志**
                # —— 报告会静默缺数据，是本文件最隐蔽的一类漏抓。
                print(f"[cookie-flaky {gid}] try{attempt}: HTTP 200 但 succeeded=false"
                      f"（限流抖动，非鉴权失败）→ 退避重试", file=sys.stderr)
                time.sleep(3 + attempt * 3)
            except urllib.error.HTTPError as e:
                # 401/403 = 鉴权失败，重试必然同样失败（Cookie 失效）→ 立即终止该星球，不浪费请求
                if e.code in (401, 403):
                    print(f"[cookie-auth {gid}] HTTP {e.code} 鉴权失败：Cookie 已失效，"
                          f"立即终止该星球抓取（不重试）。请更新 .workbuddy/zsxq_cookie.txt", file=sys.stderr)
                    auth_failed.add(gid)
                    break
                print(f"[cookie-err {gid}] try{attempt}: {e}", file=sys.stderr)
                time.sleep(3 + attempt * 3)
            except Exception as e:
                print(f"[cookie-err {gid}] try{attempt}: {e}", file=sys.stderr)
                time.sleep(3 + attempt * 3)
        if topics is None and gid not in auth_failed:
            # 重试耗尽仍无数据：必须显式报出来，否则该星球静默 0 条
            flaky_failed.add(gid)
            print(f"[cookie-flaky-fail {gid}] 退避重试 4 次仍无数据（限流抖动或接口异常，"
                  f"非鉴权失败）—— 本轮该星球将 0 条", file=sys.stderr)
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

def norm_topic(t, group_name, channel=''):
    """统一主题结构：兼容 Skill(brief扁平) 与 Cookie(嵌套) 两种格式

    channel：本条内容实际来自哪个抓取通道（'skill' / 'cookie'）。
    2026-09-18 新增 —— 归档脚本原先**写死**「抓取通道：zsxq-cli Skill」，
    一旦某星球改走 Cookie 通道，归档里的通道说明就是假的（而它是审计线索）。
    改为随数据落盘，归档按实际值渲染。
    """
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
            "create_time": ct, "images": images, "files": files, "channel": channel}

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

MAIN_SNAPSHOT = os.path.normpath(os.path.join(_HERE, 'zsxq_fetch_raw.json'))
# 覆盖主快照前滚一份备份（单份滚动）。与主快照同级同目录，
# 同样不进 git / 不进同步包（.gitignore 用 zsxq_fetch_raw*.json 通配，export_backup 用前缀排除）。
PREV_SNAPSHOT = os.path.normpath(os.path.join(_HERE, 'zsxq_fetch_raw.prev.json'))
# 本轮抓取的元信息（窗口档位 / 条数 / 是否降级 / 实际写入哪个文件）。
# 下游（gen_tj_archive.py）据此判断「手上这份快照是不是本轮抓取的结果」——
# 降级时主快照保持不变，若无此文件，归档脚本会把**上一轮的内容**当成今天的归档。
META_FILE = os.path.normpath(os.path.join(_HERE, 'zsxq_fetch_meta.json'))


def _window_label():
    """本轮窗口的档位说明（写进 meta，供归档如实标注，避免归档里写死/瞎猜档位）"""
    if os.environ.get("ZSXQ_WIN_START") and os.environ.get("ZSXQ_WIN_END"):
        return 'env 覆盖（手动指定窗口）'
    return {'noon': '午间 noon 窗口', 'afternoon': '下午 afternoon 窗口',
            'evening': '晚间 evening 窗口'}.get(_win_arg, '晨报 morning 窗口')


def _atomic_write_json(path, obj):
    """临时文件 → 回读断言 → 原子替换，避免中途异常留下半截 JSON。"""
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    with open(tmp, encoding='utf-8') as f:
        back = json.load(f)
    # 回读断言：落盘后读回的类型与规模必须一致（防序列化异常导致的静默截断）
    if type(back) is not type(obj) or len(back) != len(obj):
        os.remove(tmp)
        raise RuntimeError('快照回读断言失败：写入 %d 项，读回 %s'
                           % (len(obj), len(back) if isinstance(back, (list, dict))
                              else type(back).__name__))
    os.replace(tmp, path)


def save_snapshot(results, degraded):
    """写本轮抓取快照 + 元信息，返回 (写入路径, 是否已更新主快照)。

    为什么不能无脑覆盖主快照（2026-09-18 全链路审计 P0-2）
    -------------------------------------------------------
    主快照 `zsxq_fetch_raw.json` 既**不在 git 跟踪列表**（`git ls-files` 实测），
    又被 `export_backup.py` 的 `EXCLUDE_SUFFIX` 排除 —— 一旦被残缺结果覆盖，
    **本机没有任何副本可恢复**，当天的 DRAGON BALL模型 原文归档会跟着一起丢。
    而旧实现在 auth_failed 非空时照样覆盖主快照、照样打印 `SAVED=...`、照样退出 0，
    失败被完全伪装成成功（审计里最危险的一条）。

    现口径：
      - 正常（无降级原因）：先滚一份 .prev 备份，再原子替换主快照；
      - 降级（鉴权失败 / 限流抖动 / 窗口内 0 条）：**不碰主快照**，
        改写带时间戳的旁路文件；
      - 两种情况下都写 meta，明确记录本轮实际写到了哪个文件 —— 让下游能分辨
        「主快照是新的」还是「主快照是上一轮留下的」。
    """
    if degraded:
        stamp = datetime.now(CST).strftime('%Y%m%d_%H%M%S')
        out = os.path.normpath(os.path.join(_HERE, 'zsxq_fetch_raw_degraded_%s.json' % stamp))
        _atomic_write_json(out, results)
        is_main = False
    else:
        if os.path.exists(MAIN_SNAPSHOT):
            try:
                shutil.copyfile(MAIN_SNAPSHOT, PREV_SNAPSHOT)
            except OSError as e:
                print('[snapshot-warn] 旧快照备份失败（仍继续覆盖主快照）：%s' % e, file=sys.stderr)
        _atomic_write_json(MAIN_SNAPSHOT, results)
        out, is_main = MAIN_SNAPSHOT, True

    chans = {}
    for x in results:
        c = x.get('channel') or 'unknown'
        chans[c] = chans.get(c, 0) + 1
    _atomic_write_json(META_FILE, {
        'run_at': datetime.now(CST).strftime('%Y-%m-%dT%H:%M:%S%z'),
        'window': _window_label(),
        'win_start': WIN_START.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'win_end': WIN_END.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'total': len(results),
        'channels': chans,
        'degraded': degraded,
        'snapshot': os.path.basename(out),
        'updated_main': is_main,
    })
    return out, is_main


def main():
    results = []
    for gid, name in SKILL_GROUPS.items():
        topics = fetch_skill(gid)
        for t in topics:
            n = norm_topic(t, name, 'skill')
            if in_window(n["create_time"]):
                results.append(n)
        print(f"[skill] {name}: {len(topics)}条, 窗口内 {sum(1 for t in topics if in_window(t.get('create_time','')))}条", file=sys.stderr)
        time.sleep(3)
    for gid, name in COOKIE_GROUPS.items():
        topics = fetch_cookie(gid)
        for t in topics:
            n = norm_topic(t, name, 'cookie')
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

    # 降级原因（任一存在即不覆盖主快照）：鉴权失败 / 限流抖动 / 窗口内 0 条
    degraded = []
    if auth_failed:
        degraded.append('Cookie 鉴权失败 %d 个星球（%s）'
                        % (len(auth_failed), ', '.join(sorted(auth_failed))))
    if flaky_failed:
        degraded.append('限流抖动 %d 个星球（%s）'
                        % (len(flaky_failed), ', '.join(sorted(flaky_failed))))
    if not results:
        degraded.append('时间窗口内 0 条')

    saved, is_main = save_snapshot(results, degraded)

    n_img = sum(len(x["images"]) for x in results)
    n_file = sum(len(x["files"]) for x in results)
    print(f"TOTAL_WINDOW={len(results)}  IMAGES={n_img}  FILES={n_file}")
    if auth_failed:
        print(f"COOKIE_AUTH_FAILED={len(auth_failed)} (gid: {', '.join(sorted(auth_failed))}) "
              f"→ 需更新 .workbuddy/zsxq_cookie.txt")
    if flaky_failed:
        print(f"COOKIE_FLAKY_FAILED={len(flaky_failed)} "
              f"(gid: {', '.join(sorted(flaky_failed))}) → 限流抖动，非 Cookie 问题，重跑一次即可")
    if is_main:
        print(f"SAVED={saved}")
    else:
        print(f"SAVED_BYPASS={saved}")
        print("MAIN_SNAPSHOT_UNCHANGED=%s  ← 本轮降级（%s），未用残缺数据覆盖主快照" %
              (MAIN_SNAPSHOT, '；'.join(degraded)))
        print("[WARN] 主快照仍是上一次的完整内容，**不代表本轮结果**。"
              "若下游必须用本轮数据，请显式指定上面的 SAVED_BYPASS 文件。", file=sys.stderr)

    # 退出码：与 check_layout / check_integrity 统一口径（0=通过，1=ERROR，2=WARN）
    if auth_failed:
        return 1     # Cookie 失效 → 整个星球 0 条，本轮数据不可用
    if degraded:
        return 2     # 数据不完整或空窗口，需人工看一眼
    return 0


if __name__ == "__main__":
    sys.exit(main())
