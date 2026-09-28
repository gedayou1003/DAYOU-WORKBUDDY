# -*- coding: utf-8 -*-
"""
作战报告 · 晨报 一键编排（Phase data / finish）

把「跑晨报」里可机械化的步骤收拢成两条命令，省掉逐个 Bash 来回 + 事后返工：
  · data   阶段一（数据采集）：抓取 + OHLC + 技术指标 + 引擎B + 行业榜，≤2 并发一次跑完
  · finish 阶段二（产物收口）：变盘分 + 链落盘 + 归档 + SVG + HTML + 三校验 + (可选 git)

两步之间是**智能体分析**（读数据 → 建 payload → 写报告 md），由 `plan` 子命令打印完整流程速查。

用法：
  $PY .workbuddy/run_morning_report.py data
  $PY .workbuddy/run_morning_report.py finish --payload <json> --md <md> --vol "v1,v2,v3,v4,v5" [--git]
  $PY .workbuddy/run_morning_report.py plan

约定（跨设备通用）：
  · 本脚本用 sys.executable（即启动它的 $PY）跑所有子进程，不写死解释器路径
  · 技能目录 ~/.workbuddy/skills/chan-signal__skillhub 自动展开
  · 工作区脚本用相对路径 .workbuddy/xxx.py，cwd 固定为工作区根
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---- 控制台编码加固（cp936 下 print emoji 会崩，降级为 ASCII 符号）----
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except Exception:
        pass
_OK, _FAIL, _WARN, _INFO = '[OK]', '[X] ', '[~] ', '[i] '
if sys.stdout.encoding and ('utf-8' in sys.stdout.encoding.lower() or 'utf8' in sys.stdout.encoding.lower()):
    _OK, _FAIL, _WARN, _INFO = '[✅]', '[❌]', '[⚠️]', '[ℹ️]'

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
SKILL_DIR = os.path.expanduser('~/.workbuddy/skills/chan-signal__skillhub')
CODE = '000001'          # 上证综指（本报告唯一标的）
TODAY = lambda: datetime.datetime.now().strftime('%Y-%m-%d')


def _log_path(phase, step, day=None):
    day = day or TODAY()
    return os.path.join(HERE, '_morning_%s_%s_%s.log' % (day, phase, step))


def _run(cmd, cwd=None, log=None, timeout=1200):
    """跑一条子进程，stdout+stderr 合并写 log；返回 (rc, 输出尾部)。"""
    cwd = cwd or ROOT
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout)
        out = p.stdout.decode('utf-8', errors='replace')
        rc = p.returncode
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b'').decode('utf-8', errors='replace') + '\n[TIMEOUT %ds]' % timeout
        rc = -1
    except Exception as e:
        out = 'subprocess 异常：%s: %s' % (type(e).__name__, e)
        rc = -1
    dt = time.time() - t0
    if log:
        try:
            with open(log, 'w', encoding='utf-8') as f:
                f.write('$ %s\n(cwd=%s, %.1fs, rc=%d)\n%s\n' % (' '.join(cmd), cwd, dt, rc, out))
        except Exception:
            pass
    return rc, out, dt


def _tail(out, n=400):
    lines = [l for l in out.strip().splitlines() if l.strip()]
    return lines[-n:]


# ======================================================================
# 阶段一：数据采集（≤2 并发）
# ======================================================================
DATA_STEPS = [
    # (step, cwd, cmd, critical)
    ('fetch',      None,      ['fetch_zsxq.py'],                            True),
    ('ohlc',       None,      ['get_daily_ohlc.py', CODE, '1', '--slot', 'morning'], True),
    ('tech',       None,      ['calc_tech.py', '--code', CODE],             False),
    ('tech_multi', None,      ['calc_tech_multi.py', '--code', 'sh' + CODE], False),
    ('engineB',    SKILL_DIR, ['run_000001_chansignal.py', '--code', CODE], False),
    ('industry_rt', None,     ['scan_sw_realtime.py'],                      False),
    ('industry_ths', None,    ['scan_ths.py'],                              False),
]


def cmd_data(args):
    day = args.date or TODAY()
    print('===== 晨报·阶段一 数据采集（%s）=====' % day)
    print('并发上限 2；fetch / ohlc 为关键步（失败在末尾汇总报错），其余失败仅告警。\n')

    def _one(step):
        name, cwd, argv, crit = step
        if cwd is None:
            full = [sys.executable, os.path.join(ROOT, '.workbuddy', argv[0])] + argv[1:]
        else:
            full = [sys.executable, argv[0]] + argv[1:]
        rc, out, dt = _run(full, cwd=cwd, log=_log_path('data', name, day))
        return name, rc, out, dt, crit

    results = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(_one, s): s[0] for s in DATA_STEPS}
        for f in as_completed(futs):
            name, rc, out, dt, crit = f.result()
            results[name] = (rc, out, dt, crit)
            mark = _OK if rc == 0 else (_FAIL if crit else _WARN)
            print('  %s %-12s rc=%d  %.0fs' % (mark, name, rc, dt))
            if rc != 0:
                for l in _tail(out, 5):
                    print('        ' + l)

    # 摘要：告诉智能体接下来读什么
    print('\n----- 数据速览 -----')
    _print_fetch_summary(results.get('fetch'))
    _print_ohlc_summary(results.get('ohlc'))
    print('  · 技术指标: .workbuddy/_tech_%s.json + _tech_multi_%s.json' % (day, day))
    print('  · 引擎B买卖点: %s/output/000001_%s_买卖点对比表.md' % (SKILL_DIR, day.replace('-', '')))
    print('  · 行业榜: .workbuddy/backtest_data/scan_result_sw_realtime.json + scan_result_ths.json')

    crit_fail = [n for n, (rc, _, _, c) in results.items() if c and rc != 0]
    if crit_fail:
        print('\n%s 关键步骤失败：%s' % (_FAIL, ', '.join(crit_fail)))
        return 1
    print('\n%s 阶段一完成（日志见 .workbuddy/_morning_%s_data_*.log）' % (_OK, day))
    print('下一步：智能体读上述数据 → 建 payload_<日期>_morning.json → 写报告 md → 跑 finish')
    return 0


def _print_fetch_summary(r):
    if not r:
        return
    rc, out, _, _ = r
    m = re.search(r'TOTAL_WINDOW=(\d+)\s+IMAGES=(\d+)\s+FILES=(\d+)', out)
    if m:
        print('  · 抓取: %s 条（图 %s / 附件 %s）→ .workbuddy/zsxq_fetch_raw.json'
              % (m.group(1), m.group(2), m.group(3)))
    else:
        print('  · 抓取: 见日志（未解析到 TOTAL_WINDOW）')


def _print_ohlc_summary(r):
    if not r:
        return
    rc, out, _, _ = r
    if rc != 0:
        return
    try:
        j = json.loads(out)
    except Exception:
        return
    if 'close' in j:
        print('  · OHLC: %s 收盘 %.2f（%+.2f%%）' % (j.get('date'), j['close'], j.get('pct_chg', 0)))


# ======================================================================
# 阶段二：产物收口（顺序，关键步骤失败即停）
# ======================================================================
def cmd_finish(args):
    day = args.date or TODAY()
    payload = args.payload
    md = args.md
    if not os.path.isfile(payload):
        print('%s payload 不存在：%s' % (_FAIL, payload))
        return 1
    if not os.path.isfile(md):
        print('%s 报告 md 不存在：%s' % (_FAIL, md))
        return 1

    print('===== 晨报·阶段二 产物收口（%s）=====' % day)
    # 每步带「关键退出码集合」：rc ∈ crit_rc 才算关键失败（停止），否则仅告警。
    # 校验器的 rc=2 是 WARN（不是 ERROR），不能当关键失败停掉 —— 早期用布尔 crit 把这层搞混了。
    steps = []

    # 1) 变盘倾向分（OBS-2）：rc=1 输入不足必须停；rc=2 降级仅告警（prob_note 里会写明）
    if args.vol and not args.skip_turn:
        tv = ['calc_turn_score.py', '--payload', payload, '--vol', args.vol,
              '--base-a', str(args.base_a), '--base-b', str(args.base_b), '--base-c', str(args.base_c)]
        if args.band_pct is not None:
            tv += ['--band-pct', str(args.band_pct)]
        steps.append(('turn_score', None, tv, {1}, 'calc_turn_score（变盘倾向分）'))
    elif args.skip_turn:
        print('  %s 跳过变盘分（--skip-turn，prob_note 已手填）' % _INFO)
    else:
        print('  %s 未给 --vol，跳过变盘分（剧本概率沿用 payload 里已写值）' % _WARN)

    # 2) 链落盘（统一入口，rc=1 参数问题 / rc=2 校验未过，都要停）
    steps.append(('chain', None, ['chain_apply.py', '--payload', payload], {1, 2}, 'chain_apply（落盘+回读断言）'))

    # 3) DRAGON BALL 归档（rc=2 表示 0 条/守卫跳过，仅告警不覆盖，非关键）
    if not args.skip_archive:
        arch = ['gen_tj_archive.py']
        if args.force_archive:
            arch.append('--force')
        steps.append(('archive', None, arch, set(), 'gen_tj_archive（DRAGON BALL 归档）'))

    # 4) 走势图 / 5) HTML（失败可重跑，非关键）
    steps.append(('svg', None, ['gen_forecast_svg.py'], set(), 'gen_forecast_svg（预判走势图）'))
    steps.append(('html', None, ['md_to_html_report.py', md], set(), 'md_to_html_report（HTML 阅读版）'))

    # 6-8) 三校验（rc=1 是 ERROR 必须停；rc=2 是 WARN 仅告警）
    steps.append(('check_layout', None, ['check_layout.py', md], {1}, 'check_layout（排版，0 ERROR 才过）'))
    steps.append(('check_display', None, ['check_display_name.py', '--today', day], {1, 2}, 'check_display_name（脱敏守卫，任何非零都停）'))
    steps.append(('check_integrity', None, ['check_integrity.py'], {1}, 'check_integrity（数据完整性）'))

    fail = 0
    for name, cwd, argv, crit_rc, desc in steps:
        full = [sys.executable] + [os.path.join(ROOT, '.workbuddy', argv[0])] + argv[1:]
        print('\n-- %s' % desc)
        rc, out, dt = _run(full, cwd=cwd or ROOT, log=_log_path('finish', name, day))
        mark = _OK if rc == 0 else (_FAIL if rc in crit_rc else _WARN)
        print('  %s %-12s rc=%d  %.0fs' % (mark, name, rc, dt))
        if rc != 0:                       # 只在失败时打尾部，rc=0 的校验器输出不刷屏
            for l in _tail(out, 8):
                print('        ' + l)
        if rc in crit_rc:
            print('%s 关键步骤 %s 未过（rc=%d），停止后续。' % (_FAIL, name, rc))
            fail += 1
            break

    if fail:
        print('\n%s 阶段二未完成（见上方失败步骤）' % _FAIL)
        return 1

    # 9) git（可选）
    if args.git:
        print('\n-- git 提交推送')
        arts = ['outputs/作战报告_晨报_%s.md' % day,
                'outputs/作战报告_晨报_%s.html' % day,
                'outputs/000001_forecast_%s.svg' % day,
                'outputs/DRAGON_BALL_原始记录_%s.md' % day]
        for c in (['git', 'add'] + [a for a in arts if os.path.exists(os.path.join(ROOT, a))],
                  ['git', 'commit', '-m', '作战报告_晨报_%s（一键 pipeline）' % day],
                  ['git', 'push', 'origin', 'main']):
            rc, out, dt = _run(c, cwd=ROOT)
            print('  $ %s  → rc=%d' % (' '.join(c[:3]), rc))
            if rc != 0:
                for l in _tail(out, 8):
                    print('        ' + l)
                print('%s git 步骤失败（见上），报告产物已就绪，可手动补推送' % _WARN)
                return 2

    print('\n%s 阶段二完成。' % _OK)
    print('交付物: outputs/作战报告_晨报_%s.md / .html / 000001_forecast_%s.svg / DRAGON_BALL_原始记录_%s.md'
          % (day, day, day))
    return 0


def cmd_plan(args):
    print('''===== 晨报一键流程速查 =====

[阶段一] 数据采集（≤2 并发，约十几分钟）
  $PY .workbuddy/run_morning_report.py data
  产物: zsxq_fetch_raw.json / OHLC / _tech*.json / 引擎B买卖点表 / 行业榜两 JSON

[智能体分析]（本步非脚本，读数据后完成三件事）
  1. 读抓取内容 → 提取主线/共识/分歧（信息判断）
  2. 读 OHLC+技术+引擎 → 形成预判（方向/区间/支撑/压力/置信度）→ 建 payload
     $PY .workbuddy/chain_apply.py --init-template morning <日期>   # 生成 payload 骨架
  3. 写报告 md（五块，直接按脱敏口径写：真实名→定调等，附录用通道汇总）

[阶段二] 产物收口（顺序，关键失败即停）
  $PY .workbuddy/run_morning_report.py finish --payload <json> --md <md> --vol "v1,v2,v3,v4,v5" [--git]
  步骤: 变盘分 → 链落盘 → 归档 → SVG → HTML → 三校验 → (git)

排版铁律（写 md 时就照做，别再事后返工）:
  ① 关键位表唯一完整落地，正文其余处用整数/指针（同价位正文 ≤8 次）
  ② 55 线正文统一写 60F MA55（不写 60F55），走势图标签可保留 60F55
  ③ BOLL 中轨 ≡ MA20，全篇只在首次出现注一句
  ④ 核心速览每行 ≤90 字、一句话预判 ≤150 字
  ⑤ 脱敏直接写「定调」，附录 A 用通道汇总口径（不逐列星球名）
''')


def main(argv=None):
    ap = argparse.ArgumentParser(description='作战报告·晨报 一键编排', add_help=True)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sp_data = sub.add_parser('data', help='阶段一：数据采集')
    sp_data.add_argument('--date', default=None, help='指定日期（默认今天）')
    sp_data.set_defaults(func=cmd_data)

    sp_fin = sub.add_parser('finish', help='阶段二：产物收口')
    sp_fin.add_argument('--payload', required=True, help='payload JSON 路径')
    sp_fin.add_argument('--md', required=True, help='报告 md 路径')
    sp_fin.add_argument('--vol', default=None, help='近5日成交量逗号分隔（含当日，时间升序）')
    sp_fin.add_argument('--band-pct', type=float, default=None, help='15F BOLL 带宽 %%')
    sp_fin.add_argument('--base-a', type=int, default=40)
    sp_fin.add_argument('--base-b', type=int, default=35)
    sp_fin.add_argument('--base-c', type=int, default=25)
    sp_fin.add_argument('--skip-turn', action='store_true')
    sp_fin.add_argument('--skip-archive', action='store_true')
    sp_fin.add_argument('--force-archive', action='store_true')
    sp_fin.add_argument('--git', action='store_true', help='末尾 git add+commit+push')
    sp_fin.add_argument('--date', default=None)
    sp_fin.set_defaults(func=cmd_finish)

    sp_plan = sub.add_parser('plan', help='打印完整流程速查')
    sp_plan.set_defaults(func=cmd_plan)

    args = ap.parse_args(argv)
    sys.exit(args.func(args))


if __name__ == '__main__':
    main()
