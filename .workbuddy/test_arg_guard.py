# -*- coding: utf-8 -*-
"""参数守卫回归测试（2026-09-21 建）。

被测对象：手工解析 argv 的两个脚本的**非法入参行为**。
  · fetch_zsxq.py      —— --window 取值白名单
  · get_daily_ohlc.py  —— 整型入参（天数 / --ttl）+ 未知选项

为什么需要这个测试：
  两者旧实现都用 `except ValueError/IndexError: pass` **静默回退默认值**。
  fetch_zsxq 的后果最严重：`--window nooon`（拼错）会静默落回 morning 窗口
  （前一天 16:00 起），窗口无声变窄 —— 与 2026-09-21 晨报「漏掉整个周末」
  属同一族事故。get_daily_ohlc 则是 `--ttl abc` / `000001 abc` 静默用默认值。

**变异自证**（见本文件第 3 节）：
  断言若不能变红就等于没测。故测试会把两个脚本复制进 mkdtemp 沙箱，
  用正则反向变异回旧实现，要求变异体复现「rc=0 且静默通过」。
  变异不生效（正则失配）会直接判 FAIL，避免「测试没跑」伪装成「测试通过」。

退出码：0 全部通过 · 1 有断言失败。
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # silent-ok: 终端编码收口尽力而为，失败不影响结论
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
CST_ENV = dict(os.environ, PYTHONIOENCODING='utf-8')

fails = []
L = []


def ck(cond, msg):
    L.append('  [%s] %s' % ('OK  ' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


def run_script(script, args):
    return subprocess.run([PY, os.path.join(HERE, script)] + args, cwd=HERE,
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', env=CST_ENV)


def run_import(modname, argv):
    """以「指定 argv 后 import 模块」的方式测模块级参数守卫（不触发抓取）。"""
    code = 'import sys; sys.argv=%r; import %s as m; print("OK", m.WIN_START.isoformat())' \
           % (argv, modname)
    return subprocess.run([PY, '-c', code], cwd=HERE, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', env=CST_ENV)


# ============================================================ 1. fetch_zsxq
L.append('=' * 74)
L.append('1) fetch_zsxq.py · --window 白名单')
L.append('=' * 74)

for bad, why in (('nooon', '拼错的窗口名'), (None, '--window 后面缺值')):
    argv = ['fetch_zsxq.py', '--window'] + ([bad] if bad else [])
    r = run_import('fetch_zsxq', argv)
    first = (r.stderr or '').strip().splitlines()[0] if (r.stderr or '').strip() else ''
    L.append('  %-16s rc=%d  %s' % (why, r.returncode, first[:88]))
    ck(r.returncode == 1, '%s → 退出码 1（旧实现：静默落回 morning）' % why)
    ck('[FAIL]' in (r.stderr or ''), '%s → 有 [FAIL] 提示' % why)

# 四个合法窗口仍须可用，且窗口起点符合各自定义
EXPECT_START = {
    'morning': 'T16:00:00',    # 前一天 16:00
    'noon': 'T08:00:00',       # 当天 08:00
    'afternoon': 'T12:30:00',  # 当天 12:30
    'evening': 'T12:00:00',    # 当天 12:00
}
for w, needle in EXPECT_START.items():
    r = run_import('fetch_zsxq', ['fetch_zsxq.py', '--window', w])
    ok = r.returncode == 0 and needle in (r.stdout or '')
    L.append('  --window %-9s rc=%d  %s' % (w, r.returncode, (r.stdout or r.stderr or '').strip()[:70]))
    ck(ok, '合法窗口 %s 可用且起点含 %s' % (w, needle))

# 不传 --window → 默认 morning 语义必须保留
r = run_import('fetch_zsxq', ['fetch_zsxq.py'])
ck(r.returncode == 0 and 'T16:00:00' in (r.stdout or ''),
   '不传 --window 时仍为「前一天 16:00 起」的 morning')

# 环境变量优先级高于 --window（铁律：ZSXQ_WIN_START/END > --window）
env = dict(CST_ENV, ZSXQ_WIN_START='2026-01-02T03:00:00+08:00',
           ZSXQ_WIN_END='2026-01-02T04:00:00+08:00')
r = subprocess.run([PY, '-c',
                    "import sys; sys.argv=['fetch_zsxq.py','--window','evening'];"
                    "import fetch_zsxq as m; print(m.WIN_START.isoformat())"],
                   cwd=HERE, capture_output=True, text=True, encoding='utf-8',
                   errors='replace', env=env)
ck(r.returncode == 0 and '2026-01-02T03:00:00' in (r.stdout or ''),
   '环境变量 ZSXQ_WIN_START 仍覆盖 --window（窗口优先级铁律未被破坏）')

# ====================================================== 2. get_daily_ohlc
L.append('')
L.append('=' * 74)
L.append('2) get_daily_ohlc.py · 整型入参 + 未知选项')
L.append('=' * 74)

for args, why in (
    (['000001', 'abc'], '天数非整数'),
    (['000001', '1', '--ttl', 'abc'], '--ttl 非整数'),
    (['000001', '1', '--ttl='], '--ttl= 空值'),
    (['000001', '1', '--no-cach'], '选项拼错'),
):
    r = run_script('get_daily_ohlc.py', args)
    first = (r.stderr or '').strip().splitlines()[0] if (r.stderr or '').strip() else ''
    L.append('  %-16s rc=%d  %s' % (why, r.returncode, first[:88]))
    ck(r.returncode == 1, '%s → 退出码 1（旧实现：静默用默认值）' % why)
    ck('[FAIL]' in (r.stderr or ''), '%s → 有 [FAIL] 提示' % why)

# 正常路径：合法入参必须照常返回 JSON（网络不可用则记为 SKIP，不伪造通过）
r = run_script('get_daily_ohlc.py', ['000001', '1', '--no-cache'])
if r.returncode == 0:
    ok = '"close"' in (r.stdout or '') and '"pct_chg"' in (r.stdout or '')
    L.append('  正常取数        rc=0  字段齐全=%s' % ok)
    ck(ok, '合法入参仍返回含 close / pct_chg 的 JSON')
else:
    L.append('  正常取数        rc=%d  [SKIP] 网络不可用，跳过（不视为通过）' % r.returncode)

# ================================================ 3. 变异自证（防止假绿）
L.append('')
L.append('=' * 74)
L.append('3) 变异自证：反向变异回旧实现后必须复现「静默通过」')
L.append('=' * 74)

def mutate_fetch(s):
    """把 fetch_zsxq.py 的窗口守卫还原成旧实现（try/except IndexError: pass）。

    用「标记切片」而非单个正则：守卫块里**有两个 sys.exit(1)**（缺值 / 未知取值），
    用非贪婪正则只会吞掉第一个，剩下那个仍会拦住非法窗口 → 变异不生效，
    行为上看是「变异体没复现静默」，实际是**变异本身没做对**（假红）。
    """
    i = s.index('WINDOWS = ("morning", "noon", "afternoon", "evening")')
    j = s.index('def _resolve_window')
    old = ('_win_arg = None\n'
           'if "--window" in sys.argv:\n'
           '    try:\n'
           '        _win_arg = sys.argv[sys.argv.index("--window") + 1]\n'
           '    except IndexError:\n'
           '        pass\n'
           '\n\n')
    return s[:i] + old + s[j:]


MUT_OHLC = (
    re.compile(r"        elif a == '--ttl':\n"
               r"            ttl = _int_arg\(_need_val\(argv, i, '--ttl'\), '--ttl'\)\n"
               r"            i \+= 1\n"
               r"        elif a\.startswith\('--ttl='\):\n"
               r"            ttl = _int_arg\(a\.split\('=', 1\)\[1\], '--ttl'\)\n"
               r"        elif a\.startswith\('-'\):\n"
               r"            # 拼错的选项旧实现会被当成位置参数或直接吞掉；现在显式报错\n"
               r"            raise ValueError\('未知选项 %r' % a\)\n", re.M),
    "        elif a == '--ttl':\n"
    "            i += 1\n"
    "            if i < len(argv):\n"
    "                try:\n"
    "                    ttl = int(argv[i])\n"
    "                except ValueError:\n"
    "                    pass\n"
    "        elif a.startswith('--ttl='):\n"
    "            try:\n"
    "                ttl = int(a.split('=', 1)[1])\n"
    "            except ValueError:\n"
    "                pass\n",
)

sb = tempfile.mkdtemp(prefix='wb_argguard_')
try:
    # 被测脚本 + 同目录真实存在的依赖一律连带复制（否则 ModuleNotFoundError 假失败）
    for f in ('fetch_zsxq.py', 'get_daily_ohlc.py', 'market_codes.py', 'qt_api.py'):
        src = os.path.join(HERE, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(sb, f))

    # ① fetch_zsxq：标记切片变异
    p = os.path.join(sb, 'fetch_zsxq.py')
    s = io.open(p, encoding='utf-8').read()
    try:
        s2 = mutate_fetch(s)
    except ValueError:  # silent-ok: 变异体构造失败即置 None，下方断言会直接判 FAIL
        s2 = None
    ck(s2 is not None, '变异体 fetch_zsxq.py 构造成功（标记缺失即代表源码结构变了，须同步改测试）')
    if s2 is not None:
        ck('WINDOWS = (' not in s2 and 'sys.exit(1)' not in s2.split('def _resolve_window')[0],
           '变异体 fetch_zsxq.py 两个 sys.exit 守卫均已移除（非贪婪正则只吞一个的坑）')
        io.open(p, 'w', encoding='utf-8').write(s2)

    # ② get_daily_ohlc：正则变异
    p2 = os.path.join(sb, 'get_daily_ohlc.py')
    s = io.open(p2, encoding='utf-8').read()
    s2, n = MUT_OHLC[0].subn(MUT_OHLC[1], s)
    ck(n == 1, '变异体 get_daily_ohlc.py 构造成功（正则命中 %d 处，0 处代表正则已失效）' % n)
    io.open(p2, 'w', encoding='utf-8').write(s2)

    # 变异体：非法入参必须**复现静默通过**（rc=0）
    r = subprocess.run([PY, '-c',
                        "import sys; sys.argv=['fetch_zsxq.py','--window','nooon'];"
                        "import fetch_zsxq as m; print('SILENT', m.WIN_START.isoformat())"],
                       cwd=sb, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', env=CST_ENV)
    L.append('  变异体 --window nooon     rc=%d  %s' % (r.returncode, (r.stdout or r.stderr or '').strip()[:64]))
    ck(r.returncode == 0, '变异体在非法窗口上静默通过 → 说明本测试确实在测这条行为')

    r = subprocess.run([PY, os.path.join(sb, 'get_daily_ohlc.py'), '000001', '1', '--ttl', 'abc'],
                       cwd=sb, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', env=CST_ENV)
    L.append('  变异体 --ttl abc          rc=%d' % r.returncode)
    ck(r.returncode == 0, '变异体在非法 --ttl 上静默通过 → 同上')
finally:
    shutil.rmtree(sb, ignore_errors=True)

# ============================================================== 汇总
n_ck = len([x for x in L if x.strip().startswith('[OK') or x.strip().startswith('[FAIL')])
L.append('')
L.append('=' * 74)
L.append('RESULT: %s（%d 项断言，失败 %d 项）'
         % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails), n_ck, len(fails)))
for f in fails:
    L.append('  FAIL: %s' % f)
L.append('=' * 74)

print('\n'.join(L))
sys.exit(1 if fails else 0)
