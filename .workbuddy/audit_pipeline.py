# -*- coding: utf-8 -*-
"""链路审计（常驻工具）：一次性回答「现在整个链路有没有 BUG / 重复 / 文档腐烂 / 退出码缺失」。

用法：
    $PY .workbuddy/audit_pipeline.py                 # 全量扫描，打印摘要
    $PY .workbuddy/audit_pipeline.py --full          # 逐条明细（默认只打摘要 + Top 若干）
    $PY .workbuddy/audit_pipeline.py --out 文件.txt   # 结果同时写 UTF-8 文件（终端中文乱码时用）

退出码：0 无 P0 级问题 / 1 有 P0 级问题（失败路径静默）/ 2 仅 P1/P2
  P0 判定口径：会打印「失败/❌/[FAIL]」但**没有失败退出码**的脚本 —— 属「失败被当成成功」，
  是本项目历史上最贵的一类 BUG（见 memory 2026-09-18 审计）。

检查九项：
  1. 退出码语义：有入口但无 sys.exit(非零) 的脚本，并标记其中「代码区里输出/抛出失败字样」
     的高危子集（注释、docstring、表格渲染符号 ❌ 一律不计 —— 假阳性会淹没真高危）
  2. 静默失败反模式：危险默认值/静默回退、吞异常 pass/continue、静默 return、裸 except
     （2026-09-23 起用 AST 扫描，此前是三条正则 —— 实测漏报过半：31 处只报出 15 处）
  3. 硬编码：绝对路径（含用户名）、写死的具体日期
  4. 文档对账：文档引用的 *.py 是否存在（区分「已归档」与「真不存在」）、脚本是否被文档遗漏
  5. 重复：跨脚本近似重复对、跨脚本同名函数、脚本被多份文档重复描述
  6. 运行件：.workbuddy 下非 .py/.md 文件是否被 gitignore 覆盖（用 git check-ignore 实测）
  7. 校验器体检：check_*/test_* 的退出码取值分布
  8. 测试覆盖：非 test_ 脚本是否有对应 test_<名字>.py；单列「在役链路缺口」（2026-09-21 新增）
  9. subprocess 调用点是否校验退出码（判据：所在函数体里有没有 returncode/check=，
     或 rc 是否被 sys.exit/return 直接传给上游）（2026-09-21 新增，2026-09-23 收紧）

⚠️ 【8】【9】是**信息项**，不参与退出码判定：8 的缺口是长期存量（51 个），
   若让它长期报红会变成永久噪声、导致闸门被无视；9 的命中多数是「失败也无所谓」的调用。
   两节的价值在于把印象变成清单，逐条确认时不必再翻全仓代码。

静默失败的「刻意豁免」约定（与 §4 文档对账的 explained/external 同口径）：
   确属刻意（终端编码收口、缓存读写、getmtime 竞态、多格式尝试这类）的吞异常，
   在 **except 行尾**写 `# silent-ok: <原因>`（原因 ≥4 字）。扫描器把它单列【2】的
   「已声明豁免」并逐条打印原因，不计入阈值 —— 于是**未声明项数 = 真待办数**。
   原因过短或写在别的行一律不算声明：声明要能被人复核，不是用来把闸门关掉的开关。

同一约定自 2026-09-23 起覆盖【3】硬编码：
   测试里刻意构造的样本路径（如造 `C:/Users/alice/…` 验证扫描器本身）不是真硬编码，
   在**命中那一行**行尾写 `# silent-ok: <原因>` 即进【3】的「已声明豁免」。
   没有这个出口时，这 2 处会永久把闸门顶在 WARN 上，**真新增一条硬编码时
   没人看得出「2 变成 3」**（温水煮青蛙 —— 与永久噪声同源）。

设计约束：只读、不改任何文件；结果可复现（同一输入两次运行一致）。
"""
import argparse
import ast
import io
import os
import re
import subprocess
import sys
import tokenize

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # silent-ok: 终端编码收口尽力而为，失败不影响结论
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
# 2026-09-23 由正则改为 AST。起因：用一次性 AST 探针实测，旧正则实现把 **31 处漏成 15 处**。
# 三种漏报形态（都是正则本身的局限，不是代码里没有）：
#   ① body 是 `continue` / `return` 而不是 `pass` —— 正则只认 pass；
#   ② except 与 pass 之间夹了注释行 —— `\s*\n\s*pass` 匹配不上；
#   ③ 同行写 `except Exception: pass` —— 正则要求换行。
# 还有一类反向失真：正则按字符偏移推算行号，docstring / 字符串里的示例代码会被算成真命中。
# AST 直接看 ExceptHandler.body 的结构，与排版无关，也不受注释、docstring、字符串干扰。
#
# 五类形态（要求 body **全部**由该形态构成，避免误伤正常处理逻辑）：
#   BARE   裸 except（无异常类型）—— 连捕获什么都说不清。命中即不再按 body 分类，避免一条记两次
#   PASS   body 只有 pass / continue —— 完全静默
#   RETURN body 只有 return（无值）—— 静默返回 None
#   RETVAL body 只有 return <字面量> —— 静默返回默认值（参数静默回退就是这个形态）
#   ASSIGN body 只有赋值、RHS 是**裸字面量**、且异常未绑定名字 —— 即「读不动就回退到写死的默认值」。
#          判据刻意收窄（`as e` 或 RHS 里出现表达式一律不算）：把异常转写成错误记录
#          （`r = {'error': str(e)}`）、超时按 124 计这类**正常降级**不算反模式，
#          否则 17 处里只有 7 处是真的，噪声会把真问题淹掉。
#          为什么必须收这一类：2026-09-23 实测 gen_tj_archive 的两处 `old_x = ''` / `= 0`
#          会让「人工精修版不许覆盖」的守卫**整条跳过**（`if old_txt and ...` 短路），
#          与 2026-09-21 那次 P0 数据丢失同族 —— 而旧实现（三条正则）对它完全无感。
#
# 刻意豁免的写法：在 except 行尾写 `# silent-ok: <原因>`。
#   · 原因少于 4 个字视为**未声明**（防止用空声明把闸门蒙混过关，与「声明了不存在的目录照样算问题」同口径）
#   · 已声明项**逐条打印原因**，但不计入阈值 —— 降噪不等于静默，否则就是偷偷把闸门调松
#   · 必须是**真注释**（tokenize 的 COMMENT 记号），字符串里长的像声明的文本不算 ——
#     否则改一行测试数据就能伪造声明把闸门关掉（2026-09-23 实测过，见 comment_text_lines）
SILENT_OK = re.compile(r'#\s*silent-ok\s*[:：]\s*(\S.{3,})')
SILENT_LABEL = {'BARE': '裸 except（无异常类型）', 'PASS': 'body 只有 pass/continue',
                'RETURN': '静默 return None', 'RETVAL': '静默返回字面量（参数回退）',
                'ASSIGN': '危险默认值（读不动就回退到写死的字面量）'}
# 写死日期兜底：原先混在 §2 的三条正则里各扫一遍，现改到 code_only_lines 的代码区上扫
DEAD_DATE = re.compile(r"""\bor\s+['"]20\d\d[-/][0-9]{2}['"]""")


def comment_text_lines(s):
    """返回 {行号: 该行的**真实注释**文本}（用 tokenize 取 COMMENT 记号）。

    为什么不能直接在原始行上跑 SILENT_OK 正则：**字符串内容里的
    `# silent-ok: …` 会伪造声明**。2026-09-23 实测：测试样本串里的
    `# silent-ok: 短`（原因只有 1 个字，靠串尾的 `\\n'` 凑够长度）被当成
    正式声明，把一处真硬编码放行了 —— 改一行测试数据就能悄悄关掉闸门。
    声明必须是**人写的那一行注释**，不是被引号包起来的一段文本。

    取不到词法（语法不完整）时返回空表：**宁可多报，也不放过**。
    """
    out = {}
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(s).readline))
    except Exception:  # silent-ok: 词法不可得即视为「无任何声明」，判定只会更严不会更松
        return out
    for t in toks:
        if t.type == tokenize.COMMENT:
            out.setdefault(t.start[0], []).append(t.string)
    return {k: ' '.join(v) for k, v in out.items()}


def scan_silent(src):
    """扫描静默失败反模式。返回 (未声明, 已声明豁免)，元素均为 (文件, 行号, 说明)。"""
    undecl, declared = [], []
    for f, s in src.items():
        try:
            tree = ast.parse(s)
        except SyntaxError as e:
            # 解析不了就不能假装「这里没问题」—— 如实报成待办
            undecl.append((f, 0, 'PARSE   语法不可解析，静默失败扫描跳过（%s）' % str(e)[:40]))
            continue
        head_comments = comment_text_lines(s)

        def _note(node, kind):
            ln = node.lineno
            # 只在**真注释**里找声明（不是原始行）：字符串内容不得伪造声明
            m = SILENT_OK.search(head_comments.get(ln, ''))
            body = '%-7s %s' % (kind, SILENT_LABEL[kind])
            if m:
                declared.append((f, ln, '%s（silent-ok：%s）' % (body, m.group(1))))
            else:
                undecl.append((f, ln, body))

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if node.type is None:
                _note(node, 'BARE')
                continue                      # 裸 except 已是最强判定，不再按 body 二次计数
            kinds = set()
            for st in (node.body or []):
                if isinstance(st, ast.Pass):
                    kinds.add('pass')
                elif isinstance(st, ast.Continue):
                    kinds.add('continue')
                elif isinstance(st, ast.Return):
                    if st.value is None:
                        kinds.add('ret')
                    elif isinstance(st.value, ast.Constant):
                        kinds.add('retval')
                    else:
                        kinds.add('other')
                elif isinstance(st, (ast.Assign, ast.AnnAssign)):
                    v = st.value
                    lit = isinstance(v, (ast.Constant, ast.Dict, ast.List, ast.Tuple, ast.Set))
                    kinds.add('assign' if (lit and not node.name) else 'other')
                else:
                    kinds.add('other')
            if kinds and kinds <= {'pass', 'continue'}:
                _note(node, 'PASS')
            elif kinds == {'ret'}:
                _note(node, 'RETURN')
            elif kinds and kinds <= {'retval'}:
                _note(node, 'RETVAL')
            elif kinds and kinds <= {'assign'}:
                _note(node, 'ASSIGN')
        for ln, code in code_only_lines(s):
            if DEAD_DATE.search(code):
                undecl.append((f, ln, 'DEAD    疑似静默回退到写死日期'))
    return undecl, declared


# ---------------- 3. 硬编码 ----------------
# 三引号字符串（含带前缀的 f/r/b）—— 只有这类才整段剔除
TRIPLE_STR = re.compile(r'^[A-Za-z]{0,3}("""|\'\'\')')
_FS_START = getattr(tokenize, 'FSTRING_START', None)
_FS_END = getattr(tokenize, 'FSTRING_END', None)
_FS_MID = getattr(tokenize, 'FSTRING_MIDDLE', None)


def code_only_lines(s):
    """返回 [(行号, 仅在「代码区」的行内容)]，剔除注释与**三引号**字符串。

    必要性：本项目大量「已修复」的记录写在 docstring 里（如「- 删掉写死的绝对路径」），
    若不剔除，扫描器会把**修好之后留下的说明**当成命中 —— 那就是自造噪声，
    而噪声会让闸门被无视（见 MEMORY「校验器体检」）。

    2026-09-23 重写（原为手写三引号状态机，见下）。
    旧实现**会与源码失步**：实测 `gen_tj_archive.py` 只保留 139/356 行，
    失步点之后整段（含 `__main__` 与 `sys.exit(main())`）被吞掉 ——
    后果是 §1 把它误报成「有入口但无失败退出码」，而 §1/§3/§9 此后对
    **该文件后半部分永久失明**（看着干净，其实没扫到）。
    失步诱因：docstring 正文里带引号、多行 f-string 模板、行内 `#` 在字符串里，
    手写状态机无从区分。新实现改用标准库 `tokenize`（真词法分析）：
      · COMMENT 与**三引号** STRING 的字符区间清空（多行字符串的中间行整行清空）；
      · 单引号字符串**照旧保留** —— §3 硬编码路径检测恰恰依赖看见字符串里的路径，
        全清会把闸门顺手关掉（第六原则：降噪不能变成悄悄放宽）；
      · 三引号 f-string（py3.12+ 拆成 FSTRING_START/MIDDLE/END）整段清空；
      · tokenize 抛错（语法不完整）就**退回整行原样返回** —— 宁可多看也不漏看。
    """
    lines = s.split('\n')
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(s).readline))
    except Exception:
        return [(i, ln) for i, ln in enumerate(lines, 1)]
    cut = {}          # 行号 -> [(起列, 止列)]，止列为 None 表示「到行尾」
    depth = 0         # 三引号 f-string 嵌套层数

    def blank(ln_no, a, b):
        cut.setdefault(ln_no, []).append((a, b))

    for t in toks:
        if _FS_START is not None and t.type == _FS_START:
            if TRIPLE_STR.match(t.string):
                depth += 1
                blank(t.start[0], t.start[1], None)
            continue
        if _FS_END is not None and t.type == _FS_END:
            if depth:
                depth -= 1
                blank(t.start[0], 0, t.end[1])
            continue
        if depth:
            # 三引号 f-string 内部（字面量或插值表达式）：整段清空，避免模板正文被当代码
            for ln_no in range(t.start[0], t.end[0] + 1):
                blank(ln_no, 0, None)
            continue
        if t.type == tokenize.COMMENT:
            blank(t.start[0], t.start[1], t.end[1])
        elif t.type == tokenize.STRING and TRIPLE_STR.match(t.string):
            for ln_no in range(t.start[0], t.end[0] + 1):
                blank(ln_no, t.start[1] if ln_no == t.start[0] else 0,
                      t.end[1] if ln_no == t.end[0] else None)

    out = []
    for i, ln in enumerate(lines, 1):
        if i in cut:
            ch = list(ln)
            for a, b in cut[i]:
                hi = len(ch) if b is None else b
                for k in range(max(0, a), max(0, min(len(ch), hi))):
                    ch[k] = ' '
            ln = ''.join(ch)
        out.append((i, ln))
    return out


def scan_hardcode(src):
    """硬编码绝对路径扫描。返回 (hits, declared)。

    声明出口（2026-09-23 加，与 §2 的 `# silent-ok: <原因>` 同一约定）：
    在**命中那一行**行尾写真实注释 `# silent-ok: <原因>` 即视为刻意豁免，进 declared 单列。

    为什么必须有它：测试里故意构造的样本路径（`C:/Users/alice/…`）会永久计成
    2 处硬编码 → 闸门长期停在「硬编码 2」这个 WARN 上，**真新增一条硬编码时
    没人看得出「2 变成 3」**（温水煮青蛙）。降噪不等于静默：declared 逐条打印。

    ⚠️ 归属判定用 `comment_text_lines`（真注释），不是原始行 —— 否则字符串里的
    `# silent-ok: …` 能伪造声明（实测踩过）。
    """
    hits, declared = [], []
    for f, s in src.items():
        cmts = comment_text_lines(s)
        for ln, code in code_only_lines(s):
            for m in re.finditer(r'[Cc]:[\\/]{1,2}Users[\\/]{1,2}(\w+)|/c/Users/(\w+)', code):
                user = m.group(1) or m.group(2)
                why = '硬编码绝对路径（用户名 %s）' % user
                d = SILENT_OK.search(cmts.get(ln, ''))
                (declared if d else hits).append(
                    (f, ln, why + ('（silent-ok：%s）' % d.group(1) if d else '')))
    return hits, declared


# ---------------- 4. 文档对账 ----------------
DOCS = ['脚本地图.md', '报告生成流程.md', 'README_预判系统.md',
        '报告逻辑排版完整性规范_v2.md', '预判规则_v5.md']
PLACEHOLDER_OK = re.compile(r'^(\w*MMDD|\w*xxx|xxx)\.py$')   # 命名约定占位符

# 技能家目录：部分在役脚本（缠论引擎）不在本仓库，而在用户级技能目录里。
SKILL_HOME = os.path.expanduser(os.path.join('~', '.workbuddy', 'skills'))

# 「已交代」标注词：命中即说明**文档自己已经把这条讲清楚了**（历史沿革 / 已归档 / 已废弃 /
# 尚未创建），读者不会照它去找一个活脚本。→ 归入 explained，不计入文档腐烂。
#
# ⚠️ 为什么必须把这类单独列出来而不是继续算作腐烂：
#   2026-09-21 复核发现，「文档腐烂 37 处」里真正会误导读者的只有 4 处，
#   其余是「文档已写『已归档 → archive/…』」与「脚本在技能目录且文档写明了技能目录」。
#   假阳性 = 噪声 = 闸门被无视（与 M-9 审计器假阳性同源）。
#   **但降噪绝不等于静默** —— explained 会逐条打印命中的标注词，人一眼能看出是否放水过度。
EXPLAINED = re.compile(r'已归档|归档|移至|移入|移出|存档|已废弃|废弃|~~|旧版|原版'
                       r'|尚未创建|计划中|改名|取代')

# 文档自述的外部脚本根：`技能目录：`~/.workbuddy/skills/chan-signal__skillhub``
# 用「文档声明位置 + 真实磁盘解析」替代「硬编码白名单」——
# 白名单是固定映射表（M-8/M-12 的定时炸弹），声明+解析则天然随环境变化。
EXTERNAL_ROOT = re.compile(r'(?:技能目录|外部目录|脚本位置|引擎目录)\s*[：:]?\s*`?([^\s`）)，、*]+)`?')

# 行内路径前缀：`skills/chan-signal__skillhub/run_000001_x.py`
INLINE_PREFIX = re.compile(r'(?:^|[\s`(\[])([\w.~/-]+/)([A-Za-z_][A-Za-z0-9_]*\.py)')

_ARCH_CACHE = None


def _archive_index():
    """归档目录索引：{文件名: 相对路径}。缓存，避免每处引用都走一遍 os.walk。"""
    global _ARCH_CACHE
    if _ARCH_CACHE is None:
        _ARCH_CACHE = {}
        for root, _dirs, files in os.walk(ARCHIVE):
            for f in files:
                _ARCH_CACHE.setdefault(f, os.path.relpath(os.path.join(root, f), ROOT))
    return _ARCH_CACHE


def _resolve(base, fn):
    """按真实磁盘解析「base/fn」是否存在。base 可为相对路径、`skills/x/` 或 `~/...`。

    只认磁盘事实，不认任何写死的名单：目录不存在 → 解析失败 → 该引用照旧算问题。
    """
    base = os.path.expanduser(base)
    cands = []
    if os.path.isabs(base):
        cands.append(os.path.join(base, fn))
    else:
        cands += [os.path.join(ROOT, base, fn), os.path.join(HERE, base, fn)]
        parts = [q for q in base.replace('\\', '/').split('/') if q not in ('', '.')]
        if parts and parts[0] == 'skills':
            # 文档里的 `skills/x/` 指用户级技能目录，不是仓库里的 skills/
            cands.append(os.path.join(os.path.dirname(SKILL_HOME), *parts, fn))
        elif parts:
            cands.append(os.path.join(SKILL_HOME, parts[-1], fn))
    return any(os.path.exists(c) for c in cands)


def scan_docs(src):
    """文档对账 —— 四类分开报，绝不混算：

      stale      引用已归档脚本且**至少一处未交代** → 真腐烂，必须修（退出码相关）
      missing    引用真不存在且**至少一处未交代**   → 真腐烂，必须修（退出码相关）
      explained  已归档/已废弃/尚未创建，且**每一处**都交代清楚了 → 不计
      external   脚本在仓库外（技能目录），且**文档声明了位置 + 磁盘可解析** → 不计

    判定粒度是**出现位置**，不是 (文件, 文档) 对：
      同一个文件名在一份文档里往往出现多次，语境各不相同（既有「已归档」的历史沿革，
      也有「现在就用它」的操作指引）。若按对去重，后面的真问题会被前面的「已交代」吃掉 ——
      实测 `append_consensus.py` 在《脚本地图.md》出现 3 次，前两处写了归档，
      第 333 行的操作指引没写，去重后这条真腐烂直接消失。
    故：**只要有一处没交代，整条就算腐烂**，并直接给出该处的行号。
    """
    docs = {d: io.open(os.path.join(HERE, d), encoding='utf-8').read()
            for d in DOCS if os.path.exists(os.path.join(HERE, d))}
    mentions = {}
    stale, missing, explained, external, undocumented = [], [], [], [], []
    arch_idx = _archive_index()
    for d, t in docs.items():
        for f in src:
            if f in t:
                mentions.setdefault(f, []).append(d)
        lines = t.splitlines()
        # 文档级声明的外部根（同一文档内生效）
        roots = [m.group(1) for m in (EXTERNAL_ROOT.search(ln) for ln in lines) if m]
        occ = {}          # fn -> [(行号, 原文, 外部根, 标注词)]
        for i, ln in enumerate(lines, 1):
            for m in re.finditer(r'\b([A-Za-z_][A-Za-z0-9_]*\.py)\b', ln):
                fn = m.group(1)
                # 存在性以**磁盘为准**：`src` 里排除了 SKIP（本文件自身），
                # 若只判 `fn in src`，文档里每提一次 `audit_pipeline.py` 都会被算成「真不存在」——
                # 纯噪声，会把真正的文档腐烂淹掉。
                if (fn in src or os.path.exists(os.path.join(HERE, fn))
                        or PLACEHOLDER_OK.match(fn)):
                    continue
                # ① 行内带路径前缀 → 按磁盘解析
                pre = next((pm.group(1) for pm in INLINE_PREFIX.finditer(ln)
                            if pm.group(2) == fn), '')
                base = pre if (pre and _resolve(pre, fn)) else ''
                # ② 文档声明了外部根 → 按磁盘解析
                if not base:
                    base = next((r for r in roots if _resolve(r, fn)), '')
                mk = EXPLAINED.search(ln)
                occ.setdefault(fn, []).append((i, ln.strip(), base, mk.group(0) if mk else ''))
        for fn, items in occ.items():
            hit = next((it for it in items if it[2]), None)          # 有任一处解析到技能目录
            bad = next((it for it in items if not it[2] and not it[3]), None)  # 未解析且未交代
            if hit:
                external.append((fn, d, '%s @L%d' % (hit[2], hit[0])))
            elif bad:
                arch = arch_idx.get(fn)
                detail = 'L%d' % bad[0]
                if arch:
                    detail += ' · 在 %s' % arch
                (stale if arch else missing).append((fn, d, detail))
            else:
                explained.append((fn, d, '%s @L%d' % (items[0][3], items[0][0])))
    undocumented = [f for f in src if f not in mentions]
    return docs, mentions, stale, missing, explained, external, undocumented


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


# ---------------- 8. 测试覆盖 ----------------
# 在役链路：每日/每档都会被调用到的脚本。这些缺测试才算缺口；
# 一次性回测/分析脚本（backtest_* / gen_*_html 等）缺测试是正常的，不计入。
CRITICAL_SCRIPTS = {
    'fetch_zsxq.py', 'fetch_zsxq_fallback.py', 'backfill_zsxq_window.py',
    'get_daily_ohlc.py', 'forecast_analyze.py', 'calc_tech_multi.py', 'scan_ths.py',
    'chain_apply.py', 'chainlib.py', 'normalize_chain.py',
    'report_builder.py', 'md_to_html_report.py', 'gen_forecast_svg.py', 'gen_tj_archive.py',
    'check_layout.py', 'check_integrity.py', 'check_display_name.py', 'check_cookie.py',
    'display_names.py', 'layout_spec.py',
    'cleanup_workspace.py', 'export_backup.py', 'audit_pipeline.py', 'audit_coverage.py',
}

# 测试基础设施：本身不是被测对象，不该被算作「缺测试」（否则它会一直在缺口清单里）
TEST_INFRA = {'run_tests.py'}


def scan_coverage(src):
    """非 test_ 脚本是否有对应测试文件。

    判据（前缀匹配，非严格同名）：存在 `test_<stem>.py` 或 `test_<stem>_*.py`
    ——`check_integrity.py` 的负例验证是 `test_check_integrity_neg.py`，
       `check_layout.py` 的是 `test_check_layout_basis.py`，严格同名会把它们误报成缺口。

    2026-09-21 首次盘出缺口清单 —— 缺口本身不是 BUG，价值在于把
    「在役链路有没有测试」从印象变成清单；其中属 CRITICAL_SCRIPTS 的才重点看。
    """
    tests = sorted(f for f in src if f.startswith('test_'))

    def covered_by(stem):
        return [t for t in tests if t == 'test_%s.py' % stem or t.startswith('test_%s' % stem)]

    covered, uncovered = [], []
    for f in sorted(src):
        if f.startswith('test_') or f in TEST_INFRA:
            continue
        stem = f[:-3]
        (covered if covered_by(stem) else uncovered).append(f)
    crit_gap = [f for f in uncovered if f in CRITICAL_SCRIPTS]
    return covered, uncovered, crit_gap


# ---------------- 9. subprocess 未校验退出码 ----------------
SPAWN = re.compile(r'\bsubprocess\.(run|Popen|call|check_output)\s*\(|\bos\.system\s*\(')


def _block_after(lines, j, cap=40):
    """调用点之后「还要看多远」= 至多 cap 行，且遇到**缩进小于所在 def** 的行就停。

    旧版固定看 6 行，太窄：退出码校验写在第 9 行（`fetch_zsxq.py`）或第 5 行但格式较长
    （`test_arg_guard.py` 顶层脚本形态）都会被误报。这里改成「所在函数的范围」：
      · 调用点在某个 def 内 → 看到该 def 结束（出现缩进更小的行）为止；
      · 顶层脚本代码（没有 enclosing def）→ 看满 cap 行
        （顶层语句彼此平级，用「缩进更小」无法划界）。
    有界很重要：无上限地看下去，会把**别的函数**里的 `returncode` 当成「这行已校验」。
    """
    code = lines[j][1]
    indent = len(code) - len(code.lstrip())
    base = None
    for k in range(j, -1, -1):                     # 向上找最近的、缩进更小的 def
        c = lines[k][1]
        if not c.strip():
            continue
        ind = len(c) - len(c.lstrip())
        if ind < indent and re.match(r'\s*def\b', c):
            base = ind
            break
    out = []
    for _, c in lines[j + 1:j + 1 + cap]:
        if base is not None and c.strip() and (len(c) - len(c.lstrip())) < base:
            break                                  # 函数结束
        out.append(c)
    return '\n'.join(out)


# 退出码直接向上游传递的写法：rc 由调用栈上游接住，本行无需再校验
PASS_THROUGH = re.compile(r'(?:sys\.exit|return)\s*\(?\s*subprocess\.')


def scan_subprocess(src):
    """subprocess 调用点的退出码**是否有人接住**（块级判据，不再用固定 6 行）。

    不代表一定是 BUG：可能由调用方在别处校验，或本身就是「失败也无所谓」的辅助命令
    （如读剪贴板失败返回空串后仍有 warn）。列出来是为了逐个低成本确认，
    比出事后再回溯便宜。2026-09-21 首次盘出 5 处。

    2026-09-23 收紧（旧版 6 行窗口的 6 处命中**全部**是误报，长期挂着会让闸门被无视）：
      · 窗口改为「所在 def 的函数体 / 顶层看满 40 行」（`_block_after`）——
        `fetch_zsxq.py` 的 `r.returncode` 写在调用点后第 9 行，旧版看不到；
      · 新增「直接传递」判据：`sys.exit(subprocess.call(...))` / `return subprocess.run(...)`
        的 rc 由上游接住（`run.py` 与各测试 helper 就是这个形态）；
      · 判据同时看**调用行本身**（`check=True` 常与调用同行，旧版从下一行看起 → 误报）。
    """
    hits = []
    for f, s in src.items():
        lines = code_only_lines(s)
        for j, (ln, code) in enumerate(lines):
            mm = SPAWN.search(code)
            if not mm:
                continue
            if PASS_THROUGH.search(code):
                continue
            scope = code + '\n' + _block_after(lines, j)
            if 'returncode' in scope or 'check=' in scope:
                continue
            hits.append((f, ln, mm.group(1) or 'system'))
    return hits


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
    silent, silent_ok = scan_silent(src)
    hard, hard_ok = scan_hardcode(src)
    docs, mentions, stale, missing, explained, external, undoc = scan_docs(src)
    pairs, shared = scan_dups(src)
    other, not_ignored, rt_err = scan_runtime()
    vals = scan_validators(src)
    covered, uncovered, crit_gap = scan_coverage(src)
    spawn = scan_subprocess(src)

    W('\n【1】退出码语义')
    W('  有入口但无失败退出码：%d 个' % len(no_code))
    W('  ⚠️ 高危子集（会打印失败字样却退出 0）：%d 个' % len(risky))
    for f in risky:
        W('      %s' % f)
    if a.full:
        for f in no_code:
            W('      · %s' % f)

    W('\n【2】静默失败反模式：%d 处未声明' % len(silent))
    for f, ln, why in (silent if a.full else silent[:8]):
        W('      %-34s :%-4s %s' % (f, ln, why))
    if len(silent) > 8 and not a.full:
        W('      … 其余 %d 处（--full 展开）' % (len(silent) - 8))
    # 已声明豁免同样**逐条打印**（含原因）—— 不计入阈值不等于不打印，否则就是偷偷调松闸门
    W('  ── 以下不计入：except 行尾声明了 `# silent-ok: 原因` 的刻意豁免 ──')
    W('  已声明豁免：%d 处' % len(silent_ok))
    for f, ln, why in (silent_ok if a.full else silent_ok[:12]):
        W('      %-34s :%-4s %s' % (f, ln, why))
    if len(silent_ok) > 12 and not a.full:
        W('      … 其余 %d 处（--full 展开）' % (len(silent_ok) - 12))

    W('\n【3】硬编码：绝对路径 %d 处未声明' % len(hard))
    for f, ln, why in (hard if a.full else hard[:8]):
        W('      %-34s :%-4s %s' % (f, ln, why))
    if len(hard) > 8 and not a.full:
        W('      … 其余 %d 处（--full 展开）' % (len(hard) - 8))
    # 已声明豁免同样逐条打印（不计入阈值 ≠ 不打印）
    W('  ── 以下不计入：命中行尾声明了 `# silent-ok: 原因` 的刻意豁免 ──')
    W('  已声明豁免：%d 处' % len(hard_ok))
    for f, ln, why in (hard_ok if a.full else hard_ok[:12]):
        W('      %-34s :%-4s %s' % (f, ln, why))

    W('\n【4】文档对账（%d 份）' % len(docs))
    W('  ⚠️ 文档引用已归档脚本（且未交代归档）：%d 处  ← 文档腐烂，必须修' % len(stale))
    for fn, d, arch in (stale if a.full else stale[:10]):
        W('      %-30s ← %-22s (在 %s)' % (fn, d, arch))
    W('  ⚠️ 文档引用真不存在（且未交代）：%d 处  ← 文档腐烂，必须修' % len(missing))
    for fn, d, detail in (missing if a.full else missing[:8]):
        W('      %-30s ← %-22s (%s)' % (fn, d, detail))
    # 下面两类**不计入腐烂**，但一律逐条打印 —— 降噪不等于静默（否则就是偷偷调松闸门）
    W('  ── 以下两类不计入腐烂，逐条列出以便人工核对是否放水过度 ──')
    W('  已交代归档/废弃/未建：%d 处（文档自己写清了，读者不会去找活脚本）' % len(explained))
    for fn, d, mk in (explained if a.full else explained[:12]):
        W('      %-30s ← %-22s (标注词「%s」)' % (fn, d, mk))
    if len(explained) > 12 and not a.full:
        W('      … 其余 %d 处（--full 展开）' % (len(explained) - 12))
    W('  仓库外脚本（技能目录，磁盘已解析）：%d 处' % len(external))
    for fn, d, base in (external if a.full else external[:12]):
        W('      %-30s ← %-22s (%s)' % (fn, d, base))
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

    W('\n【8】测试覆盖')
    W('  有对应 test_：%d 个；缺测试：%d 个（一次性回测脚本不计入缺口）'
      % (len(covered), len(uncovered)))
    W('  ⚠️ 在役链路缺口：%d 个  ← 这些每日会被调用，优先补' % len(crit_gap))
    for f in crit_gap:
        W('      · %s' % f)
    if a.full:
        W('  （全部缺测试脚本）')
        for f in uncovered:
            W('      · %s' % f)

    W('\n【9】subprocess 未校验退出码：%d 处' % len(spawn))
    W('  说明：调用点后 6 行内无 returncode/check=。可能由上层别处校验，逐个确认成本很低')
    for f, ln, kind in (spawn if a.full else spawn[:10]):
        W('      %-34s :%-4s subprocess.%s' % (f, ln, kind))

    W('\n' + '=' * 72)
    W('汇总：P0（失败退出码缺失·高危）%d · 静默失败 %d（未声明） · 硬编码 %d（未声明） · 文档腐烂 %d · 未记录脚本 %d'
      % (len(risky), len(silent), len(hard), len(stale) + len(missing), len(undoc)))
    W('      · 在役链路缺测试 %d · subprocess 未校验 %d' % (len(crit_gap), len(spawn)))
    W('      文档腐烂只计「未交代归档 / 未解析到技能目录」的引用；'
      '另有已核销 %d 处（已交代归档 %d + 仓库外已解析 %d），明细见【4】'
      % (len(explained) + len(external), len(explained), len(external)))
    W('      静默失败只计「未声明」的；另有已声明豁免 %d 处'
      '（except 行尾 `# silent-ok: 原因`，逐条见【2】）' % len(silent_ok))
    W('      硬编码只计「未声明」的；另有已声明豁免 %d 处'
      '（命中行尾 `# silent-ok: 原因`，逐条见【3】）' % len(hard_ok))
    W('=' * 72)

    blob = '\n'.join(L)
    print(blob)
    if a.out:
        io.open(a.out, 'w', encoding='utf-8').write(blob)
        print('\n[written] %s' % a.out)
    return 1 if risky else (2 if (silent or hard or stale or missing) else 0)


if __name__ == '__main__':
    sys.exit(main())
