# -*- coding: utf-8 -*-
"""chain_apply 回归测试

v2（2026-09-17 重写）—— v1 有两个致命缺陷：

  1. **日期脆弱导致假绿**：用例把待复盘的 id 写死为 `2026-09-16-morning`，同时沙箱
     直接拷贝真链。而该条在 9/17 晨报时已被复盘成 verified，于是用例走进
     `apply_review` 的「已有 review → 幂等跳过」分支，**空壳校验根本没被执行** ——
     B/C 两个「应拒绝」用例静默变成「已跳过」，却仍被当成通过读过。
  2. **期望不符仍返回 0**：脚本只打印「期望 / 实际」不做断言，无法当 gate 用。

  另：ROOT 硬编码绝对路径 `C:\\Users\\gedayou\\...`，家里机器直接跑不起来。

v2 改为：
  - 沙箱内**自建合成链**，与真链状态彻底解耦，永不受链前进影响
  - ROOT 由 `__file__` 推导
  - 每条用例断言退出码 / 链状态 / 文件落盘，不符即 FAIL；末尾汇总，有 FAIL 则非零退出
  - 覆盖 2026-09-17 修复的三个 BUG：**K-1** 共识链复盘路径、**K-2** bias 相对路径、
    **K-3** validate_prev 误报

用法：python .workbuddy/test_chain_apply.py
改动 chainlib / chain_apply 后必须跑一遍，确认「拒得住 + 不误伤 + 门是关的」。

v3（2026-09-18）—— 消除一个偶发假失败 + 一个卫生漏洞：
  · 沙箱原为**固定路径** `.workbuddy/_test_sandbox`，`fresh()` 先 `rmtree` 再 `makedirs`。
    Windows 上 rmtree 偶发因句柄未释放而残留目录 → `makedirs` 抛 `FileExistsError` 直接崩
    （实测 2026-09-18 出现一次 EXIT=1，随后连跑 5 次均 EXIT=0）。
    现改用 `tempfile.mkdtemp()`：唯一、在系统临时目录、**不占仓库**、并发跑也不相撞。
  · 该固定目录名在 .gitignore 里**本就有覆盖**（`.workbuddy/_test_sandbox/`），
    但只匹配精确名称 —— 若日后改成带后缀的固定名就会漏。顺手把该规则改为
    `.workbuddy/_test_sandbox*/` 作兜底。

v4（2026-09-21）—— 「聚合跑必红 / 单跑必绿」的真因钉住了（两处）：
  1) **删除仓库内文件触发环境删除保护** → 子进程被杀（rc=1、输出截断、无 traceback）。
     这是 case L 收尾那两句 `os.remove` 导致的。子进程在沙箱内时必杀，
     而手动单跑因命令被提权、沙箱被绕过，所以一直是绿的 —— 典型的「环境差异假失败」。
     现改为**不删**（文件已被 .gitignore 覆盖，清理交 cleanup_workspace.py），并在末尾报出。
  2) `fresh()` 仍在反复 rmtree+makedirs 同一目录，现改为**每用例新开沙箱、运行期零删除**。
  另：run_tests.py 原先只收 stdout、丢掉 stderr，把 traceback 藏了 —— 已改为合并捕获。
"""
import os
import shutil
import subprocess
import sys
import tempfile

WB = os.path.dirname(os.path.abspath(__file__))
# 沙箱：**每个用例一个全新目录**，运行期不做任何删除（见 fresh() 的说明）
SB = None
SANDBOXES = []
CA = os.path.join(WB, 'chain_apply.py')
PY = sys.executable
S = '<<< 必填'

RID_F = 'T-2026-01-02-morning'      # forecast 待复盘靶子
RID_C = 'T-2026-01-02-morning'      # consensus 待复盘靶子（两条链各自命名空间）
PREV = 'T-2026-01-01-morning'       # 上一条（已 verified）
BIAS_TMP = '_bias_test_tmp.json'    # 匹配 .gitignore 的 _bias_*.json，跑完自动清

RESULTS = []


# ---------------------------------------------------------------- 沙箱

def synth_forecast():
    """合成 forecast 链：1 条 verified（带上一条的回显数据）+ 1 条 pending（本次靶子）"""
    return [
        {'id': PREV, 'report_type': 'morning', 'created_at': '2026-01-01 08:50',
         'direction': '偏多', 'range': '3000~3100', 'confidence': '中',
         'status': 'verified',
         'review': {'reviewed_at': '2026-01-01 15:00',
                    'actual': {'date': '2026-01-01', 'close': 3050, 'pct_chg': 0.5},
                    'direction_verdict': '✅ 命中', 'range_verdict': '⚠️ 部分',
                    'support_verdict': '✅ 命中', 'resistance_verdict': '❌ 失效'}},
        {'id': RID_F, 'report_type': 'morning', 'created_at': '2026-01-02 08:50',
         'direction': '偏空', 'range': '3000~3100', 'confidence': '中', 'status': 'pending'},
    ]


def synth_consensus():
    """合成 consensus 链：review 用 per_topic + opposite_review（与 forecast schema 不同）"""
    return [
        {'id': PREV, 'report_type': 'morning', 'created_at': '2026-01-01 08:50',
         'window': 'x', 'consensus': [], 'opposing': [], 'status': 'verified',
         'review': {'review_time': '2026-01-01 15:00',
                    'per_topic': [{'topic': 't', 'type': 'consensus',
                                   'verdict': '✅ 兑现', 'note': ''}],
                    'opposite_review': {'topic': 'o', 'verdict': '✅ 未兑现', 'note': ''}}},
        {'id': RID_C, 'report_type': 'morning', 'created_at': '2026-01-02 08:50',
         'window': 'x', 'consensus': [], 'opposing': [], 'status': 'pending'},
    ]


def fresh():
    """开一个**全新沙箱**，不回删旧目录。

    v4（2026-09-21）—— 消除「聚合跑必红、单跑必绿」的偶发假失败：
      v3 改成 mkdtemp 只解决了「固定名残留」，但 `fresh()` 每次仍是
      `rmtree(SB)` + `makedirs(SB)`，一个测试文件里要重复 ~10 次。两个后果：
        · rmtree 与紧随的 makedirs 竞态（v3 注释里记的那个 2026-09-18 EXIT=1 就是这个）；
        · 聚合跑时进程内累计删除量可观，会撞上环境的安全删除闸门，
          **进程被直接杀掉** —— 表现是 rc=1、输出写到一半就断、且**没有 traceback**
          （2026-09-21 实测：聚合跑连红 3 次，单跑连绿 3 次）。
      现在改为每用例新开一个目录、运行期删除次数 = 0，收尾统一清一次（见文件末尾）。
    """
    global SB
    SB = tempfile.mkdtemp(prefix='wb_chain_apply_')
    SANDBOXES.append(SB)
    for name, recs in (('forecast_chain.json', synth_forecast()),
                       ('consensus_chain.json', synth_consensus())):
        write(os.path.join(SB, name), recs)


def write(path, obj):
    import json
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def read(path):
    import json
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def run(payload):
    p = os.path.join(SB, 'payload.json')
    write(p, payload)
    env = dict(os.environ, CHAIN_DIR=SB)
    return subprocess.run([PY, CA, '--payload', p], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', env=env)


# ---------------------------------------------------------------- 断言

def rec_of(rid, chain='forecast'):
    fn = 'forecast_chain.json' if chain == 'forecast' else 'consensus_chain.json'
    for r in read(os.path.join(SB, fn)):
        if r.get('id') == rid:
            return r
    return None


def chain_len(chain='forecast'):
    fn = 'forecast_chain.json' if chain == 'forecast' else 'consensus_chain.json'
    return len(read(os.path.join(SB, fn)))


def check(desc, cond):
    RESULTS.append((bool(cond), desc))
    print('   %s %s' % ('PASS' if cond else 'FAIL', desc))


def case(title):
    print('\n===== %s =====' % title)


def brief(r, keys=('拒绝', '被拒', '回读', '幂等', '复盘', '待复盘', '警告')):
    return '\n'.join('     | ' + l.strip() for l in r.stdout.splitlines() if any(k in l for k in keys))


# ---------------------------------------------------------------- 用例

# --- B/C：forecast 空壳 review 必须被拒（K 系列的核心守卫）
for label, rv in (
    ('B) 空壳 review（模板哨兵）应被拒',
     {'reviewed_at': S, 'actual': {'date': '', 'open': 0, 'high': 0, 'low': 0, 'close': 0},
      'direction_verdict': S + '：✅/⚠️/❌ + 说明', 'range_verdict': S + '：x',
      'support_verdict': S + '：x', 'resistance_verdict': S + '：x'}),
    ('C) 空壳 review（全空串）应被拒',
     {'reviewed_at': 'x', 'actual': {'close': 0}, 'direction_verdict': '',
      'range_verdict': '', 'support_verdict': '', 'resistance_verdict': ''}),
):
    case(label)
    fresh()
    r = run({'forecast': {'review': {'id': RID_F, 'review': rv}}})
    rec = rec_of(RID_F)
    print(brief(r))
    check('退出码 = 2（被拒）', r.returncode == 2)
    check('链中仍为 pending', rec.get('status') == 'pending')
    check('未写入 review', not rec.get('review'))

# --- D：正常填写不应误伤
case('D) 正常填写应通过（不误伤）')
fresh()
r = run({'forecast': {'review': {'id': RID_F, 'review': {
    'reviewed_at': '2026-01-02 15:00（复盘）',
    'actual': {'date': '2026-01-02', 'open': 3000, 'high': 3050, 'low': 2980,
               'close': 3040, 'pct_chg': 0.8},
    'direction_verdict': '✅ 命中', 'range_verdict': '⚠️ 部分',
    'support_verdict': '✅ 命中', 'resistance_verdict': '❌ 失效'}}}})
rec = rec_of(RID_F)
print(brief(r))
check('退出码 = 0', r.returncode == 0)
check('status -> verified', rec.get('status') == 'verified')
check('review 已落盘', bool(rec.get('review')))

# --- E：record 残留占位符应被拒
case('E) 占位符 record 应被拒')
fresh()
n0 = chain_len()
r = run({'forecast': {'record': {'id': 'T-2026-01-02-close',
                                 'direction': S + '：偏多/偏空/震荡',
                                 'range': S + '：下沿~上沿',
                                 'confidence': S + '：高/中/低'}}})
print(brief(r))
check('退出码 = 2', r.returncode == 2)
check('未追加记录', chain_len() == n0)

# --- F：幂等 —— 重复提交不覆盖已有 review
case('F) 幂等：重复提交同一 review 不覆盖')
fresh()
first = {'reviewed_at': 'a', 'actual': {'close': 3000},
         'direction_verdict': '✅ 第一次', 'range_verdict': '✅', 'support_verdict': '✅',
         'resistance_verdict': '✅'}
run({'forecast': {'review': {'id': RID_F, 'review': first}}})
r2 = run({'forecast': {'review': {'id': RID_F, 'review': {
    'reviewed_at': 'b', 'actual': {'close': 9999},
    'direction_verdict': '❌ 第二次（不应生效）', 'range_verdict': '❌', 'support_verdict': '❌',
    'resistance_verdict': '❌'}}}})
rec = rec_of(RID_F)
print(brief(r2, keys=('幂等', '回读', '复盘')))
check('第二次退出码 = 0', r2.returncode == 0)
check('内容仍为第一次（未被覆盖）',
      (rec.get('review') or {}).get('direction_verdict') == '✅ 第一次')

# --- G/H/I：共识链复盘（K-1 回归）—— 修复前一律被误判空壳而拒写
case('G) 共识链空壳 review 应被拒（K-1 回归）')
fresh()
r = run({'consensus': {'review': {'id': RID_C, 'review': {
    'review_time': '', 'per_topic': [{'topic': 't', 'type': 'consensus',
                                      'verdict': '', 'note': ''}],
    'opposite_review': {'topic': 'o', 'verdict': S, 'note': ''}}}}})
rec = rec_of(RID_C, 'consensus')
print(brief(r))
check('退出码 = 2', r.returncode == 2)
check('链中仍为 pending', rec.get('status') == 'pending')

case('H) 共识链实填 review 应通过（K-1 回归：修复前必被拒）')
fresh()
r = run({'consensus': {'review': {'id': RID_C, 'review': {
    'review_time': '2026-01-02 15:00', 'phase': '收盘后',
    'per_topic': [{'topic': '分歧点A', 'type': 'consensus', 'verdict': '✅ 兑现', 'note': 'x'},
                  {'topic': '分歧点B', 'type': 'opposing', 'verdict': '❌ 未兑现', 'note': 'y'}],
    'opposite_review': {'topic': '剧本C', 'verdict': '⚠️ 部分兑现', 'note': 'z'}}}}})
rec = rec_of(RID_C, 'consensus')
print(brief(r, keys=('拒绝', '被拒', '回读', '幂等', '复盘', '共识')))
check('退出码 = 0', r.returncode == 0)
check('status -> verified', rec.get('status') == 'verified')

case('I) 共识链仅填 opposite_review 也应通过')
fresh()
r = run({'consensus': {'review': {'id': RID_C, 'review': {
    'review_time': '2026-01-02 15:00',
    'opposite_review': {'topic': '剧本C', 'verdict': '✅ 兑现', 'note': ''}}}}})
rec = rec_of(RID_C, 'consensus')
check('退出码 = 0', r.returncode == 0)
check('status -> verified', rec.get('status') == 'verified')

# --- J：consensus record 追加 + 幂等
case('J) 共识链 record 追加应通过且幂等')
fresh()
pl = {'consensus': {'record': {'id': 'T-2026-01-02-close', 'report_type': 'close',
                               'created_at': '2026-01-02 19:00', 'window': 'x',
                               'consensus': [], 'opposing': []}}}
r1 = run(pl)
n1 = chain_len('consensus')
r2 = run(pl)
check('首次退出码 = 0', r1.returncode == 0)
check('已追加（条数 +1）', n1 == chain_len('consensus') == 3)
check('重复提交退出码 = 0', r2.returncode == 0)
check('幂等：条数未变', chain_len('consensus') == 3)

# --- K：validate_prev 指向「本次即将复盘的那条」不应误报（K-3 回归）
case('K) validate_prev 指向本次将复盘对象时不误报（K-3 回归）')
fresh()
r = run({'forecast': {'validate_prev': RID_F,
                      'review': {'id': RID_F, 'review': {
                          'reviewed_at': 'x', 'actual': {'close': 3000},
                          'direction_verdict': '✅', 'range_verdict': '✅',
                          'support_verdict': '✅', 'resistance_verdict': '✅'}}}})
print(brief(r))
check('输出含「待复盘」', '待复盘' in r.stdout)
check('输出不含误导性「需先复盘」', '需先复盘' not in r.stdout)
check('退出码 = 0', r.returncode == 0)

# --- L：bias.write 相对路径（K-2 回归）—— 两种写法都不得崩、且文件要落到 .workbuddy/
case('L) bias.write 相对路径落盘（K-2 回归）')
for label, wp, target in (
    ('裸文件名', BIAS_TMP, os.path.join(WB, BIAS_TMP)),
    ('.workbuddy/ 前缀', '.workbuddy/_bias_test_tmp2.json', os.path.join(WB, '_bias_test_tmp2.json')),
):
    fresh()
    r = run({'forecast': {'review': {'id': RID_F, 'review': {
                'reviewed_at': 'x', 'actual': {'close': 3000},
                'direction_verdict': '✅', 'range_verdict': '✅',
                'support_verdict': '✅', 'resistance_verdict': '✅'}}},
            'bias': {'print': True, 'write': wp}})
    check('%s：退出码 = 0（不再因附属文件崩成 1）' % label, r.returncode == 0)
    check('%s：文件已写到 .workbuddy/ 下' % label, os.path.exists(target))
    # ⚠️ 这里**故意不 os.remove**（2026-09-21 把偶发假失败的真因钉住了）：
    #   `os.remove` 删的是**仓库内**文件，会触发执行环境的删除保护，
    #   子进程被直接杀掉 —— 表现是 rc=1、输出写到一半断、**没有 traceback**。
    #   它只在 `run_tests.py` 里发作（子进程在沙箱内），单跑时命令被提权、沙箱被绕过，
    #   于是长期呈现为「聚合跑必红、单跑必绿」的鬼故事。
    #   这两个文件名是 `_bias_*.json`，已被 .gitignore 覆盖，留着无害；
    #   真要清理由 cleanup_workspace.py 统一处理（本项目约定：归档而非就地删除）。

# --- 真链只读校验（仅信息，不作为通过条件 —— 链会随报告前进）
print('\n===== 真链状态（只读，仅供对照）=====')
env = dict(os.environ)
env.pop('CHAIN_DIR', None)
for n, fn in (('forecast', 'forecast_chain.json'), ('consensus', 'consensus_chain.json')):
    try:
        recs = read(os.path.join(WB, fn))
        v = sum(1 for x in recs if x.get('status') == 'verified')
        p = sum(1 for x in recs if x.get('status') == 'pending')
        print('   %-9s 总 %d | verified %d | pending %d' % (n, len(recs), v, p))
    except Exception as e:
        print('   %-9s 读取失败：%r' % (n, e))

# ---------------------------------------------------------------- 汇总
# 本用例会在 .workbuddy/ 下留 2 个 _bias_test_tmp*.json（见 L 的注释：刻意不删）。
# **显式报出来**，免得日后被当成「莫名多出来的文件」—— 静默留垃圾也是一种隐瞒。
_LEFTOVER = [os.path.join(WB, BIAS_TMP), os.path.join(WB, '_bias_test_tmp2.json')]
_have = [p for p in _LEFTOVER if os.path.exists(p)]
if _have:
    print('\n(按设计保留的临时文件 %d 个，已被 .gitignore 覆盖：%s)'
          % (len(_have), '、'.join(os.path.basename(p) for p in _have)))

bad = [d for ok, d in RESULTS if not ok]
print('\n' + '=' * 60)
print('用例合计 %d，通过 %d，失败 %d' % (len(RESULTS), len(RESULTS) - len(bad), len(bad)))
if bad:
    print('失败项：')
    for d in bad:
        print('  - %s' % d)
    print('=' * 60)
else:
    print('全部通过 ✅')
    print('=' * 60)


def _cleanup_sandboxes():
    """收尾清理：**先出结论、后清理** —— 万一清理被环境拦下（甚至把进程杀掉），
    判定结果已经打印落纸，不会把绿判成红。超过阈值就只报告、不动手。"""
    n = sum(len(fs) for d in SANDBOXES for _, _, fs in os.walk(d))
    if n > 40:
        print('(沙箱文件 %d 个，超过安全阈值，未删除：%s)' % (n, SANDBOXES))
        return
    ok = 0
    for d in SANDBOXES:
        try:
            shutil.rmtree(d, ignore_errors=True)
            ok += 1
        except Exception:
            pass
    print('(沙箱已清理 %d/%d 个，位于系统临时目录)' % (ok, len(SANDBOXES)))


_cleanup_sandboxes()
sys.exit(1 if bad else 0)
