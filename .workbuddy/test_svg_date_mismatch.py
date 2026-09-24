# -*- coding: utf-8 -*-
"""验证 gen_forecast_svg.py 的走势图身份守卫（两代）。

第一代（2026-09-24 事故当天加的）：「levels.date 与记录 id 日期不一致」+「--out 覆盖别人的图」。
第二代（2026-09-24 复审 R2-1 / R4 加的）：**SVG 自述身份** + **actual 按 target 匹配**。

为什么要单独验：这是 2026-09-24 真实事故（9/24 晨报覆盖了 9/23 午间档的图，
两张图 md5 完全相同、不可恢复）。守卫必须
  ①在**不一致时真的报错**（不能静默按 date 命名），
  ②在**一致时仍然放行**（不能把正常路径也堵死）。
只做①就是又一个「假闸门」。

R2-1 的意义（复审结论）：事故当天加的守卫只是「不让写进去」，
但**已经写坏的图无法被任何机器发现** —— SVG 本体不含身份信息，
`check_integrity.py` 也从不看 `.svg`。故必须让图**自述自己是谁**，
再由校验器核对「文件名日期 == 自述目标日」。
本文件同时验两代守卫，保证新版没有把旧版的防线拆掉。
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # silent-ok: 终端编码收口尽力而为
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(HERE, 'gen_forecast_svg.py')
PY = sys.executable

FAILS = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        FAILS.append(msg)


# 完整的最小 levels（字段齐才能走到「推文件名」那一步）
def lv(date):
    return {
        'date': date, 'now': 3900.0, 'band': {'low': 3880.0, 'high': 3920.0},
        'decision': {'price': 3910.0, 'label': '决策位'},
        'up_target': {'price': 3960.0, 'label': '上目标'},
        'down_lower': {'price': 3850.0, 'label': '下目标'},
        'down_support': {'price': 3860.0, 'label': '下支撑'},
        'prob': {'up': 0.4, 'range': 0.35, 'down': 0.25},
        'signals': ['测试'],
    }


def run(rid, d, with_out, out_name='x.svg', precreate=False, force=False,
        actuals=None, target=None):
    """在临时目录里造一个最小链，跑脚本，返回 (rc, 输出文本)

    ⚠️ 链格式与前置条件（本测试初版连踩两坑，记下来免得再犯）：
      1. `forecast_chain.json` 是**裸 list**，不是 `{'records': [...]}`
         （写成 dict 会 `AttributeError: 'str' object has no attribute 'get'`）。
      2. 脚本还要求链里**另有一条 verified 记录、且带 review.actual 的 open/high/low/close**
         （走势图要叠加真实走势）。只给 pending 会先撞这条前置检查，
         根本走不到「推默认文件名」那一步 —— 于是**测试看起来红了，其实测的不是目标守卫**。
         故这里必须补一条 verified 的 actual 记录。
      3. 脚本 `from display_names import scrub` 是按**自身所在目录**导入的，
         拷脚本时必须连 `display_names.py` 一起拷，否则 ModuleNotFoundError。

    precreate=True 时先占位一个同名文件，用于测「已存在 → 拒绝覆盖」。

    2026-09-24 复审新增参数（用于测 R4「actual 按 target 匹配」）：
      actuals=[('2026-01-01', {...OHLC}), ...]  自定义链上的 verified 记录集；
      target='2026-01-03 全天'                 给 pending 记录显式 target。
    """
    tmp = tempfile.mkdtemp(prefix='svgdate_')
    wb = os.path.join(tmp, '.workbuddy')
    out = os.path.join(tmp, 'outputs')
    os.makedirs(wb)
    os.makedirs(out)
    if actuals is None:
        chain = [
            {'id': 'T-2026-01-01', 'status': 'verified', 'report_type': 'morning',
             'levelsec': 'T',
             'review': {'actual': {'date': '2026-01-01', 'open': 3895.0, 'high': 3920.0,
                                   'low': 3880.0, 'close': 3905.0}}},
            {'id': rid, 'status': 'pending', 'levels': lv(d)},
        ]
    else:
        chain = []
        for ad, ohlc in actuals:
            chain.append({'id': 'V-%s' % ad, 'status': 'verified', 'report_type': 'morning',
                          'review': {'actual': dict(ohlc, date=ad)}})
        pend = {'id': rid, 'status': 'pending', 'levels': lv(d)}
        if target:
            pend['target'] = target
        chain.append(pend)
    with io.open(os.path.join(wb, 'forecast_chain.json'), 'w', encoding='utf-8') as f:
        json.dump(chain, f, ensure_ascii=False)
    # 脚本用 HERE/.. 定位项目根 → 拷一份脚本到 tmp/.workbuddy 下即可
    # ⚠️ 还要拷 display_names.py：脚本 `from display_names import scrub` 是按
    #    **自身所在目录**导入的，只拷主脚本会 ModuleNotFoundError（本测试初版即踩此坑）。
    for fn in ('gen_forecast_svg.py', 'display_names.py'):
        with io.open(os.path.join(HERE, fn), encoding='utf-8') as f:
            src = f.read()
        with io.open(os.path.join(wb, fn), 'w', encoding='utf-8') as f:
            f.write(src)
    args = [PY, os.path.join(wb, 'gen_forecast_svg.py'), '--pred', rid]
    if with_out:
        tgt = os.path.join(out, out_name)
        if precreate:
            with io.open(tgt, 'w', encoding='utf-8') as f:
                f.write('<svg>占位（模拟别的档位已存在的图）</svg>')
        args += ['--out', tgt]
    else:
        tgt = None
    if force:
        args += ['--force']
    p = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=tmp)
    blob = (p.stdout or '') + (p.stderr or '')
    svg_text = None
    if tgt:
        svg_path = tgt
    elif rid:
        # 无 --out 时默认落 outputs/000001_forecast_<date>.svg（date 取自 levels.date）
        svg_path = os.path.join(out, '000001_forecast_%s.svg' % d.replace('/', '-'))
    else:
        svg_path = None
    if svg_path and os.path.exists(svg_path):
        svg_text = io.open(svg_path, encoding='utf-8').read()
    return p.returncode, blob, svg_text


print('=== 守卫：levels.date 与记录 id 日期不一致（2026-09-24 事故复现）===')
rc, blob, _ = run('2026-09-24-morning', '2026-09-23', with_out=False)
ck(rc != 0, '不一致 + 无 --out → 必须非零退出（实测 rc=%d）' % rc)
ck('不一致' in blob, '错误信息须点明「不一致」')
ck('--out' in blob, '错误信息须给出补救办法（--out）')
ck('覆盖' in blob or '事故' in blob, '错误信息须点明覆盖风险')

print('=== 反向：一致时必须放行（不能把正常路径堵死）===')
rc, blob, _ = run('2026-09-24-morning', '2026-09-24', with_out=False)
ck(rc == 0, '一致 + 无 --out → 必须正常出图（实测 rc=%d）' % rc)

print('=== 反向：不一致但给了 --out → 应放行（--out 与 date 无关）===')
rc, blob, _ = run('2026-09-24-morning', '2026-09-23', with_out=True)
ck(rc == 0, '不一致 + 显式 --out → 正常出图（实测 rc=%d）' % rc)

print('=== 反向：id 无日期段（非 YYYY-MM-DD 前缀）→ 跳过该校验，不误伤 ===')
rc, blob, _ = run('MUTANT', '2026-09-23', with_out=False)
ck(rc == 0, 'id 无日期段 → 不误报（实测 rc=%d）' % rc)

# ── 2026-09-24 复审补充：覆盖守卫必须**不区分路径来源** ──────────────────
# 上一版只堵了「默认路径按 date 命名」，而真实事故是**通过显式 --out 打进去的**
# （9/23 的图与 9/24 的图 md5 完全相同，证明覆盖已发生且不可恢复）。
# 所以这里专门测 --out 路径：往「别人的图」上写必须被拒。
print('=== 覆盖守卫（--out 路径）：不得毁掉别的档位的图 ===')

rc, blob, _ = run('2026-09-24-morning', '2026-09-24', with_out=True,
                  out_name='000001_forecast_2026-09-23.svg', precreate=True)
ck(rc != 0, '--out 指向已存在的**别的档位**图 → 必须拒绝（实测 rc=%d）' % rc)
ck('拒绝覆盖' in blob or '覆盖' in blob, '错误信息须点明「覆盖」')
ck('--force' in blob, '错误信息须给出逃生办法（--force）')

rc, blob, _ = run('2026-09-24-morning', '2026-09-24', with_out=True,
                  out_name='000001_forecast_2026-09-24.svg', precreate=True)
ck(rc == 0, '--out 指向**自己的**图（同日重跑）→ 必须放行（实测 rc=%d）' % rc)

rc, blob, _ = run('2026-09-24-morning', '2026-09-24', with_out=True,
                  out_name='000001_forecast_2026-09-23.svg', precreate=True, force=True)
ck(rc == 0, '--force 显式越过 → 必须放行（实测 rc=%d）' % rc)

rc, blob, _ = run('2026-09-24-morning', '2026-09-24', with_out=True,
                  out_name='brand_new.svg', precreate=False)
ck(rc == 0, '--out 指向不存在的文件 → 必须放行（实测 rc=%d）' % rc)

# ── R2-1：SVG 必须**自述身份**（让「已经写坏的图」也能被机器发现） ─────────
# 复审结论：事故当天加的守卫只做到「不让写进去」，而**写坏的图本身无从识别** ——
# SVG 不含任何身份信息，check_integrity 也从不读 .svg。
# 故生成器必须把 pred= / date= / actual= 写进 <title>/<desc>，校验器才能核对。
print('=== R2-1：SVG 自述身份（<title>/<desc> 含 pred= / date= / actual=）===')
rc, blob, svg = run('2026-09-24-morning', '2026-09-24', with_out=True,
                    out_name='own.svg')
ck(rc == 0, '正常出图（实测 rc=%d）' % rc)
ck(svg is not None, 'SVG 文件已生成')
if svg:
    ck('<title>' in svg, 'SVG 须含 <title>（人肉排查时一眼看出是哪一档）')
    ck('<desc>' in svg, 'SVG 须含 <desc>（机器核对的载体）')
    ck('pred=2026-09-24-morning' in svg, '自述须含 pred=<记录 id>')
    ck('date=2026-09-24' in svg, '自述须含 date=<目标日>')
    ck('actual=' in svg, '自述须含 actual=<实际叠加的 actual 日期>（9/24 事故正是叠错了日子）')
    # 关键：自述的 date 必须取「目标日」，不是 levels.date（后者可能被填成基准日）
    rc2, blob2, svg2 = run('2026-09-24-morning', '2026-09-23', with_out=True,
                           out_name='baseday.svg')
    ck(rc2 == 0, 'levels.date 填成基准日 + 显式 --out → 放行（实测 rc=%d）' % rc2)
    if svg2:
        ck('date=2026-09-24' in svg2,
           '⚠️ 自述 date 须取**记录 id 的目标日**(2026-09-24)，'
           '而非 levels.date 的基准日(2026-09-23) —— 否则校验器会被数据里的错值带歪')
        ck('date=2026-09-23' not in svg2, '自述不得把基准日写成目标日')

# ── R4：actual 必须按 **target** 匹配，不是「链上最后一条」 ────────────────
# 旧实现取「链中最后一条带完整 OHLC 的 verified」：
#   · --pred <历史记录> 重绘时 → 叠加的是**今天**的走势（画成"历史预判 + 未来走势"）；
#   · target 与 actual.date 不等时（*-close 档 target=次日、周末档 target 下周一）→ 靠顺序蒙对。
print('=== R4：actual 按 target 匹配（不得取"链上最后一条"）===')

_ohlc = lambda c: {'open': 3895.0, 'high': 3920.0, 'low': 3880.0, 'close': c}
# 目标 2026-01-05，链上有 01-02 / 01-03 / 01-05 三天的 actual（01-05 是最接近且不晚于）
rc, blob, svg = run('2026-01-05-morning', '2026-01-05', with_out=True, out_name='t4.svg',
                    actuals=[('2026-01-02', _ohlc(3901.0)),
                             ('2026-01-03', _ohlc(3902.0)),
                             ('2026-01-05', _ohlc(3905.0))],
                    target='2026-01-05 全天（周一）')
ck(rc == 0, '出图成功（实测 rc=%d）' % rc)
ck('actual_date=2026-01-05' in blob, 'target=01-05 → 须取 01-05 的 actual（输出：%s）'
   % [l for l in blob.splitlines() if 'actual_date' in l])
if svg:
    ck('actual=2026-01-05' in svg, 'SVG 自述的 actual 须为 2026-01-05')

# target 当天还没收盘（链上只有更早的 actual）→ 取「最近且不晚于」的那条，不得取未来
rc, blob, svg = run('2026-01-06-morning', '2026-01-06', with_out=True, out_name='t4b.svg',
                    actuals=[('2026-01-02', _ohlc(3901.0)),
                             ('2026-01-05', _ohlc(3905.0)),
                             ('2026-01-07', _ohlc(3907.0))],   # 01-07 是"未来"，不得用
                    target='2026-01-06 全天（周二）')
ck(rc == 0, '出图成功（实测 rc=%d）' % rc)
ck('actual_date=2026-01-05' in blob,
   'target=01-06 而链上无 01-06 → 须取最近且**不晚于**的 01-05，不得取未来的 01-07'
   '（输出：%s）' % [l for l in blob.splitlines() if 'actual_date' in l])

# 反向：target 当天有 actual 时必须取当天，而不是「链上最后一条」（01-07）
rc, blob, svg = run('2026-01-07-morning', '2026-01-07', with_out=True, out_name='t4c.svg',
                    actuals=[('2026-01-02', _ohlc(3901.0)),
                             ('2026-01-05', _ohlc(3905.0)),
                             ('2026-01-07', _ohlc(3907.0))],
                    target='2026-01-07 全天（周三）')
ck('actual_date=2026-01-07' in blob, 'target 当天有 actual → 须取当天（输出：%s）'
   % [l for l in blob.splitlines() if 'actual_date' in l])

# 旧行为的回归靶子：若还取"链上最后一条"，下面这条会错拿 01-05 而非 01-02
rc, blob, svg = run('2026-01-02-morning', '2026-01-02', with_out=True, out_name='t4d.svg',
                    actuals=[('2026-01-02', _ohlc(3901.0)),
                             ('2026-01-05', _ohlc(3905.0))],
                    target='2026-01-02 全天（周五）')
ck('actual_date=2026-01-02' in blob,
   '重绘历史档（target=01-02）→ 须取 01-02 而**不是**链上最后一条 01-05'
   '（这正是旧实现的 bug；输出：%s）' % [l for l in blob.splitlines() if 'actual_date' in l])

# ════════════════════════════════════════════════════════════════════════
# 第三代（2026-09-24 复审收尾）：冒烟语义核对的**分层**不得混线
# ════════════════════════════════════════════════════════════════════════
# 为什么要测这一组：语义核对刚上线时，8/25、8/26 两张**旧格式** <desc>
# 每轮都报 WARN。它们既不需要处理、重跑该档就自愈 —— 属于典型「永久噪声」，
# 会把真 WARN 一起淹掉（2026-09-17 清过一次同类）。
# 于是把语义输出分成两条通道：真问题 → WARN（参与 rc），已知遗留 → INFO（不参与）。
# ⚠️ 分层本身有个致命误用风险：**把真问题也丢进 INFO，就等于静默豁免** ——
#    这正是本项目反复吃亏的「假闸门」形态。所以两边都必须断言：
#      ① 旧格式 <desc> → 进 INFO（不算问题）
#      ② 身份不符（覆盖事故形态）→ **必须**进 WARN（不许被 INFO 收编）
print()
print('=== 第三代：冒烟语义核对分层（INFO 不得收编真问题）===')

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location('_smoke_mod', os.path.join(HERE, 'smoke_pipeline.py'))
_sm = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_sm)


def _sem_probe(write_legacy=True, write_mismatch=True):
    """在临时目录里造 outputs/，塞入两种形态的 SVG，跑 semantic_check 看落哪条通道。

    返回 (warn_rels, info_rels) —— 只含 000001_forecast_*.svg 命中项。

    ⚠️ 两种形态用的**日期很关键**（本测试初版就栽在这）：
       · 旧格式必须取 < SEMANTIC_SVG_SINCE（2026-09-25）—— 现实里它们就是 8/25、8/26；
       · 身份不符必须取 **≥ SINCE**。初版把 mismatch 也写成 8/27（< SINCE），
         结果该规则被「机制生效前」的分支直接跳过、WARN 为空，断言假失败。
         这也暴露了一个**真实覆盖边界**（见下方 NOTE 断言）：生效日之前若真发生过
         覆盖事故，语义核对是**发现不了**的 —— 因为同名文件本来就没有可比对的基线。
    """
    tmp = tempfile.mkdtemp(prefix='semprobe_')
    out = os.path.join(tmp, 'outputs')
    os.makedirs(out)
    if write_legacy:
        # 旧格式：有人类可读描述、但无机器自述 date=（现实形态：8/25、8/26 两张图）
        with io.open(os.path.join(out, '000001_forecast_2026-08-25.svg'), 'w',
                     encoding='utf-8') as f:
            f.write('<svg><title>2026-08-25 上证综指尾盘预判</title>'
                    '<desc>13:40 现价 3886，15F带宽0.95%极度收口变盘</desc></svg>')
    if write_mismatch:
        # 覆盖事故形态（取 ≥ SINCE 的日期）：文件名 9/29，自述 date=9/28
        with io.open(os.path.join(out, '000001_forecast_2026-09-29.svg'), 'w',
                     encoding='utf-8') as f:
            f.write('<svg><title>x</title>'
                    '<desc>pred=2026-09-28-morning / date=2026-09-28 / actual=2026-09-25</desc>'
                    '</svg>')
    _old_root = _sm.ROOT
    _sm.ROOT = tmp
    try:
        w, i = [], []
        # ⚠️ 必须接住返回值！`w`/`i` 是**出参**（warn_list 是拼好的字符串 /
        #    info_list 是字符串），真正的结构化结果在返回值 `problems` 里 ——
        #    它才是 [(rule, rel, msg)]。本测试初版对 `w` 取 `x[1]`，
        #    拿到的是**拼好字符串的第 2 个字**（实测得到 'u'，来自 'outputs'），
        #    于是断言恒假失败。
        #    这个坑很典型：出参给人看、返回值给机器用，别拿混。
        _checked, _problems = _sm.semantic_check(w, i)
    finally:
        _sm.ROOT = _old_root
        shutil.rmtree(tmp, ignore_errors=True)
    wrels = sorted(x[1] for x in _problems if '000001_forecast_' in x[1])
    irels = sorted(x.split('（')[0] for x in i if '000001_forecast_' in x)
    return wrels, irels


_w, _i = _sem_probe()
ck(any('2026-08-25' in r for r in _i), '旧格式 <desc> → 必须进 INFO 通道（实测 INFO=%s）' % _i)
ck(not any('2026-08-25' in r for r in _w), '旧格式 <desc> → **不得**进 WARN（实测 WARN=%s）' % _w)
ck(any('2026-09-29' in r for r in _w), '身份不符（覆盖事故形态）→ **必须**进 WARN（实测 WARN=%s）' % _w)
ck(not any('2026-09-29' in r for r in _i), '身份不符 → **不得**被 INFO 收编（静默豁免）（实测 INFO=%s）' % _i)
# 反向：两种形态都不给 → 两条通道都应为空（防止「恒报警」假闸门）
_w2, _i2 = _sem_probe(write_legacy=False, write_mismatch=False)
ck(_w2 == [] and _i2 == [], '无异常产物 → 两条通道都须为空（WARN=%s INFO=%s）' % (_w2, _i2))
# 已记录的覆盖边界（不判 FAIL，但每次打印，免得被误当成「全覆盖」）
print('  [NOTE] 覆盖边界：%s 之前的图不做身份核对（无自述基线）——'
      '存量靠重跑自愈，历史段查不出，已知且接受。' % _sm.SEMANTIC_SVG_SINCE)

print()
if FAILS:
    print('RESULT: FAIL（%d 条）' % len(FAILS))
    for m in FAILS:
        print('  -', m)
    sys.exit(1)
print('RESULT: ALL PASS')
