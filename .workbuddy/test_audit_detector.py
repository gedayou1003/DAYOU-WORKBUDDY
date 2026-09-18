# -*- coding: utf-8 -*-
"""审计器自检（闸门的闸门）：证明 audit_pipeline 的「高危」判定**真的会红、也真的不误红**。

为什么必须有这个测试：
  2026-09-18 的审计里，4 个**自检型脚本**（chainlib / market_codes / qt_api /
  backtest_forecast_multiperiod）被报成「会打印失败字样却退出 0」的高危，实际它们的
  `❌` 是**表格渲染符号**、命中的「失败/无法」在 **docstring** 里 —— 纯假阳性。
  假阳性 = 噪声 = 闸门被无视。收紧判定后，必须用变异测试反过来证明：
    · 真·失败打印（无退出码）→ **必须**被标记
    · 假阳性形态（渲染符号 / docstring / raise）→ **必须不**被标记
  否则这次的「降噪」就等于把闸门一起关掉了。

用法：$PY .workbuddy/test_audit_detector.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('ap', os.path.join(HERE, 'audit_pipeline.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

fails = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


def scan(src):
    return m.scan_exit_codes({'x.py': src})


# ── 真阳性：这些形态必须被标记为高危 ──────────────────────────────
print('1) 真阳性（必须红）')
cases_red = [
    ('print + [FAIL]，无退出码',
     'def main():\n    print("[FAIL] 链文件缺失")\n\nif __name__ == "__main__":\n    main()\n'),
    ('except 里 print 失败后继续，无退出码',
     'def main():\n    try:\n        go()\n    except Exception as e:\n'
     '        print(f"失败: {e}")\n\nif __name__ == "__main__":\n    main()\n'),
    ('sys.stderr.write 报错，无退出码',
     'def main():\n    sys.stderr.write("无法解析链文件\\n")\n\n'
     'if __name__ == "__main__":\n    main()\n'),
    ('logging.error 报错，无退出码',
     'def main():\n    logging.error("不存在该标的")\n\n'
     'if __name__ == "__main__":\n    main()\n'),
]
for label, src in cases_red:
    _nc, risky = scan(src)
    ck('x.py' in risky, '%s → 被标记为高危' % label)

# ── 假阳性回归：这些形态必须**不**被标记 ─────────────────────────────
print('\n2) 假阳性回归（必须不红）')
cases_green = [
    ('表格渲染符号 ❌（无输出语句）',
     'def main():\n    dir_v = ("❌相反" if pct > 0.15 else "✅同向")\n'
     '    print(dir_v)\n\nif __name__ == "__main__":\n    main()\n'),
    ('docstring 里的「失败/无法/返回 1」',
     '"""doc：全部域名失败时抛错；缺 created_at 时返回 1（说明文字）。\n'
     '不存在的字段一律忽略。"""\ndef main():\n    pass\n\n'
     'if __name__ == "__main__":\n    main()\n'),
    ('注释里的「失败」',
     'def main():\n    # 逐个域名试，失败仅记录（注释）\n    pass\n\n'
     'if __name__ == "__main__":\n    main()\n'),
    ('raise（抛异常自带非零退出，不算失败当成功）',
     'def main():\n    raise RuntimeError("全部域名均失败")\n\n'
     'if __name__ == "__main__":\n    main()\n'),
]
for label, src in cases_green:
    _nc, risky = scan(src)
    ck('x.py' not in risky, '%s → 未被误标' % label)

# ── 有退出码就不该进任何清单 ────────────────────────────────────────
print('\n3) 已有失败退出码 → 两个清单都不进')
with_code = ('def main():\n    print("[FAIL] 缺数据")\n    return 1\n\n'
             'if __name__ == "__main__":\n    sys.exit(main())\n')
nc, risky = scan(with_code)
ck('x.py' not in risky and 'x.py' not in nc, 'return 1 + sys.exit(main()) → 完全出列')

# ── no_code 与 risky 的分工：无退出码但不打印失败 → 只在 no_code ──────
print('\n4) 无退出码但也不打印失败 → 只进 no_code，不进高危')
quiet = 'def main():\n    compute()\n\nif __name__ == "__main__":\n    main()\n'
nc, risky = scan(quiet)
ck('x.py' in nc and 'x.py' not in risky, '静默脚本进 no_code、不进高危（两级如实体现在数据上）')

print()
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
sys.exit(1 if fails else 0)
