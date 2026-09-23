# -*- coding: utf-8 -*-
"""P1-1 变异测试：check_integrity 的三级退出码是否真的会按级别变色。

思路（照 assertion-gate-hardening 的方法）：不满足于「改动后仍报绿」，
而是在沙箱里**主动注入** ERROR / WARN / 设计使然三类情形，看闸门是否分别
给出 1 / 2 / 0 —— 一个永远报绿的校验器等于没有校验器。

2026-09-23 补 J~P（配合【1】口径修 + 【2】已知缺口白名单）：
  该轮给闸门做了两处**放宽**（未跑晨报档不再要求归档；9/22 真缺口登记白名单）。
  放宽动作必须成对验证，否则等于悄悄打开后门：
    · **放宽确实生效**：J（无晨报档 → 0）、M（白名单内 → 0）
    · **闸门仍咬得住**：K（有晨报档缺归档 → 1）、L（白名单外缺口 → 1）、
      N（--strict 忽略白名单 → 1）
    · **白名单自身被检查**：O（空原因 → ERROR）、P（条目失效 → WARN）
  少了任何一侧，这次改动就只是"变绿了"，而不是"判得对了"。

用法：$PY .workbuddy/test_check_integrity_neg.py（沙箱内自建链与归档，不碰真链）
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
TODAY = datetime.date.today().isoformat()
RID = TODAY + '-morning'

# 档位后缀 → 报告文件名里的中文档位段（与 check_integrity.TIER_BY_SUFFIX 同口径，
# 这里复制一份是为了让沙箱**自洽**：链上有的记录，产物也落下来，否则【7】会如实报缺口，
# 把"A~I 在测别的检查"变成"A~I 全被【7】带红"。
TIER_ZH = {'morning': '晨报', 'morning-v2': '晨报', 'noon': '午间', 'afternoon': '午间',
           'close': '收盘', 'intraday': '盘中', '1100': '盘中', '1340': '盘中'}


def prev_trading_day(day=None):
    """TODAY 之前最近的一个交易日（用于造「有交易日但链上零记录」的真缺口）"""
    d = datetime.date.fromisoformat(day or TODAY) - datetime.timedelta(days=1)
    while d.weekday() >= 5:
        d -= datetime.timedelta(days=1)
    return d.isoformat()


def patch_whitelist(sb, name, body):
    """把沙箱副本里的某个白名单字典**整体换掉**（用于验证白名单自检本身有效）。

    用正则匹配 `NAME = {...}` 而不是替换字面量全文 —— 后者会在任何人改写原因文案后失效，
    而这类"测试跟着数据腐烂"正是 run_tests.py 建立时要解决的问题。
    """
    p = os.path.join(sb, '.workbuddy', 'check_integrity.py')
    t = open(p, encoding='utf-8').read()
    new, n = re.subn(r'%s\s*=\s*\{[^}]*\}' % name, '%s = %s' % (name, body),
                     t, count=1, flags=re.S)
    assert n == 1, '白名单 %s 未找到（改名了？测试需同步）' % name
    open(p, 'w', encoding='utf-8').write(new)


def build(tj_archive=True, forecast=None, consensus=None, report=True, skip_dates=()):
    """搭沙箱。

    report=False  → 一份报告都不落盘（用于验证【7】的缺产物断言）
    skip_dates    → 只对这些日期不落报告（用于验证「ARTIFACT_SINCE 之前算历史例外」）
    """
    sb = tempfile.mkdtemp(prefix='p11_')
    dot = os.path.join(sb, '.workbuddy')
    os.makedirs(dot)
    os.makedirs(os.path.join(sb, 'outputs'))
    shutil.copyfile(os.path.join(HERE, 'check_integrity.py'),
                    os.path.join(dot, 'check_integrity.py'))
    if tj_archive:
        open(os.path.join(sb, 'outputs', 'DRAGON_BALL_原始记录_%s.md' % TODAY),
             'w', encoding='utf-8').write('# 归档\n## [1] 内容\n')
    # 【7】链记录 → 报告产物：按 id 后缀映射中文档位落报告，让沙箱自洽（见 TIER_ZH 说明）。
    if report:
        for r in (forecast or []):
            rid = r.get('id', '')
            m = re.match(r'^(\d{4}-\d{2}-\d{2})-(.+)$', rid)
            if m and m.group(2) in TIER_ZH and m.group(1) not in skip_dates:
                open(os.path.join(sb, 'outputs',
                                  '作战报告_%s_%s.md' % (TIER_ZH[m.group(2)], m.group(1))),
                     'w', encoding='utf-8').write('# 报告\n')
    with open(os.path.join(dot, 'forecast_chain.json'), 'w', encoding='utf-8') as f:
        json.dump(forecast, f, ensure_ascii=False)
    with open(os.path.join(dot, 'consensus_chain.json'), 'w', encoding='utf-8') as f:
        json.dump(consensus if consensus is not None else [{'id': RID}], f, ensure_ascii=False)
    return sb


def run(sb, from_date=None, extra=()):
    cmd = [PY, os.path.join(sb, '.workbuddy', 'check_integrity.py'),
           '--from', from_date or TODAY] + list(extra)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
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

print('H) 注入 ERROR（链有记录、报告文件没落盘）→ 1')
sb = build(report=False, forecast=[{'id': RID, 'review': {'actual': FULL}}])
rc, out = run(sb)
ck(rc == 1, '缺报告产物时退出码 1（实测 %s）' % rc)
ck('缺报告' in out, '【7】报出「链记录 → 报告产物」缺口')
ck('产物缺口 1' in out, '汇总里标出产物缺口 1')
shutil.rmtree(sb, ignore_errors=True)

print('I) 但命名规范生效日之前的缺口只算历史例外 → 0')
# 2026-08-21 远早于 ARTIFACT_SINCE（2026-08-27），当时报告名不同 —— 不该判红
sb = build(forecast=[{'id': '2026-08-21-morning', 'review': {'actual': FULL},
                      'status': 'verified'},
                     {'id': RID, 'review': {'actual': FULL}}],
           skip_dates=('2026-08-21',))
rc, out = run(sb)
ck(rc == 0, 'ARTIFACT_SINCE 之前的缺产物不判红（实测 %s）' % rc)
ck('历史例外' in out and '作战报告_晨报_2026-08-21.md' not in out,
   '默认只汇总不逐条展开（--verbose 才列文件名）')
shutil.rmtree(sb, ignore_errors=True)

print()
print('--- 2026-09-23 新增：【1】口径修 + 【2】已知缺口白名单 ---')
NOON = TODAY + '-noon'
PREV = prev_trading_day()

print('J) 只跑午间档（该日无晨报档）→ 归档按设计不产出，**不判红** → 0')
sb = build(tj_archive=False, forecast=[{'id': NOON, 'review': {'actual': FULL}}])
rc, out = run(sb)
ck(rc == 0, '未跑晨报档的日子缺归档不判红（实测 %s）——改前这里必然误报 ERROR' % rc)
ck('未跑晨报档' in out, '明说「按设计不产出」而非静默跳过（可审计，不是放水）')
shutil.rmtree(sb, ignore_errors=True)

print('K) 同日**有**晨报档却缺归档 → 仍判红 → 1（证明 J 的放宽没有削弱闸门）')
sb = build(tj_archive=False,
           forecast=[{'id': RID, 'review': {'actual': FULL}},
                     {'id': NOON, 'review': {'actual': FULL}}])
rc, out = run(sb)
ck(rc == 1, '有晨报档时缺归档仍报 ERROR（实测 %s）' % rc)
ck('该日跑过晨报档' in out, '报错信息点名「跑过晨报档 → 应有归档」')
shutil.rmtree(sb, ignore_errors=True)

print('L) 白名单外的「有交易日但链上零记录」→ 1')
# 先把沙箱白名单清空再断言：否则本用例会依赖**产品白名单的实际内容**——
# 而 PREV 恰好在某些日子就是真缺口本身（首次跑本用例时 PREV == 2026-09-22），
# 于是"白名单外的洞"变成了"白名单内的洞"，用例静默失效。
# 测试造洞必须自己控制前提，不能把前提寄在待测数据上。
sb = build(forecast=[{'id': RID, 'review': {'actual': FULL}}])
patch_whitelist(sb, 'KNOWN_FC_GAPS', '{}')
rc, out = run(sb, from_date=PREV)
ck(rc == 1, '%s 无记录时退出码 1（实测 %s）' % (PREV, rc))
ck('无预判记录' in out, '报出档位缺口')
shutil.rmtree(sb, ignore_errors=True)

print('M) 同一缺口登记进白名单（带原因）→ 0，但缺口仍逐条打印（不静默）')
sb = build(forecast=[{'id': RID, 'review': {'actual': FULL}}])
patch_whitelist(sb, 'KNOWN_FC_GAPS', "{'%s': '测试用原因：该日未触发'}" % PREV)
rc, out = run(sb, from_date=PREV)
ck(rc == 0, '白名单内缺口不计 ERROR（实测 %s）' % rc)
ck('已知缺口 1 条' in out and PREV in out, '白名单命中仍打印日期+原因（留痕，非静默）')

print('N) 同一沙箱加 --strict → 忽略白名单，洞立刻复现 → 1')
rc, out = run(sb, from_date=PREV, extra=('--strict',))
ck(rc == 1, '--strict 下白名单失效，缺口复现为 ERROR（实测 %s）' % rc)
ck('--strict' in out, '汇总行标注本次为 --strict 模式')

print('O) 白名单条目**没有原因** → 判 ERROR（空原因=无声放水）')
patch_whitelist(sb, 'KNOWN_FC_GAPS', "{'%s': ''}" % PREV)
rc, out = run(sb, from_date=PREV)
ck(rc == 1, '空原因白名单条目判 ERROR（实测 %s）' % rc)
ck('没有原因' in out, '报出「无声放水」并点名日期')
shutil.rmtree(sb, ignore_errors=True)

print('P) 白名单条目**已失效**（该日其实有记录）→ WARN 提示清理 → 2')
sb = build(forecast=[{'id': RID, 'review': {'actual': FULL}}])
patch_whitelist(sb, 'KNOWN_FC_GAPS', "{'%s': '测试用：这一天其实有记录，条目应被清理'}" % TODAY)
rc, out = run(sb)
ck(rc == 2, '失效白名单条目报 WARN（实测 %s）' % rc)
ck('已不再成立' in out, '提示清理（白名单必须能缩小）')
shutil.rmtree(sb, ignore_errors=True)

print()
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
sys.exit(1 if fails else 0)
