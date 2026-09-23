# -*- coding: utf-8 -*-
"""全链路冒烟测试（常驻工具，2026-09-21 建）—— 一条命令把报告链路的每一环真跑一遍，看谁崩。

为什么需要它：
  项目已有 `run_tests.py`（跑单元/回归测试）与 `audit_pipeline.py`（静态结构审计），
  但**没有任何东西会真的把链路跑一遍**。「测试全绿 + 静态干净」与「链路能跑通」是两件事 ——
  改过某个脚本的 CLI、改过某个函数的返回结构，测试可能照样绿，而流水线要到下一档才发现崩。

设计原则：
  1. **默认零副作用**：链操作一律 `--dry-run`；不生成报告；不改两条链；
     需落盘的产物一律写到 `--tmp` 指定的**临时目录**。唯一会真写的是抓取阶段
     （这是它的本职工作，且自带 `.prev` 备份与「降级不覆盖主快照」守卫）。
  2. **前后 md5 快照**：跑之前对「受保护文件」取 md5，跑完再取一次，
     **任何非预期变化都判 FAIL** —— 这是「冒烟测试自己有没有搞坏东西」的唯一硬证据。
     受保护范围：两条链、`outputs/` 下所有交付物、`.workbuddy/*.md` 与 `*.py`。
     备份写成**单个 zip**（不是几百个散文件），回滚时按成员解出。
     ⚠️ 教训（2026-09-21）：备份若做成散文件，临时目录会膨胀到 700+ 个，
     清理时撞上环境的安全删除闸门，**冒烟在第一行就死掉**——闸门把测闸门的人也拦了。
  2b. 每次运行都新建独立临时目录（`_smoke_tmp/run_<时间戳>`），**从不删别人的目录**。
  3. **声明式阶段清单**：加/改一环只改 `build_stages()`，不新写脚本。
  4. **「期望退出码」写在声明里**：如 `gen_tj_archive` 空窗口退 2 是**设计**而非故障、
     `md_to_html` 无参退 1 是**守卫**而非崩溃。不写清楚就只能靠人肉记忆，等于没有判据。
  5. 串行执行（项目约定：并发 >2 会触发沙箱拦截）。`--only` 可只跑子集。

用法：
    $PY .workbuddy/smoke_pipeline.py                 # 全量
    $PY .workbuddy/smoke_pipeline.py --no-net        # 跳过联网阶段（离线可跑）
    $PY .workbuddy/smoke_pipeline.py --no-slow       # 跳过慢阶段（引擎/测试）
    $PY .workbuddy/smoke_pipeline.py --only chain    # 只跑名字含该子串的阶段
    $PY .workbuddy/smoke_pipeline.py --keep-tmp      # 保留临时目录（排查用）

退出码：0 全部通过 · 1 有 FAIL · 2 仅 WARN
"""
import argparse
import fnmatch
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # silent-ok: 终端编码收口尽力而为，失败不影响结论
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
TIMEOUT = 480          # 单个阶段墙钟上限（秒）
DEFAULT_TMP = os.path.join(HERE, '_smoke_tmp')
CLEANUP_MAX_FILES = 40  # 临时目录超过这么多文件就不自动删（见 _cleanup 的说明）

# ── 受保护：冒烟**不允许**被改动。改了就是最严重的 BUG（说明有脚本在乱写）──
PROTECTED_GLOBS = [
    '.workbuddy/forecast_chain.json',
    '.workbuddy/consensus_chain.json',
    'outputs/*.md',
    'outputs/*.html',
    'outputs/*.svg',
    '.workbuddy/*.md',
    '.workbuddy/*.py',
]
# ── 允许变化，但如实汇报（抓取/扫描类阶段的正常产出）──
# 注意：这里**必须与 PROTECTED_GLOBS 完全不相交**，否则该文件永远同时命中两边 →
# 每次冒烟都报「受保护文件被改」→ 永久红灯 → 闸门被无视（2026-09-21 踩过：
#   outputs/DRAGON_BALL_原始记录_*.md 同时在两边，制造了一次假 FAIL）。
# 现在归档阶段改走 --out 写到临时目录，该文件回归「纯受保护」，被改一定是真问题。
MAY_CHANGE_GLOBS = [
    '.workbuddy/zsxq_fetch_raw*.json',
    '.workbuddy/zsxq_fetch_meta.json',
    '.workbuddy/*_bias_*.json',
    '.workbuddy/backtest_data/*.json',
    '.workbuddy/_ohlc_cache/*.json',
]
# 新增文件允许出现的目录（阶段自建产物）
NEW_FILE_SCOPE = ['outputs', '.workbuddy']
IGNORE_NEW = ('_smoke_tmp', '__pycache__')


def _cleanup(tmp):
    """清理本次运行的临时目录。

    两个约束（2026-09-21 踩过）：
      1) **不预先 rmtree 旧目录**：上一次运行的 `_smoke_tmp` 里有 357 个备份文件，
         一开始就删它会直接撞上环境的安全删除闸门（一次删 716 个 > 阈值 50），
         整个冒烟在第一行就死掉。所以现在每次运行都新建独立目录，从不删别人的。
      2) **删成功与否都要核实**：`rmtree(ignore_errors=True)` 会把删除失败吞掉 ——
         实测环境闸门会按 `backup_zip` 的**成员数**计数（360 成员 → 报 count=367），
         于是目录根本删不掉，而旧写法连一个字都不说。现在删完必须回查，
         没删掉就如实报出来（留着垃圾可以，瞒着不行）。
    """
    if not os.path.isdir(tmp):
        return True
    loose = sum(len(fs) for _, _, fs in os.walk(tmp))
    members = 0
    for root, _, fs in os.walk(tmp):
        for f in fs:
            if f.endswith('.zip'):
                try:
                    with zipfile.ZipFile(os.path.join(root, f)) as z:
                        members += len(z.namelist())
                except Exception:  # silent-ok: zip 成员数读不到按 0 计，只影响临时目录阈值提示（偏保守）
                    pass
    total = loose + members
    if total > CLEANUP_MAX_FILES:
        print('[WARN] 临时目录 %d 个文件（含备份 zip 成员 %d）超过阈值 %d，**不自动删除**：%s'
              % (loose, members, CLEANUP_MAX_FILES, tmp))
        return False
    shutil.rmtree(tmp, ignore_errors=True)
    if os.path.isdir(tmp):
        print('[WARN] 临时目录**删除失败**（环境删除保护拦截），请人工处理：%s'
              % tmp)
        return False
    return True


def md5(p):
    m = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            m.update(b)
    return m.hexdigest()


def _match(rel, globs):
    return any(fnmatch.fnmatch(rel.replace('\\', '/'), g) for g in globs)


def collect():
    """{相对 ROOT 的 posix 路径: md5}。范围固定为 PROTECTED_GLOBS。"""
    out = {}
    for g in PROTECTED_GLOBS:
        for p in glob.glob(os.path.join(ROOT, g)):
            if os.path.isfile(p):
                rel = os.path.relpath(p, ROOT).replace('\\', '/')
                out[rel] = md5(p)
    return out


def collect_may():
    """MAY_CHANGE 范围跑前的 md5。**只记哈希、不备份** —— 这些文件本来就允许变。"""
    out = {}
    for g in MAY_CHANGE_GLOBS:
        for p in glob.glob(os.path.join(ROOT, g)):
            if os.path.isfile(p):
                out[os.path.relpath(p, ROOT).replace('\\', '/')] = md5(p)
    return out


def list_scope():
    """枚举 NEW_FILE_SCOPE 下的现有文件集合（用于检测新增文件）。"""
    fs = set()
    for s in NEW_FILE_SCOPE:
        d = os.path.join(ROOT, s)
        for p in glob.glob(os.path.join(d, '*')):
            if any(k in p for k in IGNORE_NEW):
                continue
            if os.path.isdir(p):
                fs.add(os.path.relpath(p, ROOT).replace('\\', '/') + '/')
            else:
                fs.add(os.path.relpath(p, ROOT).replace('\\', '/'))
    return fs


def newest_by_mtime(pattern, base=None):
    base = base or ROOT
    fs = glob.glob(os.path.join(base, pattern))
    return max(fs, key=os.path.getmtime) if fs else None


# 注意：不要用 % 格式化来拼这段代码 —— 代码体里本来就有 %s/%d，
# 一旦某个占位符忘了转义，就会变成「把路径喂给 %d」的 TypeError（2026-09-21 踩过）。
# 用 repr() + 唯一标记替换，彻底绕开转义问题。
COMPILE_SNIPPET = r'''
import glob, os, py_compile, sys, tempfile
HERE = @@HERE@@
bad = []
cf = os.path.join(tempfile.gettempdir(), '_wb_smoke_compile.pyc')
files = sorted(glob.glob(os.path.join(HERE, '*.py')))
for f in files:
    try:
        py_compile.compile(f, doraise=True, cfile=cf)
    except Exception as e:
        bad.append('%s: %s' % (os.path.basename(f), e))
print('compiled=%d bad=%d' % (len(files), len(bad)))
for b in bad:
    print('  ' + b)
sys.exit(1 if bad else 0)
'''.replace('@@HERE@@', repr(HERE))


GUARD_PROBE = 'guard_probe.md'


def _seed_guard_probe(tmp):
    """给 C4 造一个「人工精修版」哨兵：不带生成戳的归档文件。

    内容刻意模仿人工精修版（中文类型、精确字节 + download 次数），且**只有 1 条** ——
    这样「缩水守卫」（旧条数 > 新条数才拦）一定不触发，
    C4 拿到 rc=2 就唯一地证明是「人工精修守卫」在起作用，而不是别的守卫生效。
    """
    p = os.path.join(tmp, GUARD_PROBE)
    with open(p, 'w', encoding='utf-8') as f:
        f.write('# DRAGON BALL模型 原始记录归档 · 哨兵\n\n'
                '> 人工精修版哨兵 · 故意不含生成器标记\n\n'
                '## [1] 2026-09-20T21:40:29.897+0800 · 人工挑选的核心定调句…（核心定调）\n\n'
                '- **类型**: talk（问答）\n'
                '- **附件**（1）: 周度思考 2026.9.20.pdf（size 2,037,146 / download 791）\n\n'
                '---\n')
    return p


def build_stages(tmp):
    """返回 (stages, meta)。stage = (名称, 分类, argv, 期望rc集合, 联网, 慢)"""
    rep_abs = newest_by_mtime('outputs/作战报告_*.md')
    rep = os.path.relpath(rep_abs, ROOT) if rep_abs else None
    pay_abs = newest_by_mtime('payload_*.json', HERE)
    pay = pay_abs

    # 只替换 {PY}/{WB}/{ROOT}/{TMP} 这四个已知占位符，不用 str.format ——
    # 因为 A1 那一环的参数是**一整段 Python 代码**，代码里出现花括号就会把 .format 炸掉。
    _ph = {'PY': PY, 'WB': HERE, 'ROOT': ROOT, 'TMP': tmp}
    sub = lambda a: [re.sub(r'\{(PY|WB|ROOT|TMP)\}', lambda m: _ph[m.group(1)], x) for x in a]
    s = []
    add = lambda *x: s.append((x[0], x[1], sub(x[2]), x[3], x[4], x[5]))

    # ---- A. 预检 ----
    add('A1 根脚本语法编译', 'preflight', ['{PY}', '-c', COMPILE_SNIPPET], (0,), False, False)
    add('A2 静态结构审计 audit_pipeline', 'preflight', ['{PY}', '{WB}/audit_pipeline.py'], (0, 2), False, False)
    add('A3 聚合回归测试 run_tests', 'preflight', ['{PY}', '{WB}/run_tests.py'], (0,), False, True)

    # ---- B. 数据层 ----
    add('B1 指数代码注册表 market_codes', 'data', ['{PY}', '{WB}/market_codes.py'], (0,), False, False)
    add('B2 日线 OHLC（隔离槽位 smoke）', 'data',
        ['{PY}', '{WB}/get_daily_ohlc.py', '000001', '2', '--slot', 'smoke'], (0,), True, False)
    add('B3 技术指标 calc_tech', 'data',
        ['{PY}', '{WB}/calc_tech.py', '--code', '000001', '--out', '{TMP}/tech.json', '--quiet'], (0,), True, False)
    add('B4 多周期技术位 calc_tech_multi', 'data',
        ['{PY}', '{WB}/calc_tech_multi.py', '--code', 'sh000001', '--out', '{TMP}/tech_multi.json', '--quiet'],
        (0,), True, True)

    # ---- C. 抓取层 ----
    add('C1 星球抓取 afternoon 窗口', 'fetch',
        ['{PY}', '{WB}/fetch_zsxq.py', '--window', 'afternoon'], (0, 2), True, True)
    add('C2 抓取摘要 digest_zsxq', 'fetch',
        ['{PY}', '{WB}/digest_zsxq.py', '--out', '{TMP}/digest.txt', '--limit', '5'], (0,), False, False)
    # C3 走 --out 写到临时目录：既验证归档生成能跑，又完全不碰当天交付物。
    add('C3 T&J 原文归档（写临时路径）', 'fetch',
        ['{PY}', '{WB}/gen_tj_archive.py', '--out', '{TMP}/tj_archive.md'], (0, 2), False, False)
    # C4 人工精修守卫：哨兵文件**故意不带生成戳**，脚本必须拒绝覆盖并退 2。
    #    这是 2026-09-21 那次 P0（机械版静默覆盖人工精修版）的回归闸门。
    _seed_guard_probe(tmp)
    add('C4 归档精修守卫（必须拒绝覆盖）', 'fetch',
        ['{PY}', '{WB}/gen_tj_archive.py', '--out', '{TMP}/guard_probe.md'], (2,), False, False)

    # ---- D. 引擎层 ----
    add('D1 一键预判数据包 forecast_analyze', 'engine',
        ['{PY}', '{WB}/forecast_analyze.py', '000001'], (0,), True, True)
    add('D2 四周期联动 analyze_000001_multi', 'engine',
        ['{PY}', '{WB}/analyze_000001_multi.py'], (0,), True, True)
    add('D3 申万行业缠论 run_sw_chansignal', 'engine',
        ['{PY}', '{WB}/run_sw_chansignal.py', '--code', '801080'], (0,), True, True)
    add('D4 引擎有效性复盘 engine_effectiveness', 'engine',
        ['{PY}', '{WB}/engine_effectiveness.py'], (0,), False, False)

    # ---- E. 行业层 ----
    add('E1 申万实时行情 scan_sw_realtime', 'industry',
        ['{PY}', '{WB}/scan_sw_realtime.py'], (0,), True, True)
    add('E2 同花顺行业方向分 scan_ths', 'industry',
        ['{PY}', '{WB}/scan_ths.py'], (0, 2), True, True)
    add('E3 行业强弱榜 industry_rank', 'industry',
        ['{PY}', '{WB}/industry_rank.py'], (0,), False, False)

    # ---- F. 链层 ----
    add('F1 链状态自检 chainlib', 'chain', ['{PY}', '{WB}/chainlib.py'], (0,), False, False)
    add('F2 偏差重算 chain_apply --bias-only', 'chain',
        ['{PY}', '{WB}/chain_apply.py', '--bias-only'], (0, 2), False, False)
    if pay:
        add('F3 链操作幂等预演 chain_apply --dry-run', 'chain',
            ['{PY}', '{WB}/chain_apply.py', '--payload', pay, '--dry-run'], (0, 1, 2), False, False)

    # ---- G. 校验层 ----
    if rep:
        add('G1 版面体检 check_layout（最新报告）', 'validate',
            ['{PY}', '{WB}/check_layout.py', rep], (0, 1, 2), False, False)
    add('G2 数据完整性 check_integrity', 'validate',
        ['{PY}', '{WB}/check_integrity.py'], (0, 1, 2), False, False)
    add('G3 显示名守卫 check_display_name', 'validate',
        ['{PY}', '{WB}/check_display_name.py', '--today', time.strftime('%Y-%m-%d')], (0, 1), False, False)
    # rc=1 = audit_coverage 判出「有真盲区」（源码 `return 1 if blind else 0`），
    # 属**信号**而非故障，所以 1 也是预期值。（首轮冒烟漏了它 → 一次假 FAIL。）
    add('G4 行业覆盖审计 audit_coverage', 'validate',
        ['{PY}', '{WB}/audit_coverage.py'], (0, 1, 2), False, False)

    # ---- H. 输出层 ----
    add('H1 走势图 SVG（重绘到临时路径）', 'output',
        ['{PY}', '{WB}/gen_forecast_svg.py', '--out', '{TMP}/forecast.svg'], (0,), False, False)
    add('H2 md_to_html 无参守卫', 'output',
        ['{PY}', '{WB}/md_to_html_report.py'], (1,), False, False)
    add('H3 md_to_html 不存在文件守卫', 'output',
        ['{PY}', '{WB}/md_to_html_report.py', '{TMP}/nosuch.md'], (1,), False, False)
    if rep:
        add('H4 md_to_html 正常路径', 'output',
            ['{PY}', '{WB}/md_to_html_report.py', rep], (0,), False, False)
    add('H5 匿名化 anonymize_report', 'output',
        ['{PY}', '{WB}/anonymize_report.py'], (0, 1, 2), False, False)

    meta = {'report': rep, 'payload': pay}
    return s, meta


def main(argv=None):
    ap = argparse.ArgumentParser(description='全链路冒烟测试（默认零副作用）')
    ap.add_argument('--no-net', action='store_true', help='跳过联网阶段')
    ap.add_argument('--no-slow', action='store_true', help='跳过慢阶段（回归测试/引擎/扫描）')
    ap.add_argument('--only', default=None, metavar='SUBSTR', help='只跑名字含该子串的阶段')
    ap.add_argument('--tmp', default=DEFAULT_TMP, help='临时目录（默认 .workbuddy/_smoke_tmp）')
    ap.add_argument('--out', default=None, help='报告落盘路径（默认系统临时目录）')
    ap.add_argument('--keep-tmp', action='store_true', help='保留临时目录')
    a = ap.parse_args(argv)

    tmp = os.path.join(a.tmp, 'run_%s' % time.strftime('%Y%m%d_%H%M%S'))
    os.makedirs(tmp, exist_ok=True)

    stages, meta = build_stages(tmp)
    if a.only:
        stages = [x for x in stages if a.only in x[0] or a.only in x[1]]
    if a.no_net:
        stages = [x for x in stages if not x[4]]
    if a.no_slow:
        stages = [x for x in stages if not x[5]]
    if not stages:
        sys.stderr.write('[FAIL] 没有匹配的阶段\n')
        return 1

    L = []
    W = L.append
    W('=' * 78)
    W('全链路冒烟测试 · %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
    W('临时目录 %s' % tmp)
    W('最新报告 %s' % (meta['report'] or '(无)'))
    W('最新 payload %s' % (os.path.basename(meta['payload']) if meta['payload'] else '(无)'))
    W('阶段 %d 个%s' % (len(stages), '（已过滤）' if a.only or a.no_net or a.no_slow else ''))
    W('=' * 78)

    # ── 跑前快照 ──
    prot_before = collect()
    may_before = collect_may()
    files_before = list_scope()
    # 备份收进**单个 zip**，不做几百个散文件拷贝：散文件会让临时目录膨胀到 700+ 个，
    # 清理时直接撞环境的安全删除闸门（2026-09-21 实测：冒烟在第一行就被拦死）。
    BKZIP = os.path.join(tmp, 'protected_backup.zip')
    with zipfile.ZipFile(BKZIP, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel in prot_before:
            z.write(os.path.join(ROOT, rel), rel)
    W('受保护文件 %d 个已取快照（备份为单个 zip，可回滚）' % len(prot_before))

    # ── 执行 ──
    results = []
    for name, cat, cmd, expect, net, slow in stages:
        t0 = time.time()
        try:
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=TIMEOUT,
                               env=dict(os.environ, PYTHONIOENCODING='utf-8'))
            rc, out, err, to = r.returncode, r.stdout or '', r.stderr or '', False
        except subprocess.TimeoutExpired as e:
            rc, out, err, to = 124, (e.stdout or '') if isinstance(e.stdout, str) else '', '', True
        dt = time.time() - t0
        ok = rc in expect
        results.append({'name': name, 'cat': cat, 'rc': rc, 'expect': expect, 'ok': ok,
                        'to': to, 'dt': dt, 'out': out, 'err': err})
        W('  [%s] %-42s rc=%-4s %6.1fs' % (
            'OK  ' if ok else ('TIME' if to else 'FAIL'), name, rc, dt))

    # ── 跑后核对：受保护文件 ──
    # 口径：MAY_CHANGE 优先。命中 MAY_CHANGE 的文件不参与「受保护」判定，
    # 否则一个文件同时命中两边就会永久假 FAIL。
    may_hit = lambda rel: _match(rel, MAY_CHANGE_GLOBS)
    prot_after = collect()
    changed = sorted(r for r in prot_before
                     if not may_hit(r) and prot_before[r] != prot_after.get(r))
    missing = sorted(r for r in prot_before if not may_hit(r) and r not in prot_after)
    added_prot = sorted(r for r in prot_after
                        if r not in prot_before and not may_hit(r))

    # ── 跑后核对：允许变化 / 新增文件 ──
    files_after = list_scope()
    # new_files 要排除 MAY_CHANGE 命中项，否则同一个文件会被**双重报告**：
    # 既进「按设计新增」的 INFO，又进「需要人工归置」的 WARN。
    # （2026-09-21 实测：.workbuddy/_bias_test_tmp.json 同时出现在两处，制造了一次假 WARN。）
    new_files = sorted(f for f in (files_after - files_before)
                       if not _match(f, MAY_CHANGE_GLOBS))
    may_changed, may_new = [], []
    for rel, h in sorted(may_before.items()):
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            may_changed.append(rel + '（被删除）')
        elif md5(p) != h:
            may_changed.append(rel)
    for g in MAY_CHANGE_GLOBS:
        for p in glob.glob(os.path.join(ROOT, g)):
            rel = os.path.relpath(p, ROOT).replace('\\', '/')
            if rel not in may_before:
                may_new.append(rel)

    W('')
    W('-' * 78)
    W('① 阶段结果')
    fail = [r for r in results if not r['ok']]
    if fail:
        for r in fail:
            W('  [FAIL] %s  rc=%s（期望 %s）' % (r['name'], r['rc'], '/'.join(map(str, r['expect']))))
            tail = [x for x in (r['out'] + r['err']).splitlines() if x.strip()][-12:]
            for ln in tail:
                W('         | %s' % ln[:150])
    else:
        W('  全部 %d 个阶段退出码符合预期' % len(results))
    W('')
    W('② 副作用核对（冒烟不该改动交付物与链）')
    if changed:
        W('  [FAIL] 受保护文件被改动 %d 个 —— 这是 BUG，已回滚：' % len(changed))
        for rel in changed:
            try:
                with zipfile.ZipFile(BKZIP) as z:
                    data = z.read(rel)
                with open(os.path.join(ROOT, rel), 'wb') as o:
                    o.write(data)
                W('         %s（已回滚）' % rel)
            except Exception as e:
                W('         %s（**回滚失败**：%s）' % (rel, e))
    if missing:
        W('  [FAIL] 受保护文件消失 %d 个：%s' % (len(missing), ', '.join(missing)))
    if added_prot:
        W('  [WARN] 受保护范围新增文件 %d 个：%s' % (len(added_prot), ', '.join(added_prot)))
    if not (changed or missing or added_prot):
        W('  受保护文件 %d 个全部未变（两条链 + outputs 交付物 + 文档 + 脚本）' % len(prot_before))
    if may_changed:
        W('  [INFO] 以下文件按设计发生变化（抓取/扫描阶段的正常产出）：')
        for rel in may_changed:
            W('         %s' % rel)
    if may_new:
        W('  [INFO] 按设计新增的抓取/缓存产物 %d 个：' % len(may_new))
        for rel in may_new:
            W('         %s' % rel)
    if new_files:
        W('  [WARN] 新增文件 %d 个（冒烟产生的旁路产物，需要人工归置）：' % len(new_files))
        for f in new_files:
            W('         %s' % f)

    rc = 1 if (fail or changed or missing) else (2 if (added_prot or new_files) else 0)
    W('')
    W('=' * 78)
    W('汇总：阶段 %d · 通过 %d · 失败 %d · 受保护文件被改 %d · 新增文件 %d'
      % (len(results), len(results) - len(fail), len(fail), len(changed), len(new_files)))
    W('RESULT: %s' % ('ALL PASS' if rc == 0 else ('WARN' if rc == 2 else 'FAIL')))
    W('=' * 78)

    blob = '\n'.join(L)
    print(blob)
    outp = a.out or os.path.join(os.environ.get('TEMP', HERE),
                                 'wb_smoke_%s.txt' % time.strftime('%Y%m%d_%H%M%S'))
    try:
        with open(outp, 'w', encoding='utf-8') as f:
            f.write(blob)
        print('\n[报告已写出] %s' % outp)
    except Exception as e:
        print('\n[WARN] 报告写盘失败：%s' % e)

    if not a.keep_tmp:
        _cleanup(tmp)
    return rc


if __name__ == '__main__':
    sys.exit(main())
