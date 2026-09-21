# -*- coding: utf-8 -*-
"""gen_tj_archive 守卫与保真度回归测试。

为什么必须有这个测试（2026-09-21 全链路冒烟的真实事故）：
  归档文件 `outputs/DRAGON_BALL_原始记录_YYYY-MM-DD.md` 是**人工精修交付物**
  （标题挑核心定调句、附件带 download 次数、富文本解码、窗口带判读注解）。
  而机械生成器无条件覆盖它，且两道旧守卫都拦不住：
    · 「0 条守卫」不管用 —— 本轮确实有 3 条；
    · 「缩水守卫」只比**条目数**（3 vs 3）—— 丢的是**条目内的信息密度**；
    · 「按体积守卫」方向是反的 —— 机械版 6080 B > 精修版 5688 B。
  结果是「原文一字不差」的正文里混进 `<e type="text_bold" title="%E5%BE%88..." />`
  这串机器噪声，附件精确字节与 download 次数消失，人工注解被静默抹掉。

本测试钉死两件事：
  A. **守卫真的拦得住**：不带生成戳的文件（=人工精修版）绝对不能被改写，一个字节都不行；
  B. **保真度不回退**：富文本必须解码、附件必须带精确字节与 download、类型必须中文化。

用法：$PY .workbuddy/test_tj_guard.py
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('gtj', os.path.join(HERE, 'gen_tj_archive.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

fails = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


def run(argv):
    """在受控 sys.argv 下调 main()，返回 (rc, 输出)。"""
    old = sys.argv
    sys.argv = ['gen_tj_archive.py'] + argv
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = m.main()
    finally:
        sys.argv = old
    return rc, buf.getvalue()


def sandbox(n_items, gid=None, with_rich=True, with_files=True, today_out=None):
    """建沙箱：patched SRC/META/ROOT，并在 ROOT/outputs 下准备目录。"""
    sb = tempfile.mkdtemp(prefix='tjguard_')
    os.makedirs(os.path.join(sb, 'outputs'), exist_ok=True)
    gid = gid if gid is not None else m.TARGET_GID
    items = []
    for i in range(n_items):
        items.append({
            'gid': gid,
            'topic_id': 'T%03d' % i,
            'create_time': '2026-09-20T1%d:00:00.000+0800' % i,
            'type': 'q&a' if i == 0 else 'talk',
            'text': ('<e type="text_bold" title="%E5%BE%88%E7%90%86%E8%A7%A3" />'
                     if (with_rich and i == 0) else '正文第%d条' % i),
            'files': ([{'name': 'f%d.pdf' % i, 'size': 2037146, 'download_count': 791}]
                      if with_files else []),
            'images': [],
        })
    src = os.path.join(sb, 'zsxq_fetch_raw.json')
    with open(src, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False)
    m.SRC = src
    m.META = os.path.join(sb, 'zsxq_fetch_meta.json')   # 故意不存在 → 不触发 stale 守卫
    m.ROOT = sb
    return sb


def target_path(sb):
    import datetime
    return os.path.join(sb, 'outputs',
                        'DRAGON_BALL_原始记录_%s.md' % datetime.datetime.now().strftime('%Y-%m-%d'))


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def write(p, s):
    with open(p, 'w', encoding='utf-8') as f:
        f.write(s)


# ═══════════════════════════════════════════════════════════════
print('A) 人工精修守卫：不带生成戳的文件绝不能被机械值改写')
print('=' * 62)
sb = sandbox(3)
out = target_path(sb)
CURATED = ('# DRAGON BALL模型 原始记录归档 · 精修版哨兵\n\n'
           '> 人工精修 · 故意不含生成器标记\n\n'
           '## [1] 2026-09-20T21:40:29.897+0800 · 人工挑选的核心定调句…（核心定调）\n\n'
           '- **类型**: talk（问答）\n'
           '- **附件**（1）: 周度思考 2026.9.20.pdf（size 2,037,146 / download 791）\n\n---\n')
write(out, CURATED)
before = read(out)
rc, sout = run([])
ck(rc == 2, '不带生成戳 → 拒绝覆盖并退 2（实际 rc=%s）' % rc)
ck(read(out) == before, '文件**逐字节未变**（人工精修内容零丢失）')
ck('人工精修版' in sout, '输出里明确说明判定为人工精修版')
ck('--force' in sout, '输出里给出 --force 的出路')

print()
print('B) 生成戳语义：盖过戳的文件 = 机械版，允许正常重生成（幂等可走）')
print('=' * 62)
sb = sandbox(3)
out = target_path(sb)
write(out, m.STAMP + '\n# 机械版旧档\n\n## [1] a\n\n---\n')   # 1 条 < 本轮 3 条 → 不触发缩水守卫
rc, _ = run([])
ck(rc == 0, '带生成戳 + 条目更少 → 正常覆盖（rc=%s）' % rc)
txt = read(out)
ck(m.STAMP in txt, '写出的文件带生成戳（可被下次识别为机械版）')
ck(txt.count('## [') == 3, '写出 3 条（实际 %d）' % txt.count('## ['))

print()
print('C) 缩水守卫仍在：带戳但条目变少 → 拒绝')
print('=' * 62)
sb = sandbox(2)
out = target_path(sb)
write(out, m.STAMP + '\n' + ''.join('## [%d] x\n\n---\n' % i for i in (1, 2, 3)))
rc, sout = run([])
ck(rc == 2, '已有 3 条 / 本轮 2 条 → 退 2（实际 rc=%s）' % rc)
ck('缩水' in sout or '疑似抓取残缺' in sout, '输出里点名缩水风险')

print()
print('D) --force 能越过守卫（保留人工逃生通道）')
print('=' * 62)
sb = sandbox(3)
out = target_path(sb)
write(out, CURATED)
rc, _ = run(['--force'])
ck(rc == 0, '--force 覆盖不带戳的文件 → rc=0（实际 %s）' % rc)
ck(m.STAMP in read(out), '覆盖后文件带生成戳')

print()
print('E) 0 条守卫仍在：筛不出目标星球 → 不写文件、不建空壳')
print('=' * 62)
sb = sandbox(3, gid='99999999999999')   # gid 都不匹配
out = target_path(sb)
rc, sout = run([])
ck(rc == 2, '0 条 → 退 2（实际 %s）' % rc)
ck(not os.path.exists(out), '**没有**创建空壳文件（否则 check_integrity 的缺口检测会假绿）')

print()
print('F) 保真度：build_md 必须还原人工精修版的既有约定')
print('=' * 62)
sb = sandbox(2)
d = json.load(open(m.SRC, encoding='utf-8'))
md = m.build_md(d, d, '2026-09-21', '')
ck('<e type="text_bold"' not in md, '富文本标签不再原样 dump 进正文')
ck('【平台富文本加粗段，原文】很理解' in md, '标签被解码成可读原文并独立成段')
ck('download 791' in md, '附件带 download 次数')
ck('2,037,146' in md, '附件带千分位精确字节')
ck('KB' not in md.replace('KB模型', ''), '旧的「(1989KB)」粗粒度形态已消失')
ck('talk（问答）' in md, 'type=q&a 中文化为 talk（问答）')
ck(m.STAMP in md, '正文第 1 行写入生成戳')
ck('…' in m._title_of('啊' * 100), '超长标题用单字符省略号 …')
ck('…' not in m._title_of('短标题'), '短标题不加省略号')

print()
print('G) 散文形态的 review.actual 不影响归档（回归：生成器只读 text/files）')
print('=' * 62)
ck(m._plain_text('普通正文') == '普通正文', '无标签正文原样保留')
ck(m._plain_text('a\n\n\n\nb') == 'a\n\nb', '多余空行被归一化')
ck(m._files_text([]) == '无', '无附件渲染为「无」')
ck(m._files_text([{'name': 'x.pdf', 'size': 1024}]) == 'x.pdf（size 1,024）',
   'download_count 缺失时不硬写 download')

print()
print('=' * 62)
if fails:
    print('RESULT: FAIL %d 项' % len(fails))
    for f in fails:
        print('  · %s' % f)
else:
    print('RESULT: ALL PASS')
print('=' * 62)
sys.exit(1 if fails else 0)
