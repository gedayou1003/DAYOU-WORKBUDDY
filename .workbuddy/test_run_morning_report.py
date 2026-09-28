# -*- coding: utf-8 -*-
"""run_morning_report.py 的退出码语义回归测试（2026-09-28 补，堵「编排器无测试」缺口）。

为什么必须测这个（今天刚改，且直接决定明天晨报 finish 会不会卡错地方）：
  run_morning_report.py 的 cmd_finish 用「关键退出码集合 crit_rc」判定每步是否关键失败——
    · rc ∈ crit_rc → 停（fail=1，返回 1）
    · rc = 2 但 ∉ crit_rc（如 check_layout/turn_score 的 WARN）→ 仅告警，继续
    · rc = 0 → 过
  这个判定是今天从布尔 `crit` 改成 `crit_rc` 集合的（布尔无法区分三级退出码）。
  若判错，明天 finish 要么「WARN 被误停」、要么「ERROR 被放过」——都会回到
  「跑→看→修→再跑」的返工循环，正是用户最不想再经历的「一小时」。

本测试不碰网络：monkeypatch 掉 `_run`，按调用顺序喂预设 rc，验证 cmd_finish 的
停/不停/返回码 与 实际调用步数。只测语义，不测真实子进程。

用法：$PY .workbuddy/test_run_morning_report.py
退出码：0 全通过 / 1 有断言失败
"""
import importlib.util
import os
import sys
import tempfile
import types

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('rmr', os.path.join(HERE, 'run_morning_report.py'))
rmr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rmr)

fails = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


def _mk_args(payload, md, **kw):
    """构造 cmd_finish 需要的 args（SimpleNamespace）。"""
    base = dict(payload=payload, md=md, vol='1,2,3,4,5', skip_turn=False,
                base_a=40, base_b=35, base_c=25, band_pct=None,
                skip_archive=False, force_archive=False, git=False, date=None)
    base.update(kw)
    return types.SimpleNamespace(**base)


def _patch_run(rc_sequence):
    """替换 rmr._run 为「按调用顺序返回预设 rc」的假函数。返回 (原_run, calls)。"""
    orig = rmr._run
    calls = []

    def fake_run(cmd, cwd=None, log=None, timeout=1200):
        # cmd[0]=sys.executable, cmd[1]=脚本路径 → 记 basename 用于事后断言
        calls.append(os.path.basename(cmd[1]) if len(cmd) > 1 else '')
        idx = len(calls) - 1
        rc = rc_sequence[idx] if idx < len(rc_sequence) else 0
        return rc, '', 0.0

    rmr._run = fake_run
    return orig, calls


def _restore(orig):
    rmr._run = orig


def main():
    d = tempfile.mkdtemp(prefix='rmr_')
    payload = os.path.join(d, 'payload.json')
    md = os.path.join(d, 'report.md')
    for p in (payload, md):
        with open(p, 'w', encoding='utf-8') as f:
            f.write('{}')

    # 全绿时 finish 应有 8 步：turn_score + chain + archive + svg + html
    #                              + check_layout + check_display + check_integrity
    N_ALL = 8

    print('A) 全绿 8 步 → rc=0，且 8 步全部跑到')
    orig, calls = _patch_run([0] * N_ALL)
    rc = rmr.cmd_finish(_mk_args(payload, md))
    ck(rc == 0, '全绿返回 0（实测 %d）' % rc)
    ck(len(calls) == N_ALL, '跑满 %d 步（实测 %d）' % (N_ALL, len(calls)))
    _restore(orig)

    print('B) turn_score rc=2（WARN，crit_rc={1}）→ 不停，仍跑满 8 步 → rc=0')
    orig, calls = _patch_run([2] + [0] * (N_ALL - 1))
    rc = rmr.cmd_finish(_mk_args(payload, md))
    ck(rc == 0, 'WARN 不被误停（实测 %d）' % rc)
    ck(len(calls) == N_ALL, '跑满 %d 步（实测 %d）' % (N_ALL, len(calls)))
    _restore(orig)

    print('C) turn_score rc=1（ERROR，crit_rc={1}）→ 停在第 1 步 → rc=1')
    orig, calls = _patch_run([1])
    rc = rmr.cmd_finish(_mk_args(payload, md))
    ck(rc == 1, 'ERROR 停，返回 1（实测 %d）' % rc)
    ck(len(calls) == 1, '只调用 1 步即停（实测 %d）' % len(calls))
    _restore(orig)

    print('D) chain rc=2（crit_rc={1,2}，任何非零都停）→ 停在第 2 步 → rc=1')
    orig, calls = _patch_run([0, 2])
    rc = rmr.cmd_finish(_mk_args(payload, md))
    ck(rc == 1, 'chain rc=2 停，返回 1（实测 %d）' % rc)
    ck(len(calls) == 2, '只调用 2 步即停（实测 %d）' % len(calls))
    _restore(orig)

    print('E) check_integrity rc=2（WARN，crit_rc={1}）→ 不停（末步）→ rc=0')
    orig, calls = _patch_run([0] * (N_ALL - 1) + [2])
    rc = rmr.cmd_finish(_mk_args(payload, md))
    ck(rc == 0, '末步 WARN 不被误停（实测 %d）' % rc)
    ck(len(calls) == N_ALL, '跑满 %d 步（实测 %d）' % (N_ALL, len(calls)))
    _restore(orig)

    print('F) check_display rc=2（crit_rc={1,2}）→ 停在第 7 步 → rc=1')
    orig, calls = _patch_run([0] * 6 + [2])
    rc = rmr.cmd_finish(_mk_args(payload, md))
    ck(rc == 1, 'check_display 任何非零停，返回 1（实测 %d）' % rc)
    ck(len(calls) == 7, '停在第 7 步（实测 %d）' % len(calls))
    _restore(orig)

    print('G) --skip-turn 时不跑 turn_score → 从 chain 开始（第 1 步是 chain_apply）')
    orig, calls = _patch_run([0] * N_ALL)
    rc = rmr.cmd_finish(_mk_args(payload, md, skip_turn=True))
    ck(rc == 0, 'skip-turn 仍正常（实测 %d）' % rc)
    ck(len(calls) == N_ALL - 1, '少 1 步（turn_score 被跳过，实测 %d）' % len(calls))
    ck(calls and calls[0].startswith('chain_apply'), '第 1 步是 chain_apply（实测 %s）' % (calls[0] if calls else '无'))
    _restore(orig)

    print('H) --skip-archive 时不跑 archive → 少 1 步')
    orig, calls = _patch_run([0] * N_ALL)
    rc = rmr.cmd_finish(_mk_args(payload, md, skip_archive=True))
    ck(rc == 0, 'skip-archive 仍正常（实测 %d）' % rc)
    ck(len(calls) == N_ALL - 1, '少 1 步（archive 被跳过，实测 %d）' % len(calls))
    _restore(orig)

    print()
    print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
