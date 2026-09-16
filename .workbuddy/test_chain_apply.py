# -*- coding: utf-8 -*-
"""chain_apply 回归测试（2026-09-16 巡检新增）

覆盖 6 组用例，全部在 _test_sandbox 沙箱内运行，不触碰真链：
  B 空壳 review（模板哨兵） -> 应拒（退出码 2）
  C 空壳 review（全空串）   -> 应拒（退出码 2）
  D 正常填写                -> 应通过（退出码 0，status=verified）
  E 占位符 record           -> 应拒（退出码 2）
  F 重复提交                -> 幂等跳过
  末段 真链条数校验         -> 应仍为 48/17

用法：python .workbuddy/test_chain_apply.py
改动 chainlib / chain_apply 后跑一遍，确认「拒得住 + 不误伤」。
"""
import os, sys, json, shutil, subprocess

ROOT = r'C:\Users\gedayou\WorkBuddy\2026-08-14-09-01-12'
WB = os.path.join(ROOT, '.workbuddy')
SB = os.path.join(WB, '_test_sandbox')
CA = os.path.join(WB, 'chain_apply.py')
PY = sys.executable
RID = '2026-09-16-morning'
S = '<<< 必填'


def fresh():
    shutil.rmtree(SB, ignore_errors=True)
    os.makedirs(SB)
    for n in ('forecast_chain.json', 'consensus_chain.json'):
        shutil.copy(os.path.join(WB, n), os.path.join(SB, n))


def run(payload):
    p = os.path.join(SB, 'payload.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    env = dict(os.environ, CHAIN_DIR=SB)
    return subprocess.run([PY, CA, '--payload', p], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', env=env)


def stat(rid, name='forecast_chain.json'):
    with open(os.path.join(SB, name), encoding='utf-8') as f:
        d = json.load(f)
    recs = d.get('records', d) if isinstance(d, dict) else d
    r = next((x for x in recs if x.get('id') == rid), None)
    return (r or {}).get('status'), bool((r or {}).get('review'))


def brief(r):
    keep = ('拒绝', '被拒', '回读', '幂等', '复盘')
    return '\n'.join('   ' + l.strip() for l in r.stdout.splitlines() if any(k in l for k in keep))


print('===== B) 空壳 review（模板哨兵）应被拒 =====')
fresh()
r = run({'forecast': {'review': {'id': RID, 'review': {
    'reviewed_at': '2026-09-16 15:00（复盘）',
    'actual': {'date': '', 'open': 0, 'high': 0, 'low': 0, 'close': 0},
    'direction_verdict': S + '：✅/⚠️/❌ + 说明', 'range_verdict': S + '：x',
    'support_verdict': S + '：x', 'resistance_verdict': S + '：x'}}}})
print('EXIT =', r.returncode, '(期望 2)')
print(brief(r))
print('   链中 status =', stat(RID), '(期望 pending, False)')

print()
print('===== C) 空壳 review（全空串）应被拒 =====')
fresh()
r = run({'forecast': {'review': {'id': RID, 'review': {
    'reviewed_at': 'x', 'actual': {'close': 0}, 'direction_verdict': '',
    'range_verdict': '', 'support_verdict': '', 'resistance_verdict': ''}}}})
print('EXIT =', r.returncode, '(期望 2)')
print('   链中 status =', stat(RID), '(期望 pending, False)')

print()
print('===== D) 正常填写应通过（不误伤）=====')
fresh()
r = run({'forecast': {'review': {'id': RID, 'review': {
    'reviewed_at': '2026-09-16 15:00（复盘）',
    'actual': {'date': '2026-09-16', 'open': 3860, 'high': 3885, 'low': 3850,
               'close': 3878, 'pct_chg': 0.5},
    'direction_verdict': '✅ 命中', 'range_verdict': '⚠️ 部分',
    'support_verdict': '✅ 命中', 'resistance_verdict': '❌ 失效'}}},
    'consensus': {'record': {'id': '2026-09-16-close', 'report_type': 'close',
                             'created_at': '2026-09-16 19:00', 'window': 'x',
                             'consensus': [], 'opposing': []}}})
print('EXIT =', r.returncode, '(期望 0)')
print(brief(r))
print('   forecast status =', stat(RID), '(期望 verified, True)')
print('   consensus status =', stat('2026-09-16-close', 'consensus_chain.json'), '(期望 pending)')

print()
print('===== E) 占位符 record 应被拒 =====')
fresh()
r = run({'forecast': {'record': {'id': '2026-09-16-close',
                                 'direction': S + '：偏多/偏空/震荡',
                                 'range': S + '：下沿~上沿',
                                 'confidence': S + '：高/中/低'}}})
print('EXIT =', r.returncode, '(期望 2)')
print('   链中 status =', stat('2026-09-16-close'), '(期望 None)')

print()
print('===== F) 幂等：重复提交同一 review =====')
fresh()
pl = {'forecast': {'review': {'id': RID, 'review': {
    'reviewed_at': 'x', 'actual': {'close': 3878},
    'direction_verdict': '✅', 'range_verdict': '✅',
    'support_verdict': '✅', 'resistance_verdict': '✅'}}}}
run(pl)
r = run(pl)
print('第二次 EXIT =', r.returncode, '(期望 0)')
print(brief(r))

print()
print('===== 真链校验（应仍 48/17，各 1 pending）=====')
os.environ.pop('CHAIN_DIR', None)
sys.path.insert(0, WB)
import chainlib
for n in ('forecast', 'consensus'):
    recs, _ = chainlib.load(n)
    v = sum(1 for x in recs if x.get('status') == 'verified')
    p = sum(1 for x in recs if x.get('status') == 'pending')
    print(f'   {n}: 总 {len(recs)} | verified {v} | pending {p}')

shutil.rmtree(SB, ignore_errors=True)
print('\n(沙箱已清理)')
