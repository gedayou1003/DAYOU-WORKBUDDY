# -*- coding: utf-8 -*-
"""P1-4 回归测试：normalize_chain 的幂等性 / 冲突守卫 / dry-run 默认。

背景（真实事故）：本脚本原用固定改名表 ID_RENAME = {A:B, B:C, C:D}，**不幂等**。
2026-09-18 二次运行把它整体位移一步，把一条本已正确命名的 `2026-08-28-close`
（created_at=08-28）改成 `2026-08-27-close`，与已存在的同名记录**撞车产生重复 id**。
本测试专门证明：
  · 已是正确命名的记录**绝不**被再改一次（幂等）
  · 真冲突时**报 ERROR 且一个字节都不写**
`md5 不变` 是本测试的核心断言 —— 防的就是「报错却已经把文件改坏」。

用法：$PY .workbuddy/test_normalize_chain.py（全程在 tempfile 内跑，不碰真实链）
"""
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('nz', os.path.join(HERE, 'normalize_chain.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

SANDBOX = tempfile.mkdtemp(prefix='p14_nz_')
m.CHAIN = os.path.join(SANDBOX, 'forecast_chain.json')

fails = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


def write(chain):
    with io.open(m.CHAIN, 'w', encoding='utf-8') as f:
        json.dump(chain, f, ensure_ascii=False, indent=2)


def md5():
    return hashlib.md5(io.open(m.CHAIN, 'rb').read()).hexdigest()


def rec(rid, created_at, target='2026-08-31 全天（周一）', review=None):
    r = {'id': rid, 'created_at': created_at, 'target': target, 'status': 'verified'}
    if review is not None:
        r['review'] = review
    return r


def run(*args):
    m.sys.argv = ['normalize_chain.py'] + list(args)
    return m.main()


print('1) 不变量成立 → 0 处改动、不写盘')
write([rec('2026-08-27-close', '2026-08-27 16:20'),
       rec('2026-08-28-close', '2026-08-28 15:46')])
h0 = md5()
rc = run('--apply')
ck(rc == 2, '无违反时不落盘，返回 2（WARN=无事可做）')
ck(md5() == h0, 'md5 未变（未产生无谓改动）')

print('2) 回归断言：已是正确命名的记录绝不被再改一次（原 bug 的正面复现）')
# created 08-28、id 08-28-close —— 旧表会把它错改成 08-27-close（进而撞车）
after = json.load(io.open(m.CHAIN, encoding='utf-8'))
ck([r['id'] for r in after] == ['2026-08-27-close', '2026-08-28-close'],
   '「2026-08-28-close / created 08-28」保持原 id 不动（旧实现在此制造重复 id）')

print('3) 单条真违反、无冲突 → dry-run 只报告不落盘；--apply 才改')
write([rec('2026-08-27-close', '2026-08-27 16:20'),
       rec('2026-08-29-close', '2026-08-28 15:46')])   # id 日期 08-29 ≠ created 08-28
h0 = md5()
rc = run()
ck(rc == 2, 'dry-run 返回 2（有待改动但未落盘）')
ck(md5() == h0, 'dry-run 未写盘')
rc = run('--apply')
ck(rc == 0, '--apply 有改动落盘，返回 0')
ids = [r['id'] for r in json.load(io.open(m.CHAIN, encoding='utf-8'))]
ck('2026-08-28-close' in ids and '2026-08-29-close' not in ids,
   'id 已按 created_at 修正为 2026-08-28-close')

print('4) 幂等：修正后再跑 --apply 应回到「无事可做」')
rc = run('--apply')
ck(rc == 2, '二次 --apply 返回 2（改动已收敛，不反复位移）')

print('5) 冲突守卫（复现 9/18 事故形态）→ ERROR 且一字节不写')
write([rec('2026-08-27-close', '2026-08-27 16:20'),
       rec('2026-08-28-close', '2026-08-27 15:46')])   # 目标 08-27-close 已被占用
h0 = md5()
rc = run('--apply')
ck(rc == 1, '目标 id 冲突时返回 1（旧实现会直接写盘造成重复 id）')
ck(md5() == h0, '★ 冲突时文件 md5 未变 —— 报错绝不等于已经改坏')
ck(len([r for r in json.load(io.open(m.CHAIN, encoding='utf-8'))
        if r['id'] == '2026-08-27-close']) == 1, '未产生重复 id')

print('6) 链文件缺失 → 1')
os.remove(m.CHAIN)
ck(run() == 1, '链不存在时返回 1')

print('7) 链 JSON 损坏 → 1（不尝试重建）')
with io.open(m.CHAIN, 'w', encoding='utf-8') as f:
    f.write('{"broken": ')
ck(run() == 1, 'JSON 解析失败时返回 1')

print('8) actual 字段迁移：pct -> pct_chg')
write([rec('2026-08-27-close', '2026-08-27 16:20',
           review={'actual': {'date': '2026-08-28', 'open': 1.0, 'pct': 0.42}})])
rc = run('--apply')
a = json.load(io.open(m.CHAIN, encoding='utf-8'))[0]['review']['actual']
ck(rc == 0, '有字段迁移时返回 0')
ck(a.get('pct_chg') == 0.42 and 'pct' not in a, 'pct 已迁移为 pct_chg，数值不变')

print('9) 缺 actual.date → 从 target 提取补齐')
write([rec('2026-08-27-close', '2026-08-27 16:20',
           target='2026-09-01 全天（周二）',
           review={'actual': {'open': 1.0, 'pct_chg': 0.42}})])
rc = run('--apply')
a = json.load(io.open(m.CHAIN, encoding='utf-8'))[0]['review']['actual']
ck(rc == 0 and a.get('date') == '2026-09-01', 'date 已按 target 补齐为 2026-09-01')

print('10) 缺 created_at 时不误改（无法判定不变量 → 不动）')
write([{'id': '2026-08-28-close', 'target': '2026-08-31'}])
h0 = md5()
rc = run('--apply')
ck(rc == 2 and md5() == h0, '无 created_at 时保守不动，返回 2')

print()
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
sys.exit(1 if fails else 0)
