# -*- coding: utf-8 -*-
"""链路审计（常驻工具）：一次性回答「现在整个链路有没有 BUG / 重复 / 文档腐烂 / 退出码缺失」。

用法：
    $PY .workbuddy/audit_pipeline.py                 # 全量扫描，打印摘要
    $PY .workbuddy/audit_pipeline.py --full          # 逐条明细（默认只打摘要 + Top 若干）
    $PY .workbuddy/audit_pipeline.py --out 文件.txt   # 结果同时写 UTF-8 文件（终端中文乱码时用）

退出码：0 无 P0 级问题 / 1 有 P0 级问题（失败路径静默）/ 2 仅 P1/P2
  P0 判定口径：会打印「失败/❌/[FAIL]」但**没有失败退出码**的脚本 —— 属「失败被当成成功」，
  是本项目历史上最贵的一类 BUG（见 memory 2026-09-18 审计）。

检查七项：
  1. 退出码语义：有入口但无 sys.exit(非零) 的脚本，并标记其中「代码区里输出/抛出失败字样」
     的高危子集（注释、docstring、表格渲染符号 ❌ 一律不计 —— 假阳性会淹没真高危）
  2. 静默失败反模式：危险默认值/静默回退、吞异常 pass、裸 except
  3. 硬编码：绝对路径（含用户名）、写死的具体日期
  4. 文档对账：文档引用的 *.py 是否存在（区分「已归档」与「真不存在」）、脚本是否被文档遗漏
  5. 重复：跨脚本近似重复对、跨脚本同名函数、脚本被多份文档重复描述
  6. 运行件：.workbuddy 下非 .py/.md 文件是否被 gitignore 覆盖（用 git check-ignore 实测）
  7. 校验器体检：check_*/test_* 的退出码取值分布

设计约束：只读、不改任何文件；结果可复现（同一输入两次运行一致）。
"""
import argparse
import io
import os
import re
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCHIVE = os.path.join(HERE, 'archive')

SKIP = {'audit_pipeline.py'}
FAIL_WORDS = re.compile(r'\[FAIL\]|❌|错误|失败|不存在|无法')
# 「输出」上下文：失败词必须出现在**输出语句**里才算「打印了失败却继续跑」。
# 必要性有两层：
#   ① 表格渲染符号（dir_v = '❌相反'）、编码注释、docstring 里的「失败」二字
#      都曾让 4 个自检型脚本被误判为高危 —— 假阳性会让真高危被噪声淹没（见 MEMORY 闸门体检）。
#   ② 故意不收录 `raise`：抛异常本身就会带非零退出，不属于「失败被当成成功」。
OUT_CTX = re.compile(r'\bprint\s*\(|sys\.stderr|\.write\s*\('
                     r'|\.(?:error|critical|warning)\s*\(')


def scripts():
    return sorted(f for f in os.listdir(HERE)
                  if f.endswith('.py') and f not in SKIP and not f.startswith('_'))


def read(f):
    return io.open(os.path.join(HERE, f), encoding='utf-8').read()


# ---------------- 1. 退出码语义 ----------------
def scan_exit_codes(src):
    no_code, risky = [], []
    for f, s in src.items():
        if 'if __name__' not in s and 'def main' not in s:
            continue
        # 只看代码区（剔除注释与 docstring）—— 本项目习惯把「已修复」说明写在 docstring 里，
        # 裸扫会把修好之后的说明当成命中，属自造噪声。
        lines = code_only_lines(s)
        code = '\n'.join(ln for _, ln in lines)
        has_nz = bool(re.search(r'sys\.exit\(\s*[^0\s)]', code)
                      or re.search(r'return\s+[1-9]\b', code)
                      or re.search(r'raise\s+SystemExit', code))
        if has_nz:
            continue
        no_code.append(f)
        # 高危：代码区里「输出/抛出」了失败字样，却仍无条件退出 0
        for _, ln in lines:
            if FAIL_WORDS.search(ln) and OUT_CTX.search(ln):
                risky.append(f)
                break
    return no_code, risky


# ---------------- 2. 静默失败反模式 ----------------
def scan_silent(src):
    hits = []
    for f, s in src.items():
        for m in re.finditer(r'except[^\n:]*:\s*\n\s*pass\b', s):
            hits.append((f, s[:m.start()].count('\n') + 1, 'except → pass（吞异常）'))
        for m in re.finditer(r"^\s*except\s*:", s, re.M):
            hits.append((f, s[:m.start()].count('\n') + 1, '裸 except'))
        for m in re.finditer(r"""\bor\s+['"]20\d\d[-/][0-9]{2}['"]""", s):
            hits.append((f, s[:m.start()].count('\n') + 1, '疑似静默回退到写死日期'))
    return hits


# ---------------- 3. 硬编码 ----------------
def code_only_lines(s):
    """返回 [(行号, 仅在「代码区」的行内容)]，剔除注释与三引号字符串。

    必要性：本项目大量「已修复」的记录写在 docstring 里（如「- 删掉写死的绝对路径」），
    若不剔除，扫描器会把**修好之后留下的说明**当成命中 —— 那就是自造噪声，
    而噪声会让闸门被无视（见 MEMORY「校验器体检」）。
    """
    res, tri = [], None
    for i, ln in enumerate(s.split('\n'), 1):
        if tri:
            if tri in ln:
                ln = ln.split(tri, 1)[1]
                tri = None
            else:
                continue
        ln = ln.split('#')[0]
        for q in ('"""', "'''"):
            while True:
                idx = ln.find(q)
                if idx == -1:
                    break
                rest = ln[idx + 3:]
                if q in rest:
                    ln = ln[:idx] + rest.split(q, 1)[1]
                else:
                    tri = q
                    ln = ln[:idx]
                    break
        res.append((i, ln))
    return res


def scan_hardcode(src):
    hits = []
    for f, s in src.items():
        for ln, code in code_only_lines(s):
            for m in re.finditer(r'[Cc]:[\\/]{1,2}Users[\\/]{1,2}(\w+)|/c/Users/(\w+)', code):
                user = m.group(1) or m.group(2)
                hits.append((f, ln, '硬编码绝对路径（用户名 %s）' % user))
    return hits


# ---------------- 4. 文档对账 ----------------
DOCS = ['脚本地图.md', '报告生成流程.md', 'README_预判系统.md',
        '报告逻辑排版完整性规范_v2.md', '预判规则_v5.md']
PLACEHOLDER_OK = re.compile(r'^(\w*MMDD|\w*xxx|xxx)\.py$')   # 命名约定占位符


def scan_docs(src):
    docs = {d: io.open(os.path.join(HERE, d), encoding='utf-8').read()
            for d in DOCS if os.path.exists(os.path.join(HERE, d))}
    mentions, stale, missing, undocumented = {}, [], [], []
    for d, t in docs.items():
        for f in src:
            if f in t:
                mentions.setdefault(f, []).append(d)
        for m in re.finditer(r'\b([A-Za-z_][A-Za-z0-9_]*\.py)\b', t):
            fn = m.group(1)
            # 存在性以**磁盘为准**：`src` 里排除了 SKIP（本文件自身），
            # 若只判 `fn in src`，文档里每提一次 `audit_pipeline.py` 都会被算成「真不存在」——
            # 纯噪声，会把真正的文档腐烂淹掉。
            if (fn in src or os.path.exists(os.path.join(HERE, fn))
                    or PLACEHOLDER_OK.match(fn)):
                continue
            key = (fn, d)
            if key in missing:
                continue
            # 是否已在 archive 里
            arch = None
            for root, _dirs, files in os.walk(ARCHIVE):
                if fn in files:
                    arch = os.path.relpath(os.path.join(root, fn), ROOT)
                    break
            (stale if arch else missing).append((fn, d, arch))
    undocumented = [f for f in src if f not in mentions]
    return docs, mentions, stale, missing, undocumented


# ---------------- 5. 重复 ----------------
def scan_dups(src):
    import difflib
    def norm(s):
        s = re.sub(r'#.*', '', s)
        s = re.sub(r'"""(?:.|\n)*?"""', '', s)
        return re.sub(r'\s+', ' ', s).strip()

    big = {f: norm(s) for f, s in src.items() if len(s) > 2500}
    pairs, names = [], sorted(big)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            q = difflib.SequenceMatcher(None, big[a], big[b]).quick_ratio()
            if q > 0.55:
                r = difflib.SequenceMatcher(None, big[a], big[b]).ratio()
                if r > 0.42:
                    pairs.append((round(r, 2), a, b))
    fmap = {}
    for f, s in src.items():
        for m in re.finditer(r'^def\s+([a-zA-Z_]\w*)\s*\(', s, re.M):
            fmap.setdefault(m.group(1), set()).add(f)
    shared = {k: sorted(v) for k, v in fmap.items()
              if len(v) >= 2 and not k.startswith('_') and k != 'main'}
    return sorted(pairs, reverse=True), shared


# ---------------- 6. 运行件 gitignore ----------------
def scan_runtime():
    """用 git check-ignore 实测哪些运行件其实会被提交/同步。

    ⚠️ 2026-09-18 踩坑：本机 Git Bash 的 shim 环境下 `git check-ignore --stdin`
    **读不到标准输入**（rc=1、stdout 为空），会导致「全部运行件都未被忽略」的假警报。
    改为把路径作为**命令行参数**传入（实测可用）。rc 语义：0=有被忽略项，1=一个都没忽略。
    非 0/1 视为无法判定，如实上报而不是硬报问题。
    """
    other = sorted(f for f in os.listdir(HERE)
                   if os.path.isfile(os.path.join(HERE, f))
                   and not f.endswith(('.py', '.md')))
    if not other:
        return [], [], ''
    rels = ['.workbuddy/' + f for f in other]
    try:
        r = subprocess.run(['git', 'check-ignore'] + rels, cwd=ROOT,
                           capture_output=True, text=True, encoding='utf-8')
    except Exception as e:
        return other, [], 'git check-ignore 调用失败：%r' % (e,)
    if r.returncode not in (0, 1):
        return other, [], 'git check-ignore 返回 rc=%d，无法判定（stderr: %s）' \
                          % (r.returncode, (r.stderr or '')[:120])
    ign = set(x.strip() for x in (r.stdout or '').split('\n') if x.strip())
    return other, [x for x in rels if x not in ign], ''


# ---------------- 7. 校验器体检 ----------------
def scan_validators(src):
    rows = []
    for f, s in src.items():
        if not (f.startswith('check_') or f.startswith('test_')):
            continue
        rows.append((f,
                     sorted(set(re.findall(r'sys\.exit\(\s*([^)\n]{0,26})', s))),
                     sorted(set(re.findall(r'return\s+([0-9])\b', s)))))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description='链路审计（只读）')
    ap.add_argument('--full', action='store_true', help='打印逐条明细')
    ap.add_argument('--out', default=None, metavar='PATH', help='同时写 UTF-8 文件')
    a = ap.parse_args(argv)

    src = {f: read(f) for f in scripts()}
    L = []

    def W(s=''):
        L.append(s)

    W('=' * 72)
    W('链路审计 · %s' % __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M'))
    W('脚本 %d 个（不含 _ 前缀临时件）' % len(src))
    W('=' * 72)

    no_code, risky = scan_exit_codes(src)
    silent = scan_silent(src)
    hard = scan_hardcode(src)
    docs, mentions, stale, missing, undoc = scan_docs(src)
    pairs, shared = scan_dups(src)
    other, not_ignored, rt_err = scan_runtime()
    vals = scan_validators(src)

    W('\n【1】退出码语义')
    W('  有入口但无失败退出码：%d 个' % len(no_code))
    W('  ⚠️ 高危子集（会打印失败字样却退出 0）：%d 个' % len(risky))
    for f in risky:
        W('      %s' % f)
    if a.full:
        for f in no_code:
            W('      · %s' % f)

    W('\n【2】静默失败反模式：%d 处' % len(silent))
    shown = silent if a.full else silent[:8]
    for f, ln, why in shown:
        W('      %-34s :%-4s %s' % (f, ln, why))
    if len(silent) > len(shown):
        W('      … 其余 %d 处（--full 展开）' % (len(silent) - len(shown)))

    W('\n【3】硬编码：绝对路径 %d 处' % len(hard))
    for f, ln, why in (hard if a.full else hard[:8]):
        W('      %-34s :%-4s %s' % (f, ln, why))

    W('\n【4】文档对账（%d 份）' % len(docs))
    W('  文档引用已归档脚本：%d 处  ← 文档腐烂' % len(stale))
    for fn, d, arch in (stale if a.full else stale[:10]):
        W('      %-30s ← %-22s (在 %s)' % (fn, d, arch))
    W('  文档引用真不存在：%d 处' % len(missing))
    for fn, d, _ in (missing if a.full else missing[:8]):
        W('      %-30s ← %s' % (fn, d))
    W('  未被任何文档提及的脚本：%d 个' % len(undoc))
    for f in (undoc if a.full else undoc[:12]):
        W('      · %s' % f)

    W('\n【5】重复')
    W('  跨脚本近似重复：%d 对' % len(pairs))
    for r, x, y in (pairs if a.full else pairs[:6]):
        W('      %.2f  %-34s ~ %s' % (r, x, y))
    W('  跨脚本同名函数（非 _ 前缀、非 main）：%d 个' % len(shared))
    for k in sorted(shared, key=lambda x: -len(shared[x]))[:10]:
        W('      %-24s %d 个脚本：%s' % (k, len(shared[k]), ', '.join(shared[k][:4])))
    multi = {f: v for f, v in mentions.items() if len(v) > 1}
    W('  被多份文档重复描述的脚本：%d 个' % len(multi))
    for f, ds in sorted(multi.items(), key=lambda x: -len(x[1]))[:6]:
        W('      %-30s %d 份' % (f, len(ds)))

    W('\n【6】运行件 gitignore')
    if rt_err:
        W('  ⚠️ %s' % rt_err)
    W('  非 .py/.md 文件 %d 个；未被忽略 %d 个（已跟踪，或被提交/同步）'
      % (len(other), len(not_ignored)))
    W('  说明：已跟踪 ≠ 有问题（如 morning_prompt_std.txt 是刻意入库的模板）；此处仅供核对')
    for x in not_ignored:
        W('      · %s' % x)

    W('\n【7】校验器退出码取值')
    for f, ex, rt in vals:
        W('      %-28s sys.exit=[%s]  return=[%s]' % (f, ', '.join(ex[:5]), ', '.join(rt[:5])))

    W('\n' + '=' * 72)
    W('汇总：P0（失败退出码缺失·高危）%d · 静默失败 %d · 硬编码 %d · 文档腐烂 %d · 未记录脚本 %d'
      % (len(risky), len(silent), len(hard), len(stale) + len(missing), len(undoc)))
    W('=' * 72)

    blob = '\n'.join(L)
    print(blob)
    if a.out:
        io.open(a.out, 'w', encoding='utf-8').write(blob)
        print('\n[written] %s' % a.out)
    return 1 if risky else (2 if (silent or hard or stale or missing) else 0)


if __name__ == '__main__':
    sys.exit(main())
