# -*- coding: utf-8 -*-
"""check_layout 第 8 类检查（本期变化·基期对账）的变异测试。

背景（2026-09-18 审计 P0-1）
----------------------------
9/18 晨报把「本期变化」的方向基期写成了**上上期**（56.2% = 9/17 晨报 n=48），
真正的基期是 9/17 收盘档 n=49 → 57.1%；而同句里区间的基期是对的 —— **同句两套基期**，
肉眼复核发现不了。第 8 类检查就是为拦住这类手写数字错。

光加检查不够：**必须证明它真的会红**（见《脚本地图》教训 3）。
本测试用真实链数据构造两份报告：一份基期正确、一份故意用「上上期」，
要求前者不报、后者报 ERROR。

数据驱动、不依赖具体日期，任何一天跑都成立。
用法：$PY .workbuddy/test_check_layout_basis.py
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

spec = importlib.util.spec_from_file_location('cl', os.path.join(HERE, 'check_layout.py'))
cl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cl)

import chainlib  # noqa: E402

fails = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


recs, _ = chainlib.load('forecast')
verified = [r for r in recs if r.get('status') == 'verified']
if len(verified) < 3:
    print('链上 verified 不足 3 条，无法构造「上上期」，跳过')
    sys.exit(0)

newest = verified[-1]['id']
second = verified[-2]['id']
cur = chainlib.bias_stats('forecast')
prev = chainlib.bias_stats('forecast', exclude_ids={newest})
older = chainlib.bias_stats('forecast', exclude_ids={newest, second})

n, n_prev = cur['periods'], prev['periods']
now_v = cur['dims']['direction']['pure']
base_ok = prev['dims']['direction']['pure']
base_bad = older['dims']['direction']['pure']
print('链实测：本期 n=%d 方向 %.1f%% ｜ 上一期 n=%d %.1f%% ｜ 上上期 %.1f%%'
      % (n, now_v, n_prev, base_ok, base_bad))
print('       最新样本 id = %s，其上一条 = %s' % (newest, second))


def short_id(rid):
    """2026-09-17-close → 9/17-close（报告里的写法）"""
    y, m, d, rest = rid.split('-', 3)
    return '%d/%d-%s' % (int(m), int(d), rest)


def make_report(base_value):
    today = datetime.date.today().isoformat()
    return ('# 作战报告 · 晨报（变异测试样本）\n\n'
            '### 二、偏差观察统计表（%d 期）\n\n'
            '| 维度 | 命中 | 部分 | 失效 | 未判定 | 纯命中率 | 备注 |\n'
            '|---|---|---|---|---|---|---|\n'
            '| 方向 | 1 | 1 | 1 | 0 | **%.1f%%** | n=%d |\n\n'
            '**本期变化**：新增 `%s` 样本，样本 %d→%d 期。方向 ⚠️ +1（%.1f%%→**%.1f%%**）。\n'
            % (n, now_v, n, short_id(newest), n_prev, n, base_value, now_v))


def run_with(text):
    sb = tempfile.mkdtemp(prefix='layout_basis_')
    out = os.path.join(sb, 'outputs')
    os.makedirs(out)
    today = datetime.date.today().isoformat()
    p = os.path.join(out, '作战报告_晨报_%s.md' % today)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)
    saved = cl.ROOT
    cl.ROOT = sb                      # 只为让 _superseded_same_date 在沙箱里找同日报
    try:
        return cl.check(p)
    finally:
        cl.ROOT = saved
        shutil.rmtree(sb, ignore_errors=True)


print('\n1) 基期正确 → 不应报基期相关 ERROR')
res_ok = run_with(make_report(base_ok))
basis_err_ok = [e for e in res_ok['errors'] if '基期' in e]
ck(not basis_err_ok, '正确基期（%.1f%%）未被误报：%s' % (base_ok, basis_err_ok or '无'))
ck(any('基期对账' in i for i in res_ok.get('infos', [])), 'INFO 显示已核对维度数')

print('2) 基期取成上上期（复现 9/18 的真实错误）→ 必须报 ERROR')
res_bad = run_with(make_report(base_bad))
basis_err_bad = [e for e in res_bad['errors'] if '基期' in e]
ck(bool(basis_err_bad), '错误基期（%.1f%%，应为 %.1f%%）被拦下：%s'
   % (base_bad, base_ok, basis_err_bad or '未拦下！检查失效'))
if basis_err_bad:
    print('        报错原文：%s' % basis_err_bad[0])

print('3) 统计表本身写错（表 ≠ 链实测）→ 也要报 ERROR')
bad_table = make_report(base_ok).replace('**%.1f%%** | n=%d' % (now_v, n),
                                        '**%.1f%%** | n=%d' % (now_v + 3.3, n))
res_tbl = run_with(bad_table)
ck(any('偏差统计表' in e for e in res_tbl['errors']), '统计表与链不符被拦下')

print('4) 链文件读不动 → 「偏差期数一致性」必须报 WARN，不许静默跳过（2026-09-23 加固）')
# 改前：_verified_count() 读不到链就返回 None，而调用点写的是 `chain_n is not None` ——
# 于是**链读不动时这条检查直接不执行**，check_layout 照样输出「无 WARN」通过。
# 现在的判据：WARN 里必须出现「未执行」字样，且带上原因（检查没跑成 ≠ 检查通过）。
_saved_fc = cl.FORECAST
_sb = tempfile.mkdtemp(prefix='layout_chain_')
try:
    cl.FORECAST = os.path.join(_sb, 'forecast_chain.json')
    res_missing = run_with(make_report(base_ok))
    miss_w = [w for w in res_missing['warns'] if '未执行' in w]
    ck(bool(miss_w), '链文件不存在 → WARN 明示「未执行」：%s' % (miss_w or '未报 ← 仍是假绿'))

    with open(cl.FORECAST, 'w', encoding='utf-8') as f:
        f.write('{ 这不是合法 JSON')
    res_broken = run_with(make_report(base_ok))
    brk_w = [w for w in res_broken['warns'] if '未执行' in w and '读不动' in w]
    ck(bool(brk_w), '链文件损坏 → WARN 带上具体原因：%s' % (brk_w or '未报'))

    # 反向：链可读时不许出现这条 WARN（防「加了检查就永久报红」）
    cl.FORECAST = _saved_fc
    res_ok_chain = run_with(make_report(base_ok))
    ck(not [w for w in res_ok_chain['warns'] if '未执行' in w],
       '链可读 → 不报「未执行」（新判据没有变成永久噪声）')
finally:
    cl.FORECAST = _saved_fc
    shutil.rmtree(_sb, ignore_errors=True)

print()
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
sys.exit(1 if fails else 0)
