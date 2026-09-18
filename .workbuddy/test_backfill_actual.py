# -*- coding: utf-8 -*-
"""P1-4 回归测试：backfill_actual_data 的退出码 / 「该补却补不了」/ 映射表过期自检。

背景：本脚本是**一次性历史回填**，用一张写死的 `NO_ACTUAL_TARGET`（记录 id → target 日期）
把缺失的 actual 补上。它的键是**记录 id**，而 id 会被 `normalize_chain.py` 规范化改名
（真实案例：原 `2026-09-01-close` 已改名 `2026-08-31-close`）。
键一旦失效就是**静默空操作** —— 与 normalize_chain 那个「固定映射表不幂等」属同一类隐患。
本测试钉住三件事：
  · 有回填 → 返回 0 且原子落盘
  · 「该补却补不了」（date 超出只读快照范围）→ 返回 2 且**全量列出明细**
  · 映射表键未命中任何记录 → 返回 2 且明说是哪个键过期（绝不静默）

用法：$PY .workbuddy/test_backfill_actual.py（全程在 tempfile 内跑，不碰真实链）
"""
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('bf', os.path.join(HERE, 'backfill_actual_data.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

SANDBOX = tempfile.mkdtemp(prefix='p14_bf_')
m.CHAIN = os.path.join(SANDBOX, 'forecast_chain.json')
ORIG_MAP = dict(m.NO_ACTUAL_TARGET)

fails = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


def write(chain):
    with io.open(m.CHAIN, 'w', encoding='utf-8') as f:
        json.dump(chain, f, ensure_ascii=False, indent=2)


def read():
    return json.load(io.open(m.CHAIN, encoding='utf-8'))


def md5():
    return hashlib.md5(io.open(m.CHAIN, 'rb').read()).hexdigest()


def run():
    m.sys.argv = ['backfill_actual_data.py']
    return m.main()


def rec(rid, review=None):
    r = {'id': rid, 'status': 'verified'}
    if review is not None:
        r['review'] = review
    return r


print('1) 正常回填：无 actual 且在映射表内 → 补整份 OHLC 并落盘')
m.NO_ACTUAL_TARGET = {'2026-08-24-close': '2026-08-25'}
write([rec('2026-08-24-close', {'foreseeable': 'x'})])
rc = run()
a = read()[0]['review']['actual']
ck(rc == 0, '有回填时返回 0')
ck(a['date'] == '2026-08-25' and a['close'] == 3889.44, 'OHLC 按只读快照正确回填')
ck(not os.path.exists(m.CHAIN + '.tmp'), '无遗留 .tmp 文件（原子写完成）')

print('2) 幂等：再跑一次应无事可做 → 2，且不写盘')
h0 = md5()
rc = run()
ck(rc == 2, '已回填完毕再跑返回 2')
ck(md5() == h0, 'md5 未变（未产生无谓改动）')

print('3) 映射表过期键（复现 2026-09-01-close → 2026-08-31-close 改名后果）→ 必须报 WARN')
m.NO_ACTUAL_TARGET = {'2026-09-01-close': '2026-09-01'}   # 链上已无此 id
write([rec('2026-08-31-close', {'foreseeable': 'x'})])
h0 = md5()
rc = run()
ck(rc == 2, '键未命中任何记录时返回 2（旧实现是完全静默的空操作）')
ck(md5() == h0, '过期键场景不写盘')
m.NO_ACTUAL_TARGET = ORIG_MAP
ck('2026-09-01-close' not in ORIG_MAP,
   '★ 正式映射表里那个失效键已修正（否则每天都是静默空操作）')

print('4) actual 缺 pct_chg 且 date 在快照内 → 补上并返回 0')
m.NO_ACTUAL_TARGET = {}
write([rec('2026-08-27-close',
           {'actual': {'date': '2026-09-02', 'open': 1.0, 'close': 2.0,
                       'high': 2.1, 'low': 0.9, 'pct_chg': None}})])
rc = run()
ck(rc == 0, '补齐 pct_chg 时返回 0')
ck(read()[0]['review']['actual']['pct_chg'] == m.pct_of('2026-09-02'),
   'pct_chg 按前一交易日收盘正确计算')

print('5) 「该补却补不了」：date 超出只读快照范围 → 返回 2 并列出明细')
write([rec('2026-09-17-close',
           {'actual': {'date': '2026-09-18', 'open': 1.0, 'close': 2.0,
                       'high': 2.1, 'low': 0.9, 'pct_chg': None}})])
h0 = md5()
rc = run()
ck(rc == 2, '超出快照范围时返回 2（不再静默跳过）')
ck(md5() == h0, '补不了就不写盘')

print('6) 链文件缺失 / JSON 损坏 → 1（不尝试重建）')
os.remove(m.CHAIN)
ck(run() == 1, '链不存在时返回 1')
with io.open(m.CHAIN, 'w', encoding='utf-8') as f:
    f.write('[broken')
ck(run() == 1, 'JSON 解析失败时返回 1')

print('7) 只读快照边界：KLINE 首日无 prev_close → pct_of 返回 None 而非编造')
ck(m.pct_of(m.DATES[0]) is None, '首个交易日无前收，如实返回 None')
ck(m.pct_of(m.DATES[1]) is not None, '第二个交易日起才有 pct_chg')

print()
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
sys.exit(1 if fails else 0)
