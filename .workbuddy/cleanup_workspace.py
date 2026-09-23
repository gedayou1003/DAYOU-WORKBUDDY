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
     'I-6 前旧命名（DRAGON BALL模型 原始抓取中转件）', None),
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
    ('.workbuddy/_engB.log', 'log', '引擎 B 执行日志（2026-09-18 收盘档临时）', None),
    ('.workbuddy/_engC.log', 'log', '引擎 C 执行日志（2026-09-18 收盘档临时）', None),
    ('.workbuddy/_engMulti.log', 'log', '四周期联动执行日志（2026-09-18 收盘档临时）', None),
    ('.workbuddy/_fetch_afternoon.log', 'log', '星球 afternoon 抓取日志（2026-09-18 收盘档临时）', None),
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

    # ---------- 6. 2026-09-21 代码梳理（临时审计件）----------
    # 结构审计已固化进 audit_pipeline.py 的【8】测试覆盖 /【9】subprocess 未校验，
    # 参数守卫已固化为常驻 test_arg_guard.py（含变异自证），以下均为一次性中间件。
    ('.workbuddy/_audit_code.py', 'oneoff_script',
     '第一遍反模式扫描器（噪声过大，已被 audit_pipeline.py 覆盖）', None),
    ('.workbuddy/_audit_code2.py', 'oneoff_script',
     '第二遍结构化精判（E 类判据过度匹配 docstring 产生误报，结论已复核并写入报告）', None),
    ('.workbuddy/_verify3.py', 'oneoff_script', '复核 E2/E3 判据的取证脚本（已确认全为误报）', None),
    ('.workbuddy/_gi2.py', 'oneoff_script',
     '运行件 git 跟踪状态取证（发现 quotepath 中文转义陷阱，已沉淀进 MEMORY）', None),
    ('.workbuddy/_scan_silentarg.py', 'oneoff_script',
     '静默参数回退定向扫描器（结论已写入代码梳理报告）', None),
    ('.workbuddy/_test_argguard.py', 'oneoff_script',
     '参数守卫验证脚本 → 已固化为常驻 test_arg_guard.py', None),
    ('.workbuddy/_mutation_argguard.py', 'oneoff_script',
     '参数守卫变异测试 → 变异自证段已并入 test_arg_guard.py 第 3 节', None),
    ('.workbuddy/_audit_code.txt', 'audit_output', '一次性扫描输出', None),
    ('.workbuddy/_audit_code2.txt', 'audit_output', '一次性扫描输出', None),
    ('.workbuddy/_verify3.txt', 'audit_output', '取证输出', None),
    ('.workbuddy/_gi2.txt', 'audit_output', '取证输出', None),
    ('.workbuddy/_scan_silentarg.txt', 'audit_output', '一次性扫描输出', None),
    ('.workbuddy/_audit_pipeline_full.txt', 'audit_output', '审计全量输出（结论已进代码梳理报告）', None),
    ('.workbuddy/_ap2.txt', 'audit_output', '扩展审计工具的验证输出', None),
    ('.workbuddy/_ap3.txt', 'audit_output', '扩展审计工具的验证输出', None),
    ('.workbuddy/_ap3_stdout.txt', 'audit_output', '扩展审计工具的终端输出', None),
    ('.workbuddy/_ap4.txt', 'audit_output', '扩展审计工具 --full 输出', None),
    ('.workbuddy/_test_argguard.txt', 'audit_output', '参数守卫验证输出', None),
    ('.workbuddy/_argguard_stdout.txt', 'audit_output', '参数守卫验证的终端输出', None),
    ('.workbuddy/_mutation_argguard.txt', 'audit_output', '变异测试输出', None),
    ('.workbuddy/_mut_stdout.txt', 'audit_output', '变异测试的终端输出', None),
    ('.workbuddy/_tag.txt', 'audit_output', 'test_arg_guard.py 的终端输出落盘', None),
    ('_gitfiles.txt', 'transient', '根目录：git 跟踪列表取证', None),
    ('_gitstatus.txt', 'transient', '根目录：git status 取证', None),
    ('_gf2.txt', 'transient', '根目录：quotepath 复跑取证', None),
    ('_gi.txt', 'transient', '根目录：check-ignore 取证', None),
    ('_list_before.txt', 'transient', '根目录：清理前临时件清单（用于与 dry-run 计划交叉核对）', None),
    ('_list_after.txt', 'transient', '根目录：清理后临时件清单（核验用）', None),
    ('_cw_dry.txt', 'audit_output', 'cleanup_workspace dry-run 输出（根目录）', None),
    ('.workbuddy/_cw_apply.txt', 'audit_output', 'cleanup_workspace --apply 输出', None),
    ('.workbuddy/_cw_apply2.txt', 'log', 'cleanup_workspace 第二次 --apply 的输出（自身滞后一轮归档）', None),
    ('.workbuddy/_run_all_tests.py', 'oneoff_script',
     '临时测试跑批 → 已提升为常驻 run_tests.py（含逐项耗时与超时保护）', None),
    ('.workbuddy/_alltests.txt', 'audit_output', '临时测试跑批输出', None),
    ('.workbuddy/_rt1.txt', 'audit_output', 'run_tests.py --only 验证输出', None),
    ('.workbuddy/_rt_all.txt', 'audit_output', 'run_tests.py 全量输出（12/12 通过）', None),
    ('.workbuddy/_lt.txt', 'audit_output', 'test_layout_typography.py 修复过程输出', None),
    ('.workbuddy/_cw_apply3.txt', 'log', 'cleanup_workspace 第三次 --apply 的输出', None),
    ('_st.txt', 'transient', '根目录：git status 取证（quotepath 默认）', None),
    ('_st2.txt', 'transient', '根目录：git status 取证（quotepath=false）', None),

    # ---------- 5. 文档腐烂收口（2026-09-21 第二轮）的取证与输出 ----------
    ('.workbuddy/_docrot_probe.py', 'oneoff_script',
     '一次性探针：把「文档引用已归档脚本」逐处展开成原文并判定是否已交代归档；'
     '判定逻辑已固化进 audit_pipeline.scan_docs + test_audit_detector.py §5', None),
    ('.workbuddy/_docrot_probe.txt', 'audit_output', '上述探针的输出（逐处原文与判定）', None),
    ('.workbuddy/_inv_0921.txt', 'audit_output', '根目录脚本清单复点（校正 66→72）', None),
    ('.workbuddy/_facts_0921.txt', 'audit_output', '归档目录计数 + 未记录脚本职责取证', None),
    ('.workbuddy/_skill_probe.txt', 'audit_output', '技能目录与引擎脚本真实位置核实（证 run_000001_*.py 确实存在）', None),
    ('.workbuddy/_audit_full_0921.txt', 'audit_output', 'audit_pipeline --full 输出（改判定前）', None),
    ('.workbuddy/_audit2_0921.txt', 'audit_output', 'audit_pipeline --full 输出（四分类后）', None),
    ('.workbuddy/_audit3_0921.txt', 'audit_output', 'audit_pipeline --full 输出（改按出现位置判定后）', None),
    ('.workbuddy/_audit4_0921.txt', 'audit_output', 'audit_pipeline --full 输出（修文档中）', None),
    ('.workbuddy/_audit5_0921.txt', 'audit_output', 'audit_pipeline --full 输出（文档腐烂 0）', None),
    ('.workbuddy/_sec4.txt', 'audit_output', '审计第【4】节与汇总的抽取片段', None),
    ('.workbuddy/_cw.txt', 'audit_output', 'cleanup_workspace.py 源码片段读取中转件', None),
    ('.workbuddy/_t1.txt', 'audit_output', 'test_audit_detector.py 输出（19 条断言全绿）', None),
    ('.workbuddy/_t2.txt', 'audit_output', 'test_audit_docrot_neg.py 输出（5/5 变异被拦下）', None),
    ('.workbuddy/_run_tests_0921.txt', 'audit_output', 'run_tests.py 全量输出（13/13 通过）', None),
    ('.workbuddy/_cw_dry2.txt', 'audit_output', 'cleanup_workspace dry-run 输出（第二轮）', None),
    ('.workbuddy/_cw_tail.txt', 'audit_output', 'cleanup_workspace dry-run 尾部抽取（核对计划数）', None),
    ('.workbuddy/_verify_final.txt', 'audit_output', '清理后核验：遗留 _ 件、根目录脚本计数、archive 总计', None),
    ('.workbuddy/_arch_count.txt', 'audit_output', 'archive 明细重新统计（校正 245→282）', None),

    # ---------- 7. 全链路冒烟（2026-09-21 第三轮）的取证与输出 ----------
    # 能力已固化为**常驻工具** .workbuddy/smoke_pipeline.py（30 阶段、默认零副作用、
    # 前后 md5 快照 + zip 备份回滚）与 test_tj_guard.py，以下均为一次性中间件。
    ('.workbuddy/_probe_cwd.py', 'oneoff_script',
     'cwd 隐式依赖全局扫描（AST，74 个脚本）→ 结论：仅 engine_effectiveness.py 一处，已修', None),
    ('.workbuddy/_probe_cwd.txt', 'audit_output', '上述扫描输出 + gen_tj_archive 幂等验证', None),
    ('.workbuddy/_probe_diff.py', 'oneoff_script',
     '归档文件「跑前 vs 重跑后」差分（坐实机械版覆盖人工精修版的信息丢失）', None),
    ('.workbuddy/_probe_diff.txt', 'audit_output', '上述差分输出', None),
    ('.workbuddy/_probe_fields.py', 'oneoff_script',
     '止损恢复脚本 + 快照可用字段探查（顺手还原被覆盖的 DRAGON_BALL 精修版）', None),
    ('.workbuddy/_probe_fields.txt', 'audit_output', '上述输出（含字段清单）', None),
    ('.workbuddy/_probe_fields_out.txt', 'audit_output', '上述脚本的终端输出落盘', None),
    ('.workbuddy/_probe_tag.py', 'oneoff_script', '平台富文本标签形态取证（title 里是 URL 编码原文）', None),
    ('.workbuddy/_probe_tag.txt', 'audit_output', '上述取证输出', None),
    ('.workbuddy/_probe_tag_out.txt', 'audit_output', '上述脚本的终端输出落盘', None),
    ('.workbuddy/_probe_chain.py', 'oneoff_script',
     'forecast_chain.json 的 review.actual 形态分布取证（dict 49 / str 2 / None 1）', None),
    ('.workbuddy/_probe_chain.txt', 'audit_output', '上述取证输出', None),
    ('.workbuddy/_probe_chain_out.txt', 'audit_output', '上述脚本的终端输出落盘', None),
    ('.workbuddy/_probe_tmp.py', 'oneoff_script', '临时目录占用盘点脚本（未执行，能力已并入 smoke 的 _cleanup）', None),
    ('.workbuddy/_smoke_fast.txt', 'audit_output', '冒烟首跑输出（暴露 harness 自身的 % 转义 BUG）', None),
    ('.workbuddy/_smoke_fast2.txt', 'audit_output', '冒烟修复后输出（19/20，暴露 engine_effectiveness cwd 依赖）', None),
    ('.workbuddy/_smoke_fast3.txt', 'audit_output', '冒烟快速档最终输出（20/20 ALL PASS）', None),
    ('.workbuddy/_smoke_full.txt', 'audit_output', '冒烟全量输出（30 阶段，29 通过；暴露 test_chain_apply 偶发红）', None),
    ('.workbuddy/_tj_test.txt', 'audit_output', 'test_tj_guard.py 输出（24 条断言全绿）', None),
    ('.workbuddy/_ee_out.txt', 'audit_output', 'engine_effectiveness.py 修复后输出（含「未纳入统计」段）', None),
    ('.workbuddy/_rt_ca.txt', 'audit_output', 'run_tests --only chain_apply 输出（单跑绿 —— 定位假失败的对照）', None),
    ('.workbuddy/_rt_full2.txt', 'audit_output', 'run_tests 全量输出（仍红，且 stderr 被丢弃看不到 traceback）', None),
    ('.workbuddy/_rt_full3.txt', 'audit_output', 'run_tests 全量输出（合并 stderr 后仍无 traceback → 判定为进程被杀）', None),
    ('.workbuddy/_rt_full4.txt', 'audit_output', 'run_tests 全量输出（改 fresh() 后仍红 → 排除 rmtree 次数假设）', None),
    ('.workbuddy/_rt_full5.txt', 'audit_output', 'run_tests 全量输出（去掉仓库内 os.remove 后 14/14 ALL PASS）', None),
    ('.workbuddy/_tca_out.txt', 'audit_output', 'test_chain_apply.py 单跑输出（cwd=仓库根）', None),
    ('.workbuddy/_tca_cwdwb.txt', 'audit_output', 'test_chain_apply.py 单跑输出（cwd=.workbuddy）', None),
    ('.workbuddy/_seq_test_arg_guard.py.txt', 'audit_output', '受控实验：按聚合顺序串跑的第 1 个', None),
    ('.workbuddy/_seq_test_audit_detector.py.txt', 'audit_output', '受控实验：第 2 个', None),
    ('.workbuddy/_seq_test_audit_docrot_neg.py.txt', 'audit_output', '受控实验：第 3 个', None),
    ('.workbuddy/_seq_test_backfill_actual.py.txt', 'audit_output', '受控实验：第 4 个', None),
    ('.workbuddy/_seq_chain_apply.txt', 'audit_output',
     '受控实验：第 5 个（绿 —— 证明触发条件是「子进程在沙箱内」，不是前序测试）', None),
    ('.workbuddy/_build_payload_0917_close.py', 'oneoff_script',
     '写死 2026-09-17 收盘 payload 的一次性生成器（47KB），全仓库零引用，成分已并入 chain_apply', None),
    ('.workbuddy/模型体检报告_2026-09-16.html', 'oneoff_output',
     '过期的一次性模型体检报告（《代码梳理报告》§六 第 6 项；同日报告已并入后续梳理，无脚本引用）', None),

    # ---------- 8. 补录 2026-09-18-close（2026-09-23）的取证与补判脚本 ----------
    # 补判能力是否要固化为常驻工具：**否** —— 该场景已被 backfill_actual_data.py
    # （批量历史回填，K 线快照止于 2026-09-04）与「正规回填路径（apply_review /
    # 直改 JSON）」覆盖，单条补判按先例属一次性操作（参考 _fix_0907_sr.py）。
    ('.workbuddy/_probe_ohlc_0921.py', 'oneoff_script',
     '拉取上证综指最近 12 个交易日真实日线（腾讯 fqkline），供补录 9/21 的 actual 比对', None),
    ('.workbuddy/_probe_ohlc_0921.json', 'audit_output', '上述取数结果（含 9/21、9/22 两日实况）', None),
    ('.workbuddy/_probe_outputs_sensitive.py', 'oneoff_script',
     'outputs/ 入库前的敏感项体检（凭证 / gid / 星球真名 / 通道信息 / 长数字串 / 手机号形态）', None),
    ('.workbuddy/_probe_outputs_sensitive.json', 'audit_output',
     '上述体检结果：cred=0、gid=1 处、真名命中 121 个文件 —— 入库决策的直接依据', None),
    ('.workbuddy/_fix_0918_close.py', 'oneoff_script',
     '一次性补判（一阶段）：补齐 2026-09-18-close 的 actual + 支撑/压力两维，'
     '四维总期数 51→52 对齐；备份于 archive/backup_20260923_0918fix', None),
    ('.workbuddy/_fix_0918_range.py', 'oneoff_script',
     '一次性补判（二阶段）：按用户拍板把区间维度由「✅ 静态守住」修正为「❌ 突破」；'
     '备份于 archive/backup_20260923_0918range', None),
    ('.workbuddy/_ee_after.txt', 'audit_output',
     'engine_effectiveness 补录后输出（证明 2026-09-18-close 已进入指标1、不再是「未纳入统计」）', None),
    ('.workbuddy/_cw_dry.txt', 'audit_output', 'cleanup_workspace 本次 dry-run 输出', None),
    ('.workbuddy/_band_run.txt', 'audit_output', 'build_range_band 执行输出（补齐后 22 天区间带）', None),
    ('.workbuddy/_rt_after_fix.txt', 'audit_output', 'run_tests 输出（补录后链状态：14/14 ALL PASS）', None),
    ('.workbuddy/_rt_final.txt', 'audit_output',
     'run_tests 输出（补录 + 区间修正后的最终链状态：14/14 ALL PASS，134.3s）', None),
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
