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
import re
import shutil
import subprocess
import sys
import tempfile

WB = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
# 默认测仓库里的正本；设 FSVG_SCRIPT 可指向变异副本，用于负例验证
SCRIPT = os.environ.get('FSVG_SCRIPT') or os.path.join(WB, 'gen_forecast_svg.py')

RESULTS = []


def local_deps():
    """正本脚本 import 的、且确实存在于 `.workbuddy/` 的同目录模块文件名。

    为什么需要它（2026-09-18 修复，教训 6）
    --------------------------------------
    `gen_forecast_svg.py` 在 9/18 的显示名改造中新增了
    `from display_names import scrub, scrub_all`，而本测试的沙箱**只复制脚本正本** →
    沙箱里 `ModuleNotFoundError`，30 条断言里 19 条报这个错。
    表象是「脚本坏了」，真相是「测试沙箱缺依赖」—— 这道闸门整整哑了一轮**没人发现**，
    因为没人会去看一个自己没跑过的测试。

    故改为：扫正本脚本里的 `import X` / `from X import`，凡是 `.workbuddy/` 下真实存在
    的同目录模块一律连带复制。以后再加同目录依赖不会再重演。

    注意依赖从 **WB（仓库 .workbuddy/）** 解析而非 `dirname(SCRIPT)`：
    负例测试会把变异体写到临时目录再跑，那里没有依赖模块。
    """
    src = open(os.path.join(WB, 'gen_forecast_svg.py'), encoding='utf-8').read()
    names = set()
    for m in re.finditer(r'^\s*(?:from\s+([A-Za-z_]\w*)\s+import|import\s+([A-Za-z_]\w*))',
                         src, re.M):
        names.add(m.group(1) or m.group(2))
    return [n + '.py' for n in sorted(names) if os.path.exists(os.path.join(WB, n + '.py'))]


def check(desc, cond, extra=''):
    RESULTS.append((bool(cond), desc))
    print('   %s %s' % ('PASS' if cond else 'FAIL', desc))
    if not cond and extra:
        print('        %s' % extra)


def is_clean_error(blob):
    """是有意报错，而不是崩在深处。"""
    return ('[FAIL]' in blob) and ('Traceback' not in blob)


# ---------- 合成链素材 ----------

def lv_full(date='2026-01-02'):
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


ACT = {'date': '2026-01-01', 'open': 3895.0, 'high': 3920.0,
       'low': 3885.0, 'close': 3905.0, 'pct_chg': 0.26}

# 合成记录用**真实日期形态**的 id（2026-09-24 复审 R4 修正）
# ---------------------------------------------------------------
# 原先用 `T-2026-01-02` 这种「带前缀的假日期」，理由是"一眼看出是合成数据"。
# 但 R4 让 `gen_forecast_svg.py` 开始**从 id 里正则抽日期段**（目标是按 target 匹配 actual），
# 于是 `T-2026-01-02` 抽不出日期 → 脚本走了「target 不可解析」的退化分支 → 
# actual 选不到 → 报「链中找不到含 open/high/low/close 的 verified.review.actual」，
# **本文件 8 条断言集体假失败**（表象是「脚本坏了」，真相是「测试素材不再符合现实形态」）。
#
# 所以改用真实日期：**测试素材必须与生产数据的形态一致**，
# 否则一旦生产逻辑开始解析那个形态，测试就会以"脚本坏了"的表象报假红。
# 「一眼看出是合成数据」这个诉求改由 `T-` 前缀挪到 **levels.label / signals 的中文文案**去满足
# （测试沙箱本来就是临时目录，不会与真实数据混）。
V_ID = '2026-01-01'          # verified 记录 id
P_ID = '2026-01-02'          # pending  记录 id


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
        # 连带复制同目录依赖模块（2026-09-18：display_names.py 缺失曾让 19 条断言假失败）
        for dep in local_deps():
            shutil.copy2(os.path.join(WB, dep), os.path.join(wb, dep))
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
expect_fail('A 无 pending', [rec_verified(V_ID)],
            must_mention=['pending', '--pred'])

# B. --pred 指向不存在的 id → 报错
expect_fail('B 坏 --pred', [rec_verified(V_ID)],
            args=['--pred', 'T-NOT-EXIST'], must_mention=['T-NOT-EXIST'])

# C. pending 的 levels 不完整 → 报错
bad_lv = lv_full()
del bad_lv['down_lower']
expect_fail('C levels 残缺',
            [rec_verified(V_ID), rec_pending(P_ID, bad_lv)],
            must_mention=['down_lower'])

# D. 没有任何 verified 带 actual → 报错
expect_fail('D 无 actual',
            [rec_verified(V_ID, with_actual=False), rec_pending(P_ID)],
            must_mention=['open', 'close'])

# F1. levels 缺 date 且未给 --out → 报错（不得退化成写死日期文件名）
no_date = lv_full()
no_date.pop('date')
CH_NODATE = [rec_verified(V_ID), rec_pending(P_ID, no_date)]
blob = expect_fail('F1 缺 date 无 --out', CH_NODATE, with_out=False,
                   must_mention=['date', '--out'])
check('F1 缺 date 无 --out：未退化成 2026-08-31 文件名', '2026-08-31' not in blob, blob[:200])

# F2. levels 缺 date 但给了 --out → 应正常出图（输出路径与 date 无关）
rc, so, se, c = run(CH_NODATE, with_out=True)
check('F2 缺 date 有 --out：正常出图（退出码 0）', rc == 0, 'rc=%d %s' % (rc, (so + se)[:200]))
check('F2 缺 date 有 --out：产出了 SVG', c is not None and len(c) > 2000,
      'bytes=%s' % (len(c) if c else -1))

# E. 正常路径：产出 SVG，且两次运行字节完全一致
CH = [rec_verified(V_ID), rec_pending(P_ID)]
rc1, so1, se1, c1 = run(CH)
ok1 = (rc1 == 0 and c1 is not None)
check('E 正常路径：退出码 0 且产出 SVG', ok1, 'rc=%d stdout=%s' % (rc1, so1[:200]))
check('E 正常路径：SVG 非空（>2000 字节）', ok1 and len(c1) > 2000,
      'bytes=%d' % (len(c1) if c1 else -1))
check('E 正常路径：stdout 回显 pred id', P_ID in so1, so1[:200])

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
