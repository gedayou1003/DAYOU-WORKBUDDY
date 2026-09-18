# -*- coding: utf-8 -*-
"""链路审计（一次性）：反模式扫描 + 文档对账。结果写 UTF-8 文件供读取。"""
import os
import re
import io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, '.workbuddy')
OUT = os.path.join(D, '_audit_pipeline_out.txt')

skip = {'_audit_pipeline.py', '_rename_tj_0918.py'}
scripts = sorted(f for f in os.listdir(D)
                 if f.endswith('.py') and f not in skip)

# ---- 反模式规则 ----
RULES = [
    ('A1 静默回退默认值', re.compile(r"""\bor\s+['"]20\d\d[-/]""")),
    ('A1b DEFAULT_ 常量兜底', re.compile(r"\bDEFAULT_[A-Z_]+\b")),
    ('A2 stdout 字符串匹配取值', re.compile(r"""['"]已保存[:：]?['"]|\bin\s+out\b.*['"]已|stdout.*split.*['"]""")),
    ('A3 吞异常 pass', re.compile(r"except[^\n:]*:\s*(?:#.*)?\n\s*pass\b")),
    ('A3b 裸 except', re.compile(r"^\s*except\s*:", re.M)),
    ('A4 硬编码绝对路径', re.compile(r"[Cc]:\\\\?Users|/c/Users|gedayou")),
    ('A5 硬编码具体日期', re.compile(r"['\"]2026-0[0-9]-[0-9]{2}['\"]")),
    ('A6 subprocess 抓输出', re.compile(r"subprocess\.(run|Popen|check_output)")),
    ('A7 静默写固定文件', re.compile(r"argparse|OptionParser")),
    ('A8 打印但无退出码', re.compile(r"\bprint\(")),
]

hits = {}
for f in scripts:
    p = os.path.join(D, f)
    try:
        src = io.open(p, encoding='utf-8').read()
    except Exception as e:
        hits.setdefault('READ_FAIL', []).append((f, 0, repr(e)))
        continue
    lines = src.split('\n')
    for name, pat in RULES:
        for i, ln in enumerate(lines, 1):
            if pat.search(ln) if name.startswith('A3b') else pat.search(ln):
                # A3 需要跨行
                hits.setdefault(name, []).append((f, i, ln.strip()[:110]))
    # 跨行吞异常单独处理
    for m in re.finditer(r"except[^\n:]*:\s*\n\s*pass\b", src):
        ln = src[:m.start()].count('\n') + 1
        hits.setdefault('A3 吞异常 pass', []).append((f, ln, 'except → pass'))
    # 退出码语义
    has_main = "if __name__" in src
    has_exit = bool(re.search(r"sys\.exit\(\s*[1-9]", src)) or bool(re.search(r"return\s+[1-9]\b", src))
    if has_main and not has_exit:
        hits.setdefault('A9 main 无失败退出码', []).append((f, 0, '有 __main__ 但无 sys.exit(非零)/return 非零'))

# ---- 文档对账 ----
DOCS = ['脚本地图.md', '报告生成流程.md', 'README_预判系统.md',
        '报告逻辑排版完整性规范_v2.md', '预判规则_v5.md']
doc_text = {}
for d in DOCS:
    p = os.path.join(D, d)
    if os.path.exists(p):
        doc_text[d] = io.open(p, encoding='utf-8').read()

doc_mentions = {}
for d, t in doc_text.items():
    for f in scripts:
        if f in t:
            doc_mentions.setdefault(f, []).append(d)

undocumented = [f for f in scripts if f not in doc_mentions]
missing = []
for d, t in doc_text.items():
    for m in re.finditer(r'\b([A-Za-z_][A-Za-z0-9_]*\.py)\b', t):
        fn = m.group(1)
        if not os.path.exists(os.path.join(D, fn)) and fn not in missing:
            missing.append((fn, d))

with io.open(OUT, 'w', encoding='utf-8') as fo:
    W = fo.write
    W('=' * 72 + '\n链路审计：反模式扫描 + 文档对账\n' + '=' * 72 + '\n\n')
    W('脚本总数（不含 _ 前缀一次性）：%d\n' % len(scripts))
    W('文档数：%d\n\n' % len(doc_text))

    W('#' * 72 + '\n# 一、反模式命中\n' + '#' * 72 + '\n')
    for name, _ in RULES + [('A3 吞异常 pass', None)]:
        rows = hits.get(name, [])
        if not rows and name != 'A9 main 无失败退出码':
            continue
        extra = [r for k, v in hits.items() if k.startswith('A9') and name.startswith('A9') for r in v]
        if name.startswith('A9'):
            rows = [r for k, v in hits.items() if k.startswith('A9') for r in v]
        W('\n--- %s：%d 处 ---\n' % (name, len(rows)))
        seen = set()
        for f, ln, txt in rows:
            k = (f, ln, txt)
            if k in seen:
                continue
            seen.add(k)
            W('  %-38s :%-4s %s\n' % (f, ln or '-', txt))
        if name.startswith('A9'):
            break

    W('\n' + '#' * 72 + '\n# 二、文档对账\n' + '#' * 72 + '\n')
    W('\n--- 未被任何文档提及的脚本（%d）---\n' % len(undocumented))
    for f in undocumented:
        W('  %s\n' % f)
    W('\n--- 文档提到但文件不存在（%d）---\n' % len(missing))
    for fn, d in missing:
        W('  %-36s ← %s\n' % (fn, d))
    W('\n--- 被多份文档重复描述的脚本（Top 20）---\n')
    for f, ds in sorted(doc_mentions.items(), key=lambda x: -len(x[1]))[:20]:
        if len(ds) > 1:
            W('  %-38s %d 份  %s\n' % (f, len(ds), ' / '.join(ds)))

print('written:', OUT)
print('scripts=%d docs=%d undocumented=%d missing_refs=%d'
      % (len(scripts), len(doc_text), len(undocumented), len(missing)))
