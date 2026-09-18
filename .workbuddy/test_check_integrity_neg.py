# -*- coding: utf-8 -*-
"""P1-1 变异测试：check_integrity 的三级退出码是否真的会按级别变色。

思路（照 assertion-gate-hardening 的方法）：不满足于「改动后仍报绿」，
而是在沙箱里**主动注入** ERROR / WARN / 设计使然三类情形，看闸门是否分别
给出 1 / 2 / 0 —— 一个永远报绿的校验器等于没有校验器。

用法：$PY .workbuddy/test_check_integrity_neg.py（沙箱内自建链与归档，不碰真链）
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
TODAY = datetime.date.today().isoformat()
RID = TODAY + '-morning'


def build(tj_archive=True, forecast=None, consensus=None):
    sb = tempfile.mkdtemp(prefix='p11_')
    dot = os.path.join(sb, '.workbuddy')
    os.makedirs(dot)
    os.makedirs(os.path.join(sb, 'outputs'))
    shutil.copyfile(os.path.join(HERE, 'check_integrity.py'),
                    os.path.join(dot, 'check_integrity.py'))
    if tj_archive:
        open(os.path.join(sb, 'outputs', 'DRAGON_BALL_原始记录_%s.md' % TODAY),
             'w', encoding='utf-8').write('# 归档\n## [1] 内容\n')
    with open(os.path.join(dot, 'forecast_chain.json'), 'w', encoding='utf-8') as f:
        json.dump(forecast, f, ensure_ascii=False)
    with open(os.path.join(dot, 'consensus_chain.json'), 'w', encoding='utf-8') as f:
        json.dump(consensus if consensus is not None else [{'id': RID}], f, ensure_ascii=False)
    return sb


def run(sb):
    r = subprocess.run([PY, os.path.join(sb, '.workbuddy', 'check_integrity.py'),
                        '--from', TODAY],
                       capture_output=True, text=True, encoding='utf-8',
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    return r.returncode, (r.stdout or '')


FULL = {'date': TODAY, 'open': 1, 'high': 2, 'low': 0.5, 'close': 1.5, 'pct_chg': 0.1}
ok_static = {'phase': '晨报档·开盘前静态初验（09:20，A 股尚未开盘）',
             'reviewed_at': '2026-09-18 09:20（晨报档·开盘前静态初验）',
             'direction_verdict': '⚠️ 部分', 'actual': {'date': TODAY, 'note': '未开盘，O/H/L/C 不写入'}}

fails = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


print('A) 基线：干净数据 → 0')
sb = build(forecast=[{'id': RID, 'review': {'direction_verdict': '✅', 'actual': FULL}}])
rc, out = run(sb)
ck(rc == 0, '基线退出码 0（实测 %s）' % rc)
shutil.rmtree(sb, ignore_errors=True)

print('B) 注入 ERROR（归档缺失）→ 1')
sb = build(tj_archive=False, forecast=[{'id': RID, 'review': {'actual': FULL}}])
rc, out = run(sb)
ck(rc == 1, '缺归档时退出码 1（实测 %s）' % rc)
ck('ERROR 1' in out, '汇总里标出 ERROR 1')
shutil.rmtree(sb, ignore_errors=True)

print('C) 注入 ERROR（链停更 / 漏复盘）→ 1')
sb = build(forecast=[{'id': RID, 'review': {'actual': FULL}},
                     {'id': '2026-01-02-morning', 'status': 'pending'},
                     {'id': '2026-01-03-morning', 'status': 'pending'}])
rc, out = run(sb)
ck(rc == 1, 'pending>1 时退出码 1（实测 %s）' % rc)
shutil.rmtree(sb, ignore_errors=True)

print('D) 注入 WARN（非静态初验的 actual 缺字段）→ 2')
sb = build(forecast=[{'id': RID, 'review': {'direction_verdict': '✅',
                                            'actual': {'date': TODAY, 'close': 1.5}}}])
rc, out = run(sb)
ck(rc == 2, 'actual 缺 OHLC 时退出码 2（实测 %s）' % rc)
ck('WARN 1' in out, '汇总里标出 WARN 1')
shutil.rmtree(sb, ignore_errors=True)

print('E) 设计使然（静态初验不写 O/H/L/C）→ 0，不报噪声')
sb = build(forecast=[{'id': RID, 'review': ok_static}])
rc, out = run(sb)
ck(rc == 0, '静态初验不写 OHLC 时退出码 0（实测 %s）——这就是改前每期固定刷的那条告警' % rc)
ck('静态初验样本 1 条' in out, '改判为 INFO 并说明原因')
shutil.rmtree(sb, ignore_errors=True)

print('F) 历史散文格式 actual（白名单）→ 0')
sb = build(forecast=[{'id': '2026-09-11-morning',
                      'review': {'actual': '9/11 全天：O=3910.92 H=3912.32 L=3852.03 C=3888.11'},
                      'status': 'verified'},
                     {'id': RID, 'review': {'actual': FULL}}])
rc, out = run(sb)
ck(rc == 0, '白名单内历史例外退出码 0（实测 %s）' % rc)
shutil.rmtree(sb, ignore_errors=True)

print('G) 白名单外的字符串 actual → 2（补上改前的静默盲区）')
sb = build(forecast=[{'id': RID, 'review': {'actual': '全文一句话，没有 O/H/L/C 结构'}}])
rc, out = run(sb)
ck(rc == 2, '非白名单字符串 actual 退出码 2（改前此情形**完全不校验**）')
ck('actual 为字符串' in out, '明确报出「无法机器校验」')
shutil.rmtree(sb, ignore_errors=True)

print()
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
sys.exit(1 if fails else 0)
