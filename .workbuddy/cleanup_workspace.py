# -*- coding: utf-8 -*-
"""工作区卫生清理：把一次性脚本 / 陈旧命名产物 / 审计输出 / 临时日志归档到 archive/。

设计原则（2026-09-17 立）：
  1. **归档，不删除** —— 全部 shutil.move 到 .workbuddy/archive/hygiene_<日期>/，
     并写 MANIFEST.md 记录「原路径 → 新路径 → 为什么」。要回滚照着 MANIFEST 反向 move 即可。
  2. **默认 dry-run** —— 不加 --apply 只打印计划，不动任何文件。
  3. **重复文件先验哈希** —— 标 dup_of 的条目必须先 md5 相同才动，不同就跳过并告警。
  4. **声明式清单** —— 新发现要清理的东西，往 ACTIONS 里加一行，不要另写脚本。

用法：
    python cleanup_workspace.py            # 打印计划（不动文件）
    python cleanup_workspace.py --apply    # 执行归档
"""
import argparse
import datetime
import hashlib
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WB = os.path.join(ROOT, '.workbuddy')

# (相对路径, 分类目录, 原因, dup_of)
#   dup_of 非空时，必须先与该文件的 md5 一致才归档（防止误删不同内容）
ACTIONS = [
    # ---------- 1. I-6 重构（2026-09-16）之前的旧命名产物 ----------
    # 规范：calc_tech.py → _tech_YYYY-MM-DD.json；digest_zsxq.py → _zsxq_digest_YYYY-MM-DD.txt
    # 旧版用 _MDD（_tech_0915）或 _MMDD（_zsxq_digest_0916）两种写法，已废弃
    ('.workbuddy/_tech_0915.json', 'legacy_naming',
     'I-6 前旧命名（_MMDD），现规范为 _tech_YYYY-MM-DD.json', None),
    ('.workbuddy/_tech_0916.json', 'legacy_naming',
     'I-6 前旧命名；内容是 09-15 收盘快照，已被 _tech_2026-09-16.json 取代', None),
    ('.workbuddy/_zsxq_digest_0916.txt', 'legacy_naming',
     'I-6 前旧命名，与 _zsxq_digest_2026-09-16.txt 内容完全相同', 'md5',
     '.workbuddy/_zsxq_digest_2026-09-16.txt'),
    ('.workbuddy/_tj_raw_0916.txt', 'legacy_naming',
     'I-6 前旧命名（T&J 原始抓取中转件）', None),
    ('.workbuddy/_zsxq_digest.txt', 'legacy_naming',
     'I-6 前固定文件名产物（无日期），已被 _zsxq_digest_YYYY-MM-DD.txt 取代', None),
    ('.workbuddy/_tech_extra_2026-09-17.json', 'legacy_naming',
     '_tech_extra.py 的产出，已被 calc_tech_multi.py 的 _tech_multi_<日期>.json 取代', None),

    # ---------- 2. 已执行完的一次性脚本 ----------
    ('.workbuddy/_archive_daily.py', 'oneoff_script', '一次性脚本（归档功能已并入 archive_daily 流程）', None),
    ('.workbuddy/_audit_layout.py', 'oneoff_script', '一次性审计脚本（体检已过）', None),
    ('.workbuddy/_audit_layout2.py', 'oneoff_script', '一次性审计脚本（体检已过）', None),
    ('.workbuddy/_audit_static.py', 'oneoff_script', '一次性静态扫描脚本（体检已过）', None),
    ('.workbuddy/_calc_boll.py', 'oneoff_script', '一次性 BOLL 计算脚本', None),
    ('.workbuddy/_tech_extra.py', 'oneoff_script',
     '能力已参数化重写为 calc_tech_multi.py（原版写死绝对路径，公司机器会崩）', None),
    ('.workbuddy/_fix_0907_actual.py', 'oneoff_script',
     '一次性数据修复（已补录 2026-09-07-close 的 actual 并备份）', None),
    ('.workbuddy/_fix_0907_sr.py', 'oneoff_script',
     '一次性补判脚本（已补齐 2026-09-07-close 的 support/resistance 两维，备份于 archive/backup_20260917_srfix）', None),
    ('.workbuddy/_archive_chanlun_skills.py', 'oneoff_script',
     '一次性技能归档脚本（4 个 off 缠论技能已移入 ~/.workbuddy/skills_archive/20260917_chanlun/，还原见该目录 restore.py）', None),
    ('.workbuddy/_inv_hygiene.py', 'oneoff_script', '本次卫生盘点脚本（声明式清单已固化进 cleanup_workspace.py）', None),
    ('.workbuddy/_inv2.py', 'oneoff_script', '本次取证脚本', None),
    ('.workbuddy/gen_evening_report.py', 'oneoff_script',
     '写死 2026-08-17 的一次性报告生成器（36KB 硬编码正文），无任何脚本引用', None),
    ('.workbuddy/gen_intraday_svg.py', 'oneoff_script',
     '写死 2026-09-03 盘中快照的一次性绘图 wrapper，无引用', None),

    # ---------- 3. 审计文本输出 ----------
    ('.workbuddy/_audit_layout2.txt', 'audit_output', '审计中间输出', None),
    ('.workbuddy/_audit_layout_result.txt', 'audit_output', '审计中间输出', None),
    ('.workbuddy/_audit_static_result.txt', 'audit_output', '审计中间输出（结论已进体检报告）', None),

    # ---------- 4. 临时日志 ----------
    ('.workbuddy/_addclose.log', 'log', '执行日志', None),
    ('.workbuddy/_addmorn0916.log', 'log', '执行日志', None),
    ('.workbuddy/_band_log.txt', 'log', 'build_range_band 执行日志（每次运行覆盖，无历史价值）', None),
    ('.workbuddy/_check.log', 'log', '执行日志', None),
    ('.workbuddy/_check0916.log', 'log', '执行日志', None),
    ('.workbuddy/_cons0916.log', 'log', '执行日志', None),
    ('.workbuddy/_dims_log.txt', 'log', '执行日志', None),
    ('.workbuddy/_engine_b.log', 'log', '引擎执行日志', None),
    ('.workbuddy/_engine_c.log', 'log', '引擎执行日志', None),
    ('.workbuddy/_html.log', 'log', '执行日志', None),
    ('.workbuddy/_html0916.log', 'log', '执行日志', None),
    ('.workbuddy/_ohlc.log', 'log', '执行日志', None),
    ('.workbuddy/_recon0915.log', 'log', '执行日志', None),
    ('.workbuddy/_svg0916.log', 'log', '执行日志', None),
    ('.workbuddy/_sw.log', 'log', '执行日志', None),
    ('.workbuddy/_tech_0916.log', 'log', '执行日志', None),
    ('.workbuddy/_ths.log', 'log', '同花顺扫描日志（23KB）', None),
    ('.workbuddy/_zsxq.log', 'log', '抓取执行日志', None),
    ('_clean.log', 'log', '根目录执行日志', None),
    ('_g3.log', 'log', '根目录执行日志', None),
    ('_g4.log', 'log', '根目录执行日志', None),
    ('_git.log', 'log', '根目录执行日志', None),
    ('_git2.log', 'log', '根目录执行日志', None),
    ('_html2.log', 'log', '根目录执行日志', None),
    ('_p.log', 'log', '根目录执行日志', None),
    ('_push.log', 'log', '根目录执行日志', None),
    ('_push2.log', 'log', '根目录执行日志', None),
    ('_st.log', 'log', '根目录执行日志', None),

    # ---------- 5. 流水线中转产物 ----------
    ('.workbuddy/payload_2026-09-16_close.json', 'transient',
     'chain_apply 输入 payload，已执行完（保留最新的 09-17 作样版）', None),
    ('.workbuddy/_backfill_0917.json', 'transient',
     'backfill_zsxq_window 的 --json-out 输出，已并入补档报告', None),
    ('.workbuddy/_inv.txt', 'transient', '盘点脚本 stdout 落盘', None),
    ('.workbuddy/_inv2.txt', 'transient', '取证脚本 stdout 落盘', None),
    ('.workbuddy/_tmp_idem.txt', 'transient', '幂等复跑的 stdout 落盘', None),
    ('.workbuddy/_dbg_path.py', 'transient', '路径调试脚本', None),
    ('.workbuddy/_cw.log', 'log', 'cleanup_workspace 自身的 stdout 落盘', None),
]

# 提升为正式工具（重命名/替代，不进 archive）
PROMOTE = [
    ('.workbuddy/_neg_test_gen_forecast_svg.py', '.workbuddy/test_gen_forecast_svg_neg.py',
     '负例验证工具（证明回归测试真的拦得住），属常驻资产'),
    # _tech_extra.py 的能力已参数化重写为 calc_tech_multi.py（去掉了写死绝对路径），
    # 原件按普通一次性脚本归档；见 ACTIONS 中的 oneoff_script 段
]


def md5(p):
    m = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            m.update(b)
    return m.hexdigest()


def main():
    ap = argparse.ArgumentParser(description='工作区卫生清理（归档不删除，默认 dry-run）')
    ap.add_argument('--apply', action='store_true', help='真正执行；不加则只打印计划')
    ap.add_argument('--date', default=datetime.date.today().strftime('%Y%m%d'),
                    help='归档目录后缀（默认今日）')
    a = ap.parse_args()

    dest_root = os.path.join(WB, 'archive', 'hygiene_%s' % a.date)
    print('模式：%s' % ('APPLY（将移动文件）' if a.apply else 'DRY-RUN（不动文件）'))
    print('归档根：%s' % dest_root)
    print('')

    done, skipped, missing = [], [], []
    manifest = []
    for item in ACTIONS:
        rel, cat, why = item[0], item[1], item[2]
        dup_flag = item[3] if len(item) > 3 else None
        dup_of = item[4] if len(item) > 4 else None
        src = os.path.join(ROOT, rel.replace('/', os.sep))
        if not os.path.exists(src):
            missing.append(rel)
            continue

        # 重复文件必须先验哈希
        if dup_flag == 'md5' and dup_of:
            ref = os.path.join(ROOT, dup_of.replace('/', os.sep))
            if not os.path.exists(ref):
                skipped.append((rel, '参照文件不存在：%s' % dup_of))
                continue
            h1, h2 = md5(src), md5(ref)
            if h1 != h2:
                skipped.append((rel, 'md5 与 %s 不一致（%s vs %s），已跳过' % (dup_of, h1[:8], h2[:8])))
                continue
            why += '（md5=%s 已验证一致）' % h1[:8]

        dst = os.path.join(dest_root, cat, os.path.basename(src))
        # 字节数必须在移动**之前**取，否则汇总恒为 0
        size = os.path.getsize(src)
        manifest.append((rel, os.path.relpath(dst, ROOT), cat, why, size))
        if a.apply:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
        done.append(rel)

    promoted = []
    for src_rel, dst_rel, why in PROMOTE:
        src = os.path.join(ROOT, src_rel.replace('/', os.sep))
        dst = os.path.join(ROOT, dst_rel.replace('/', os.sep))
        if not os.path.exists(src):
            if os.path.exists(dst):
                promoted.append((src_rel, dst_rel, why, '已完成过'))
            else:
                missing.append(src_rel)
            continue
        if a.apply:
            shutil.move(src, dst)
        promoted.append((src_rel, dst_rel, why, '待执行' if not a.apply else '已重命名'))

    # 按分类汇总
    bycat = {}
    for rel, _, cat, _, size in manifest:
        bycat.setdefault(cat, []).append(size)
    print('— 计划归档 —')
    for cat in sorted(bycat):
        print('  [%s] %d 个，%.1f KB' % (cat, len(bycat[cat]), sum(bycat[cat]) / 1024))
    print('  合计 %d 个，%.1f KB' % (len(manifest), sum(x[4] for x in manifest) / 1024))
    print('')
    print('— 计划重命名 —')
    for src_rel, dst_rel, why, st in promoted:
        print('  %-42s → %-38s %s' % (src_rel, os.path.basename(dst_rel), st))
    if skipped:
        print('')
        print('— 跳过（需人工确认）—')
        for rel, why in skipped:
            print('  %s：%s' % (rel, why))
    if missing:
        print('')
        print('— 已不存在（%d 个，正常）—' % len(missing))

    if a.apply and manifest:
        os.makedirs(dest_root, exist_ok=True)
        mp = os.path.join(dest_root, 'MANIFEST.md')
        with open(mp, 'w', encoding='utf-8') as f:
            f.write('# 卫生归档清单 %s\n\n' % a.date)
            f.write('由 `cleanup_workspace.py --apply` 生成。**内容为移动，不是删除**；\n'
                    '回滚方式：按表中「新路径」反向 move 回「原路径」。\n\n')
            f.write('| 原路径 | 新路径 | 分类 | 原因 |\n|---|---|---|---|\n')
            for rel, dst_rel, cat, why, size in manifest:
                f.write('| `%s` | `%s` | %s | %s |\n' % (rel, dst_rel, cat, why))
        print('')
        print('已写出清单：%s' % mp)
        print('已归档 %d 个文件到 %s' % (len(manifest), dest_root))
    elif not a.apply and manifest:
        print('')
        print('（dry-run 结束；加 --apply 才会真正移动）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
