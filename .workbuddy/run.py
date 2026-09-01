# -*- coding: utf-8 -*-
"""统一运行入口：用 venv python 执行 .workbuddy 下的脚本，规避系统 python 缺 pandas/markdown 的问题。

背景：scan_sw_realtime.py / scan_ths.py / backtest_*.py / md_to_html_report.py 等脚本
      依赖 pandas / markdown / akshare / httpx，这些只装在 venv（~/.workbuddy/binaries/python/envs/default）。
      用系统 `python` 直接跑会报 ModuleNotFoundError。本入口统一走 venv，一次写对、处处不报错。

用法（在项目根目录）：
    python .workbuddy/run.py <脚本名.py> [参数...]
    等价于手动：<venv>/Scripts/python.exe .workbuddy/<脚本名.py> [参数...]

示例：
    python .workbuddy/run.py scan_sw_realtime.py
    python .workbuddy/run.py fetch_all.py --window noon
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.expanduser("~/.workbuddy/binaries/python/envs/default/Scripts/python.exe")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)
    script = sys.argv[1]
    args = sys.argv[2:]
    script_path = script if os.path.isabs(script) else os.path.join(HERE, script)
    if not os.path.exists(script_path):
        print(f'❌ 脚本不存在：{script_path}')
        sys.exit(1)
    if os.path.exists(VENV_PY):
        py = VENV_PY
    else:
        py = sys.executable
        print(f'⚠️ venv python 不存在（{VENV_PY}），回退当前解释器 {py}')
    os.chdir(os.path.dirname(HERE))  # 切到项目根目录，与手动在根目录跑一致
    sys.exit(subprocess.call([py, script_path] + args))


if __name__ == '__main__':
    main()
