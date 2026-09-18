# -*- coding: utf-8 -*-
"""链路审计第二轮：退出码语义 / 跨脚本重复 / 废弃标记 / gitignore 覆盖。"""
import os
import re
import io
import difflib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, '.workbuddy')
OUT = os.path.join(D, '_audit_pipeline2_out.txt')

skip = {'_audit_pipeline.py', '_audit_pipeline2.py'}
scripts = sorted(f for f in os.listdir(D) if f.endswith('.py') and f not in skip)
src = {}
for f in scripts:
    src[f] = io.open(os.path.join(D, f), encoding='utf-8').read()

W = io.open(OUT, 'w', encoding='utf-8').write
W('=' * 72 + '\n链路审计 第二轮\n' + '=' * 72 + '\n')

# ---------- 1. 退出码语义 ----------
W('\n' + '#' * 72 + '\n# 1. 退出码语义（失败路径是否真的非零）\n' + '#' * 72 + '\n')
W('\n判定：有 __main__ 入口，但全文找不到 sys.exit(非零) / return 非零 / raise SystemExit 的脚本\n\n')
no_code = []
for f in scripts:
    s = src[f]
    if 'if __name__' not in s and 'def main' not in s:
        continue
    has_nz = (re.search(r"sys\.exit\(\s*[^0\s)]", s)
              or re.search(r"return\s+[1-9]\b", s)
              or re.search(r"raise\s+SystemExit", s)
              or re.search(r"sys\.exit\(nz|sys\.exit\(rc", s))
    if not has_nz:
        no_code.append(f)
W('  【无失败退出码】%d 个：\n' % len(no_code))
for f in no_code:
    W('    %-40s %6d B  desc=%s\n' % (f, len(src[f]),
      (re.search(r'^"""(.{0,50})', src[f], re.S).group(1).replace('\n', ' ')
       if re.search(r'^"""(.{0,50})', src[f], re.S) else '-')))

# ---------- 2. 校验器退出码明细 ----------
W('\n' + '#' * 72 + '\n# 2. 校验器/测试 退出码明细\n' + '#' * 72 + '\n\n')
for f in scripts:
    if not (f.startswith('check_') or f.startswith('test_') or f.endswith('_verify.py')):
        continue
    s = src[f]
    exits = sorted(set(re.findall(r"sys\.exit\(\s*([^)\n]{0,24})", s)))
    rets = sorted(set(re.findall(r"return\s+([0-9])\b", s)))
    W('  %-32s sys.exit=[%s]  return=[%s]\n' % (f, ', '.join(exits[:6]), ', '.join(rets[:6])))

# ---------- 3. 跨脚本近似重复 ----------
W('\n' + '#' * 72 + '\n# 3. 跨脚本近似重复（difflib，>0.55 才列）\n' + '#' * 72 + '\n\n')


def norm(s):
    s = re.sub(r'#.*', '', s)
    s = re.sub(r'"""(?:.|\n)*?"""', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


big = {f: norm(src[f]) for f in scripts if len(src[f]) > 2500}
pairs = []
names = sorted(big)
for i, a in enumerate(names):
    for b in names[i + 1:]:
        r = difflib.SequenceMatcher(None, big[a], big[b]).quick_ratio()
        if r > 0.55:
            r2 = difflib.SequenceMatcher(None, big[a], big[b]).ratio()
            if r2 > 0.42:
                pairs.append((r2, a, b))
pairs.sort(reverse=True)
W('  近似重复对：%d\n\n' % len(pairs))
for r, a, b in pairs[:25]:
    W('    %.2f  %-36s ~ %s\n' % (r, a, b))

# ---------- 4. 跨脚本同名函数 ----------
W('\n' + '#' * 72 + '\n# 4. 跨脚本同名函数（>=2 个脚本各自定义）\n' + '#' * 72 + '\n\n')
fmap = {}
for f in scripts:
    for m in re.finditer(r'^def\s+([a-zA-Z_]\w*)\s*\(', src[f], re.M):
        fmap.setdefault(m.group(1), set()).add(f)
multi = {k: v for k, v in fmap.items() if len(v) >= 2}
for k in sorted(multi, key=lambda x: -len(multi[x])):
    if k.startswith('_'):
        continue
    W('  %-30s %d 个脚本: %s\n' % (k, len(multi[k]), ', '.join(sorted(multi[k]))))

# ---------- 5. 废弃标记 ----------
W('\n' + '#' * 72 + '\n# 5. 脚本内自述「已废弃/停用/不再使用」\n' + '#' * 72 + '\n\n')
for f in scripts:
    for m in re.finditer(r'.{0,40}(已废弃|已停用|不再使用|deprecated|废弃).{0,50}', src[f]):
        W('  %-34s %s\n' % (f, m.group(0).replace('\n', ' ')[:100]))

# ---------- 6. gitignore 对运行件覆盖 ----------
W('\n' + '#' * 72 + '\n# 6. 运行件是否被 gitignore 覆盖\n' + '#' * 72 + '\n\n')
gi = io.open(os.path.join(ROOT, '.gitignore'), encoding='utf-8').read()
other = sorted(f for f in os.listdir(D)
               if os.path.isfile(os.path.join(D, f))
               and not f.endswith(('.py', '.md')))
W('  .workbuddy 下非 .py/.md 文件 %d 个，用 git check-ignore 实测：\n' % len(other))


def git_ignored(relpaths):
    """用 git check-ignore 精确判定（一次调用，避免 fnmatch 近似误判）。"""
    import subprocess
    if not relpaths:
        return set()
    r = subprocess.run(['git', 'check-ignore', '--stdin'],
                       cwd=ROOT, input='\n'.join(relpaths),
                       capture_output=True, text=True, encoding='utf-8')
    return set(x.strip() for x in (r.stdout or '').split('\n') if x.strip())


rels = ['.workbuddy/' + f for f in other]
ign = git_ignored(rels)
tracked = [r for r in rels if r not in ign]
W('\n  ⚠️ 未被 gitignore（会被提交/同步）：%d\n' % len(tracked))
for r in tracked:
    W('    %s\n' % r)

print('written:', OUT)
print('no_exit_code=%d  dup_pairs=%d  cross_defs=%d  not_ignored=%d'
      % (len(no_code), len(pairs), len(multi), len(untracked_risk)))
