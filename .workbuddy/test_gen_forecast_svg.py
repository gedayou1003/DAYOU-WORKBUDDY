# -*- coding: utf-8 -*-
"""gen_forecast_svg.py 回归测试（§四 待办 #11「兜底日期写死」的验证件）。

背景（2026-09-17 加固）：旧版在「链上没有可用 pending」或「没有 verified.actual」时
**静默回退到写死的 2026-08-31 数据**。后果比崩溃严重 —— 9 月的报告会被塞进一张
8/31 的走势图：图看着正常、四个价位全错，而调用方只看到一行 `SVG written`。

本测试用**合成链**（临时目录里放一份假的 forecast_chain.json）驱动真实脚本副本，
四条失败路径 + 两条正常路径。断言分两类：
  1) **必须非零退出 + 不产出 SVG + 有明确中文诊断**（且**不得**是裸 traceback）
  2) 正常路径**字节稳定**（防止改动悄悄改变图形输出）

⚠️ 关于「无 traceback」这条：2026-09-17 负例验证发现，若把 levels 完整性校验删掉，
脚本会崩在 `float(lv['down_lower']['price'])` 抛 KeyError —— 非零退出、报错文本里
恰好含 'down_lower'、也没出图，前三条断言全部误判为通过。故必须显式排除裸崩溃。

用法：python .workbuddy/test_gen_forecast_svg.py
      FSVG_SCRIPT=<变异体路径> python .workbuddy/test_gen_forecast_svg.py   # 负例验证用
退出码：0 全通过 / 1 有失败
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

WB = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
# 默认测仓库里的正本；设 FSVG_SCRIPT 可指向变异副本，用于负例验证
SCRIPT = os.environ.get('FSVG_SCRIPT') or os.path.join(WB, 'gen_forecast_svg.py')

RESULTS = []


def check(desc, cond, extra=''):
    RESULTS.append((bool(cond), desc))
    print('   %s %s' % ('PASS' if cond else 'FAIL', desc))
    if not cond and extra:
        print('        %s' % extra)


def is_clean_error(blob):
    """是有意报错，而不是崩在深处。"""
    return ('[FAIL]' in blob) and ('Traceback' not in blob)


# ---------- 合成链素材 ----------

def lv_full(date='T-2026-01-02'):
    return {
        'date': date,
        'now': 3900.0,
        'decision': {'price': 3910.0, 'label': '决策位'},
        'up_target': {'price': 3960.0, 'label': '上目标'},
        'down_support': {'price': 3880.0, 'label': '核心支撑'},
        'down_lower': {'price': 3850.0, 'label': '下目标'},
        'signals': ['合成信号 A', '合成信号 B'],
        'prob': {'up': 0.3, 'range': 0.4, 'down': 0.3},
    }


ACT = {'date': 'T-2026-01-01', 'open': 3895.0, 'high': 3920.0,
       'low': 3885.0, 'close': 3905.0, 'pct_chg': 0.26}


def rec_verified(rid, with_actual=True):
    r = {'id': rid, 'status': 'verified', 'levels': lv_full()}
    r['review'] = {'actual': dict(ACT)} if with_actual else {'direction_verdict': '命中'}
    return r


def rec_pending(rid, levels=None):
    return {'id': rid, 'status': 'pending',
            'levels': levels if levels is not None else lv_full()}


def run(chain_records, args=None, with_out=True):
    """临时沙箱里跑一次脚本。返回 (returncode, stdout, stderr, svg_bytes 或 None)。

    沙箱布局（刻意让默认输出目录**存在**，否则「非零退出」可能只是因为目录不存在，
    断言会假性通过）：
        <tmp>/wb/gen_forecast_svg.py      ← 脚本副本（HERE = <tmp>/wb）
        <tmp>/outputs/                    ← 默认输出目录（HERE/../outputs）
        <tmp>/wb/out/x.svg                ← 显式 --out 的目标
    """
    d = tempfile.mkdtemp(prefix='wbtest_fsvg_')
    try:
        wb = os.path.join(d, 'wb')
        os.makedirs(wb)
        os.makedirs(os.path.join(d, 'outputs'))       # 默认输出目录必须存在
        os.makedirs(os.path.join(wb, 'out'))          # 显式 --out 目标目录
        shutil.copy2(SCRIPT, os.path.join(wb, 'gen_forecast_svg.py'))
        with open(os.path.join(wb, 'forecast_chain.json'), 'w', encoding='utf-8') as f:
            json.dump(chain_records, f, ensure_ascii=False, indent=2)

        a = list(args or [])
        svg = os.path.join(wb, 'out', 'x.svg')
        if with_out and '--out' not in a:
            a += ['--out', svg]
        else:
            # 不给 --out 时脚本会写默认路径，两个候选都收
            svg = None

        r = subprocess.run([PY, os.path.join(wb, 'gen_forecast_svg.py')] + a,
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', cwd=wb)

        cands = [os.path.join(wb, 'out', 'x.svg')]
        od = os.path.join(d, 'outputs')
        if os.path.isdir(od):
            cands += [os.path.join(od, f) for f in os.listdir(od)]
        content = None
        for p in cands:
            if os.path.exists(p):
                with open(p, 'rb') as f:
                    content = f.read()
                break
        return r.returncode, r.stdout or '', r.stderr or '', content
    finally:
        shutil.rmtree(d, ignore_errors=True)


def expect_fail(tag, chain, args=None, with_out=True, must_mention=()):
    """统一跑一条失败路径并做四项断言。"""
    rc, so, se, c = run(chain, args=args, with_out=with_out)
    blob = so + se
    check('%s：非零退出' % tag, rc != 0, 'rc=%d' % rc)
    check('%s：未产出 SVG' % tag, c is None, 'bytes=%s' % (len(c) if c else -1))
    check('%s：有意报错而非裸崩溃' % tag, is_clean_error(blob), blob.strip()[-260:])
    for kw in must_mention:
        check('%s：诊断提到 %s' % (tag, kw), kw in blob, blob[:200])
    return blob


# ---------- 用例 ----------

print('=== gen_forecast_svg 回归 ===')
print('')

# A. 链上无 pending → 报错，且不得渲染陈旧数据
expect_fail('A 无 pending', [rec_verified('T-2026-01-01')],
            must_mention=['pending', '--pred'])

# B. --pred 指向不存在的 id → 报错
expect_fail('B 坏 --pred', [rec_verified('T-2026-01-01')],
            args=['--pred', 'T-NOT-EXIST'], must_mention=['T-NOT-EXIST'])

# C. pending 的 levels 不完整 → 报错
bad_lv = lv_full()
del bad_lv['down_lower']
expect_fail('C levels 残缺',
            [rec_verified('T-2026-01-01'), rec_pending('T-2026-01-02', bad_lv)],
            must_mention=['down_lower'])

# D. 没有任何 verified 带 actual → 报错
expect_fail('D 无 actual',
            [rec_verified('T-2026-01-01', with_actual=False), rec_pending('T-2026-01-02')],
            must_mention=['open', 'close'])

# F1. levels 缺 date 且未给 --out → 报错（不得退化成写死日期文件名）
no_date = lv_full()
no_date.pop('date')
CH_NODATE = [rec_verified('T-2026-01-01'), rec_pending('T-2026-01-02', no_date)]
blob = expect_fail('F1 缺 date 无 --out', CH_NODATE, with_out=False,
                   must_mention=['date', '--out'])
check('F1 缺 date 无 --out：未退化成 2026-08-31 文件名', '2026-08-31' not in blob, blob[:200])

# F2. levels 缺 date 但给了 --out → 应正常出图（输出路径与 date 无关）
rc, so, se, c = run(CH_NODATE, with_out=True)
check('F2 缺 date 有 --out：正常出图（退出码 0）', rc == 0, 'rc=%d %s' % (rc, (so + se)[:200]))
check('F2 缺 date 有 --out：产出了 SVG', c is not None and len(c) > 2000,
      'bytes=%s' % (len(c) if c else -1))

# E. 正常路径：产出 SVG，且两次运行字节完全一致
CH = [rec_verified('T-2026-01-01'), rec_pending('T-2026-01-02')]
rc1, so1, se1, c1 = run(CH)
ok1 = (rc1 == 0 and c1 is not None)
check('E 正常路径：退出码 0 且产出 SVG', ok1, 'rc=%d stdout=%s' % (rc1, so1[:200]))
check('E 正常路径：SVG 非空（>2000 字节）', ok1 and len(c1) > 2000,
      'bytes=%d' % (len(c1) if c1 else -1))
check('E 正常路径：stdout 回显 pred id', 'T-2026-01-02' in so1, so1[:200])

rc2, so2, se2, c2 = run(CH)
check('E 正常路径：两次运行字节一致（确定性）',
      c1 is not None and c2 is not None and c1 == c2,
      '%s vs %s' % (len(c1) if c1 else -1, len(c2) if c2 else -1))

# 透明化：明确打印被测脚本，避免误以为测的是变异体（或反之）
print('被测脚本：%s' % SCRIPT)
print('')

# ---------- 汇总 ----------
bad = [x for ok, x in RESULTS if not ok]
print('')
print('用例合计 %d，通过 %d，失败 %d'
      % (len(RESULTS), len(RESULTS) - len(bad), len(bad)))
if bad:
    print('')
    for x in bad:
        print('  FAILED: %s' % x)
    sys.exit(1)
print('全部通过。')
sys.exit(0)
