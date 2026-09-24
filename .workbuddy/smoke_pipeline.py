# -*- coding: utf-8 -*-
"""全链路冒烟测试（常驻工具，2026-09-21 建）—— 一条命令把报告链路的每一环真跑一遍，看谁崩。

为什么需要它：
  项目已有 `run_tests.py`（跑单元/回归测试）与 `audit_pipeline.py`（静态结构审计），
  但**没有任何东西会真的把链路跑一遍**。「测试全绿 + 静态干净」与「链路能跑通」是两件事 ——
  改过某个脚本的 CLI、改过某个函数的返回结构，测试可能照样绿，而流水线要到下一档才发现崩。

设计原则：
  1. **默认零副作用**：链操作一律 `--dry-run`；不生成报告；不改两条链；
     需落盘的产物一律写到 `--tmp` 指定的**临时目录**。唯一会真写的是抓取阶段
     （这是它的本职工作，且自带 `.prev` 备份与「降级不覆盖主快照」守卫）。
  2. **前后 md5 快照**：跑之前对「受保护文件」取 md5，跑完再取一次，
     **任何非预期变化都判 FAIL** —— 这是「冒烟测试自己有没有搞坏东西」的唯一硬证据。
     受保护范围：两条链、`outputs/` 下所有交付物、`.workbuddy/*.md` 与 `*.py`。
     备份写成**单个 zip**（不是几百个散文件），回滚时按成员解出。
     ⚠️ 教训（2026-09-21）：备份若做成散文件，临时目录会膨胀到 700+ 个，
     清理时撞上环境的安全删除闸门，**冒烟在第一行就死掉**——闸门把测闸门的人也拦了。
  2b. 每次运行都新建独立临时目录（`_smoke_tmp/run_<时间戳>`），**从不删别人的目录**。
      ⚠️ 代价：目录**不会自动回收**（`_cleanup` 只在文件数 < 40 时删本次的）。
      回收交给独立小工具 `recycle_smoke_tmp.py` —— **刻意不塞进本脚本**：本脚本的设计前提是
      「零副作用」，若它自己去删历史目录，就有了删除副作用，排查时无法区分是谁删的。
  2c. **语义核对 ≠ md5 核对**（2026-09-24 复审 R2-2/R2-3，重要）：
      md5 只能证明「文件**没被改过**」，**不能证明「文件内容是对的」**。
      若某一环写出来的产物本身就是错的（例：走势图叠了错日子的 actual、报告落盘时漏了一整节），
      md5 前后一致、阶段全绿，冒烟照样报 ALL PASS。三个具体盲区：
        ① 静默失败：脚本 rc=0 但产物是错的（生成器打印一行 `SVG written` 就算成功）；
        ② 既有错误：**跑之前就错的文件**，冒烟根本不看它（只比前后）；
        ③ 覆盖事故：写进**同名不同档位**的文件，md5 变化被判「受保护文件被改」→ 回滚，
           但**为什么会被改**这条信息没有，事后查不出是哪一环干的。
      故新增 `SEMANTIC_RULES`（弱于 md5 的存在性 + 身份核对）：
      受保护交付物跑完后必须仍**能推出自己的所属档位/日期**，且与其身份自述一致。
      这不是要替代 md5，而是补上「产物内容正确性」这一层 —— 结论行里明确区分二者。
  3. **声明式阶段清单**：加/改一环只改 `build_stages()`，不新写脚本。
  4. **「期望退出码」写在声明里**：如 `gen_tj_archive` 空窗口退 2 是**设计**而非故障、
     `md_to_html` 无参退 1 是**守卫**而非崩溃。不写清楚就只能靠人肉记忆，等于没有判据。
  4b. **崩栈即失败**（2026-09-23 加固）：退出码合格还不够 —— 输出里出现 traceback
     一律判 FAIL。原因：一半阶段的期望集合含 1/2，光看退出码，「有意报错」与
     「未捕获异常」完全同形（实测：修复前的 `check_integrity` 缺链文件时
     rc=1 + Traceback + 无 `[FAIL]`，冒烟照样判 [OK]）。白名单 `ALLOW_TB`
     默认空，加条目必须写理由。
  5. 串行执行（项目约定：并发 >2 会触发沙箱拦截）。`--only` 可只跑子集。
  6. ⚠️ **跑冒烟期间不要编辑仓库文件**：受保护文件在开跑时取快照、跑完按 md5 核对，
     不一致就**回滚**（这是防「脚本乱写」的护栏）。2026-09-23 实测踩坑：
     在冒烟运行中改了 3 个脚本 → 冒烟把改动全部回滚，修复白做且结果作废。

用法：
    $PY .workbuddy/smoke_pipeline.py                 # 全量
    $PY .workbuddy/smoke_pipeline.py --no-net        # 跳过联网阶段（离线可跑）
    $PY .workbuddy/smoke_pipeline.py --no-slow       # 跳过慢阶段（引擎/测试）
    $PY .workbuddy/smoke_pipeline.py --only chain    # 只跑名字含该子串的阶段
    $PY .workbuddy/smoke_pipeline.py --keep-tmp      # 保留临时目录（排查用）

退出码：0 全部通过 · 1 有 FAIL · 2 仅 WARN
"""
import argparse
import fnmatch
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # silent-ok: 终端编码收口尽力而为，失败不影响结论
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
TIMEOUT = 480          # 单个阶段墙钟上限（秒）
# ── 慢阶段单独放宽（2026-09-24 修）──
# 原实现所有阶段共用 480s。`run_tests.py` 2026-09-24 已涨到 580s（19 个测试文件，
# 其中 test_gen_forecast_svg_neg.py 单跑 136s、test_audit_docrot_neg.py 114s），
# 于是 A3 恒 rc=124（超时）→ 冒烟永远 FAIL。
# ⚠️ 注意这条自伤的形态：**一个只能报红的闸门等于没有闸门** ——
#    一旦超时被判为常态噪声，真正的「测试跑不过」就再也不会被看见了。
# 所以这里不是放宽判据，而是让「慢」有明确、显式、可解释的额度：
#    正常跑完 → 按退出码判定（该 FAIL 还是 FAIL）
#    真超时   → 仍 rc=124 → 仍 FAIL（额度只是更大，不是免检）
TIMEOUT_SLOW = 1500    # 标记为「慢」的阶段（build_stages 第 6 个字段）用这个上限
DEFAULT_TMP = os.path.join(HERE, '_smoke_tmp')
CLEANUP_MAX_FILES = 40  # 临时目录超过这么多文件就不自动删（见 _cleanup 的说明）

# ── 崩栈即失败（2026-09-23 加固）──
# 阶段判定原先只看退出码（`ok = rc in expect`），而多数阶段的期望集合含 1/2，
# 于是「有意报错」与「未捕获异常崩栈」在退出码上完全同形 —— 实测过：
# 修复前的 check_integrity 缺链文件时是 rc=1 + Traceback + 无 [FAIL]，
# 冒烟照样判 [OK]。轨迹是：脚本坏了 → 退出码落进期望集合 → 闸门报绿。
# 现在把「输出里有 traceback」独立成一条硬失败，与退出码无关。
TB_MARK = 'Traceback (most recent call last)'
# 允许崩栈的阶段白名单：**每加一条都必须写清理由**，否则等于把闸门拆掉。
# 当前为空 —— 31 个阶段没有任何一个应当以未捕获异常收场（失败路径一律
# 打印 [FAIL] 并 sys.exit(非零)，见脚本地图 §〇·补11）。
ALLOW_TB = set()

# ── 受保护：冒烟**不允许**被改动。改了就是最严重的 BUG（说明有脚本在乱写）──
PROTECTED_GLOBS = [
    '.workbuddy/forecast_chain.json',
    '.workbuddy/consensus_chain.json',
    'outputs/*.md',
    'outputs/*.html',
    'outputs/*.svg',
    # outputs/*.json 原先**不在受保护范围**（2026-09-23 发现）：引擎数据包
    # `000001_四周期联动_<日期>.json` 每天一份，冒烟跑 D2 会直接覆盖当天那份，
    # 而 md5 核对看不见它 → 「冒烟改动了交付物却不报」的盲区。
    # 配套改动：D2 现在带 `--out {TMP}/...`，不再往真实 outputs/ 写。
    'outputs/*.json',
    '.workbuddy/*.md',
    '.workbuddy/*.py',
]
# ── 允许变化，但如实汇报（抓取/扫描类阶段的正常产出）──
# 注意：这里**必须与 PROTECTED_GLOBS 完全不相交**，否则该文件永远同时命中两边 →
# 每次冒烟都报「受保护文件被改」→ 永久红灯 → 闸门被无视（2026-09-21 踩过：
#   outputs/DRAGON_BALL_原始记录_*.md 同时在两边，制造了一次假 FAIL）。
# 现在归档阶段改走 --out 写到临时目录，该文件回归「纯受保护」，被改一定是真问题。
MAY_CHANGE_GLOBS = [
    '.workbuddy/zsxq_fetch_raw*.json',
    '.workbuddy/zsxq_fetch_meta.json',
    '.workbuddy/*_bias_*.json',
    '.workbuddy/backtest_data/*.json',
    '.workbuddy/_ohlc_cache/*.json',
]
# 新增文件允许出现的目录（阶段自建产物）
NEW_FILE_SCOPE = ['outputs', '.workbuddy']
IGNORE_NEW = ('_smoke_tmp', '__pycache__')


def _cleanup(tmp):
    """清理本次运行的临时目录。

    两个约束（2026-09-21 踩过）：
      1) **不预先 rmtree 旧目录**：上一次运行的 `_smoke_tmp` 里有 357 个备份文件，
         一开始就删它会直接撞上环境的安全删除闸门（一次删 716 个 > 阈值 50），
         整个冒烟在第一行就死掉。所以现在每次运行都新建独立目录，从不删别人的。
      2) **删成功与否都要核实**：`rmtree(ignore_errors=True)` 会把删除失败吞掉 ——
         实测环境闸门会按 `backup_zip` 的**成员数**计数（360 成员 → 报 count=367），
         于是目录根本删不掉，而旧写法连一个字都不说。现在删完必须回查，
         没删掉就如实报出来（留着垃圾可以，瞒着不行）。
    """
    if not os.path.isdir(tmp):
        return True
    loose = sum(len(fs) for _, _, fs in os.walk(tmp))
    members = 0
    for root, _, fs in os.walk(tmp):
        for f in fs:
            if f.endswith('.zip'):
                try:
                    with zipfile.ZipFile(os.path.join(root, f)) as z:
                        members += len(z.namelist())
                except Exception:  # silent-ok: zip 成员数读不到按 0 计，只影响临时目录阈值提示（偏保守）
                    pass
    total = loose + members
    if total > CLEANUP_MAX_FILES:
        # ⚠️ 这里**故意不自动删**（2026-09-21 的血泪）：环境删除闸门按 zip 成员数计数，
        #    一次删几百个会直接被拦死，整个冒烟在第一行就死。所以本函数只负责
        #    「删得掉就删、删不掉就如实说」。
        #    存量回收是**独立工具**的职责（2026-09-24 R3 落地）：
        #      python .workbuddy/recycle_smoke_tmp.py            # 预演，一个字都不删
        #      python .workbuddy/recycle_smoke_tmp.py --apply --keep 5
        #    把它写进提示，是为了让读到这条 WARN 的人知道下一步该敲什么 ——
        #    一条「只报问题、不给出路」的警告，下场就是被无视。
        print('[WARN] 临时目录 %d 个文件（含备份 zip 成员 %d）超过阈值 %d，**不自动删除**：%s'
              % (loose, members, CLEANUP_MAX_FILES, tmp))
        print('       回收请用独立工具（默认预演，不动真实目录）：'
              'python .workbuddy/recycle_smoke_tmp.py --apply --keep 5')
        return False
    shutil.rmtree(tmp, ignore_errors=True)
    if os.path.isdir(tmp):
        print('[WARN] 临时目录**删除失败**（环境删除保护拦截），请人工处理：%s'
              % tmp)
        return False
    return True


def md5(p):
    m = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            m.update(b)
    return m.hexdigest()


def _match(rel, globs):
    return any(fnmatch.fnmatch(rel.replace('\\', '/'), g) for g in globs)


def collect():
    """{相对 ROOT 的 posix 路径: md5}。范围固定为 PROTECTED_GLOBS。"""
    out = {}
    for g in PROTECTED_GLOBS:
        for p in glob.glob(os.path.join(ROOT, g)):
            if os.path.isfile(p):
                rel = os.path.relpath(p, ROOT).replace('\\', '/')
                out[rel] = md5(p)
    return out


def collect_may():
    """MAY_CHANGE 范围跑前的 md5。**只记哈希、不备份** —— 这些文件本来就允许变。"""
    out = {}
    for g in MAY_CHANGE_GLOBS:
        for p in glob.glob(os.path.join(ROOT, g)):
            if os.path.isfile(p):
                out[os.path.relpath(p, ROOT).replace('\\', '/')] = md5(p)
    return out


def list_scope():
    """枚举 NEW_FILE_SCOPE 下的现有文件集合（用于检测新增文件）。"""
    fs = set()
    for s in NEW_FILE_SCOPE:
        d = os.path.join(ROOT, s)
        for p in glob.glob(os.path.join(d, '*')):
            if any(k in p for k in IGNORE_NEW):
                continue
            if os.path.isdir(p):
                fs.add(os.path.relpath(p, ROOT).replace('\\', '/') + '/')
            else:
                fs.add(os.path.relpath(p, ROOT).replace('\\', '/'))
    return fs


def newest_by_mtime(pattern, base=None):
    base = base or ROOT
    fs = glob.glob(os.path.join(base, pattern))
    return max(fs, key=os.path.getmtime) if fs else None


# ─────────────────────────────────────────────────────────────────────────────
# 语义核对（2026-09-24 复审 R2-2/R2-3）
#
# 为什么必须有这一层：**md5 只证明「没被改过」，不证明「内容是对的」**。
#   ① 脚本 rc=0 但产物写错了 —— 例如走势图叠了**另一天**的 actual：
#      生成器只打印一行 `SVG written`，路径合理、幂等、md5 前后一致 → 全绿。
#   ② 跑之前**就已经是错的**文件 —— 冒烟只比前后，从不看存量内容。
#   ③ 覆盖事故 —— 写进同名不同档的文件，会以「受保护文件被改」的形式出现，
#      但**为什么被改**（哪一环、写错了什么）在报告里看不到。
# 故这里加一组**弱于 md5 但独立于它**的断言：受保护交付物跑完后必须仍
# **能推出自己的所属档位/日期**，且与其**身份自述**一致。
# 刻意做得比 md5 弱：只查「身份能不能对上」，不查内容细节（那属单元测试范畴）。
# ─────────────────────────────────────────────────────────────────────────────

# 交付物 → 语义断言。每条 = (glob, 规则名, 检查函数(rel, abspath) -> None|str(问题))
SEMANTIC_SVG_DESC = re.compile(r'<desc>(.*?)</desc>', re.S)
SEMANTIC_SVG_SINCE = '2026-09-25'      # 自述机制生效日（与 check_integrity 同口径）


def _sem_svg_identity(rel, path):
    """走势图必须**自述身份**，且文件名日期 == 自述 date=。

    这正是 2026-09-24 覆盖事故的形态：9/24 的图被写进 2026-09-23.svg，
    两张 md5 相同、无备份。md5 核对对**已经写坏的存量图**完全无能为力
    （它只比前后，不比内容），故必须看图自己怎么说。
    """
    base = os.path.basename(rel)
    m = re.match(r'^000001_forecast_(\d{4}-\d{2}-\d{2})\.svg$', base)
    if not m:
        return None                        # 命名不符规范的老图（_v2 等），跳过
    fdate = m.group(1)
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    except Exception as e:                 # noqa: BLE001
        return '读取失败 %s' % type(e).__name__
    d = SEMANTIC_SVG_DESC.search(text)
    if not d:
        if fdate < SEMANTIC_SVG_SINCE:
            return None                    # 自述机制生效前：允许（INFO 层面不计）
        return 'no-desc: SVG 内无自述 <desc>（date=…），无法核对身份（应为重跑新版生成器补上）'
    mm = re.search(r'\bdate=(\d{4}-\d{2}-\d{2})', d.group(1))
    if not mm:
        # ⚠️ 措辞要与事实相符（2026-09-24 修）：实测 8/25、8/26 两张图**有** <desc>，
        #    里面是**人类可读的描述文字**（'13:40 现价 3886，15F带宽0.95%…'），
        #    是「机器自述机制」之前的旧格式 —— 不是「描述缺失」。
        #    早先文案写成「<desc> 里没有 date= 字段」容易被读成「文件坏了」，
        #    实际形态是**旧格式**，性质是「历史遗留、重跑即自愈」，不是告警。
        return (LEGACY_MARK + 'legacy-desc: 旧格式 <desc>（人类描述文字，无机器自述 date=）'
                ' —— 属历史遗留，用当前生成器重跑该档即自动升级为新格式')
    if mm.group(1) != fdate:
        return ('desc-mismatch: 文件名 %s ≠ 自述 %s —— 这正是「覆盖别的档位的图」的形态'
                '（2026-09-24 真实事故：md5 相同、不可恢复）' % (fdate, mm.group(1)))
    return None


def _sem_report_tier(rel, path):
    """报告文件名必须能推出「档位 + 日期」，且与首行标题里的日期一致。

    「能推出所属档位/日期」这条断言的价值在于：一旦生成脚本改名格式改了、
    或报告被写成另一天的内容，**文件名与内容就自相矛盾** —— 而 md5 看不出来。
    """
    base = os.path.basename(rel)
    m = re.match(r'^作战报告_([^_]+)_(\d{4}-\d{2}-\d{2})\.md$', base)
    if not m:
        return None                        # 旧命名/匿名版等，跳过
    fdate = m.group(2)
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            head = f.read(4000)
    except Exception as e:                 # noqa: BLE001
        return '读取失败 %s' % type(e).__name__
    # 正文里出现**另一个日期**的强断言不做（报告必然引用历史日期），
    # 只做一条弱断言：文件名日期必须在正文里出现过（否则内容与文件名完全对不上）。
    if fdate not in head:
        return 'date-absent: 前 4000 字内找不到文件名日期 %s（内容与文件名可能对不上）' % fdate
    return None


SEMANTIC_RULES = [
    ('outputs/000001_forecast_*.svg', 'svg-identity', _sem_svg_identity),
    ('outputs/作战报告_*.md', 'report-filename-date', _sem_report_tier),
]

# 语义规则返回串若以此前缀开头 → 走 INFO 通道（已知历史遗留，不占 WARN 额度）。
# 用前缀而不是另建返回值类型：规则函数很薄，让它继续只返回「一个字符串或 None」，
# 判定逻辑集中在本处；且这个前缀在打印时会剥掉，人看不出实现细节。
LEGACY_MARK = '[legacy] '


def semantic_check(warn_list, info_list=None):
    """对**现有**受保护交付物跑语义断言（不看前后差异，只看内容是否自洽）。

    ⚠️ 与 md5 核对的本质区别：md5 是**差分**判据（前后比），本函数是**绝对**判据
    （直接看内容对不对）。这正是复审指出的盲区②——「跑之前就错的文件」，
    差分判据永远发现不了。

    两条输出通道（2026-09-24 增设 info_list）：
      · **WARN**（warn_list）—— 需要人看的：身份自相矛盾 / 机制生效后仍无自述。
      · **INFO**（info_list）—— 已知历史遗留、有自愈路径的：如旧格式 `<desc>`。
        为什么必须分开：8/25、8/26 两张旧图会让**每一轮**冒烟都冒 2 条 WARN，
        而它们既不需要处理、重跑该档就自动升级 —— 这就是 2026-09-17 清掉的
        「永久噪声」形态。噪声留着，真 WARN 就会被一起无视。
    INFO 不追加进 warn_list，也不参与 rc 判定。
    返回 (checked, problems)；problems 只含 WARN 级。
    """
    checked, problems = 0, []
    if info_list is None:
        info_list = []
    for pattern, rule, fn in SEMANTIC_RULES:
        for p in sorted(glob.glob(os.path.join(ROOT, pattern))):
            rel = os.path.relpath(p, ROOT).replace('\\', '/')
            try:
                msg = fn(rel, p)
            except Exception as e:         # noqa: BLE001
                msg = '规则自身异常 %s: %s' % (type(e).__name__, e)
            checked += 1
            if not msg:
                continue
            # 「已知历史遗留」前缀 = INFO 通道；其余一律 WARN。
            if msg.startswith(LEGACY_MARK):
                info_list.append('%s（%s）：%s' % (rel, rule, msg[len(LEGACY_MARK):].lstrip()))
                continue
            problems.append((rule, rel, msg))
            warn_list.append('%s（%s）：%s' % (rel, rule, msg))
    return checked, problems


# 注意：不要用 % 格式化来拼这段代码 —— 代码体里本来就有 %s/%d，
# 一旦某个占位符忘了转义，就会变成「把路径喂给 %d」的 TypeError（2026-09-21 踩过）。
# 用 repr() + 唯一标记替换，彻底绕开转义问题。
COMPILE_SNIPPET = r'''
import glob, os, py_compile, sys, tempfile
HERE = @@HERE@@
bad = []
cf = os.path.join(tempfile.gettempdir(), '_wb_smoke_compile.pyc')
files = sorted(glob.glob(os.path.join(HERE, '*.py')))
for f in files:
    try:
        py_compile.compile(f, doraise=True, cfile=cf)
    except Exception as e:
        bad.append('%s: %s' % (os.path.basename(f), e))
print('compiled=%d bad=%d' % (len(files), len(bad)))
for b in bad:
    print('  ' + b)
sys.exit(1 if bad else 0)
'''.replace('@@HERE@@', repr(HERE))


GUARD_PROBE = 'guard_probe.md'


def _seed_guard_probe(tmp):
    """给 C4 造一个「人工精修版」哨兵：不带生成戳的归档文件。

    内容刻意模仿人工精修版（中文类型、精确字节 + download 次数），且**只有 1 条** ——
    这样「缩水守卫」（旧条数 > 新条数才拦）一定不触发，
    C4 拿到 rc=2 就唯一地证明是「人工精修守卫」在起作用，而不是别的守卫生效。
    """
    p = os.path.join(tmp, GUARD_PROBE)
    with open(p, 'w', encoding='utf-8') as f:
        f.write('# DRAGON BALL模型 原始记录归档 · 哨兵\n\n'
                '> 人工精修版哨兵 · 故意不含生成器标记\n\n'
                '## [1] 2026-09-20T21:40:29.897+0800 · 人工挑选的核心定调句…（核心定调）\n\n'
                '- **类型**: talk（问答）\n'
                '- **附件**（1）: 周度思考 2026.9.20.pdf（size 2,037,146 / download 791）\n\n'
                '---\n')
    return p


ANON_SRC = '_anon_src_probe.md'
ANON_DST = '_anon_dst_probe.md'


def _seed_anon_probe(tmp):
    """给 H5b 造一份「含真名」的假晨报，用来验证匿名化的**正向职责**。

    为什么必须造这份输入（2026-09-23）：H5 原先是不带参数跑的 —— 当天晨报没生成时
    它会崩栈（已修），可当天晨报**存在**时它会真去写 `outputs/..._匿名版.md`，
    等于冒烟往交付目录里塞产物。冒烟「需落盘的产物一律写临时目录」的原则
    在这里靠 `--src/--out` 才能真正做到。

    文件名带 `_` 前缀是本项目「按天中间产物」约定，`check_display_name.py`（G3）
    会跳过它们 —— 否则这份**故意含真名**的探针会在下一轮冒烟里被 G3 报成泄漏。
    """
    p = os.path.join(tmp, ANON_SRC)
    with open(p, 'w', encoding='utf-8') as f:
        f.write('# 知识星球晨报 · 匿名化冒烟探针（冒烟自建，不是交付物）\n\n'
                '## 卫斯李的投研笔记\n- 大鹏鸟 转述：流沙河 今日减仓\n\n'
                '## 短评&信息（可接ai）\n- 好运哥：…\n\n'
                '## 180K Research\n- AI 产业链 走强；浑水调研 / xxpq 亦提及\n\n'
                '关联报告：`outputs/知识星球晨报_2026-09-23.md`\n')
    return p


def build_stages(tmp):
    """返回 (stages, meta)。stage = (名称, 分类, argv, 期望rc集合, 联网, 慢)"""
    rep_abs = newest_by_mtime('outputs/作战报告_*.md')
    rep = os.path.relpath(rep_abs, ROOT) if rep_abs else None
    pay_abs = newest_by_mtime('payload_*.json', HERE)
    pay = pay_abs

    # 只替换 {PY}/{WB}/{ROOT}/{TMP} 这四个已知占位符，不用 str.format ——
    # 因为 A1 那一环的参数是**一整段 Python 代码**，代码里出现花括号就会把 .format 炸掉。
    _ph = {'PY': PY, 'WB': HERE, 'ROOT': ROOT, 'TMP': tmp}
    sub = lambda a: [re.sub(r'\{(PY|WB|ROOT|TMP)\}', lambda m: _ph[m.group(1)], x) for x in a]
    s = []
    add = lambda *x: s.append((x[0], x[1], sub(x[2]), x[3], x[4], x[5]))

    # ---- A. 预检 ----
    add('A1 根脚本语法编译', 'preflight', ['{PY}', '-c', COMPILE_SNIPPET], (0,), False, False)
    add('A2 静态结构审计 audit_pipeline', 'preflight', ['{PY}', '{WB}/audit_pipeline.py'], (0, 2), False, False)
    add('A3 聚合回归测试 run_tests', 'preflight', ['{PY}', '{WB}/run_tests.py'], (0,), False, True)

    # ---- B. 数据层 ----
    add('B1 指数代码注册表 market_codes', 'data', ['{PY}', '{WB}/market_codes.py'], (0,), False, False)
    add('B2 日线 OHLC（隔离槽位 smoke）', 'data',
        ['{PY}', '{WB}/get_daily_ohlc.py', '000001', '2', '--slot', 'smoke'], (0,), True, False)
    add('B3 技术指标 calc_tech', 'data',
        ['{PY}', '{WB}/calc_tech.py', '--code', '000001', '--out', '{TMP}/tech.json', '--quiet'], (0,), True, False)
    add('B4 多周期技术位 calc_tech_multi', 'data',
        ['{PY}', '{WB}/calc_tech_multi.py', '--code', 'sh000001', '--out', '{TMP}/tech_multi.json', '--quiet'],
        (0,), True, True)

    # ---- C. 抓取层 ----
    add('C1 星球抓取 afternoon 窗口', 'fetch',
        ['{PY}', '{WB}/fetch_zsxq.py', '--window', 'afternoon'], (0, 2), True, True)
    add('C2 抓取摘要 digest_zsxq', 'fetch',
        ['{PY}', '{WB}/digest_zsxq.py', '--out', '{TMP}/digest.txt', '--limit', '5'], (0,), False, False)
    # C3 走 --out 写到临时目录：既验证归档生成能跑，又完全不碰当天交付物。
    add('C3 DRAGON BALL模型 原文归档（写临时路径）', 'fetch',
        ['{PY}', '{WB}/gen_tj_archive.py', '--out', '{TMP}/tj_archive.md'], (0, 2), False, False)
    # C4 人工精修守卫：哨兵文件**故意不带生成戳**，脚本必须拒绝覆盖并退 2。
    #    这是 2026-09-21 那次 P0（机械版静默覆盖人工精修版）的回归闸门。
    _seed_guard_probe(tmp)
    add('C4 归档精修守卫（必须拒绝覆盖）', 'fetch',
        ['{PY}', '{WB}/gen_tj_archive.py', '--out', '{TMP}/guard_probe.md'], (2,), False, False)

    # ---- D. 引擎层 ----
    # D1 退出码 1（行情未取到）/ 2（引擎降级）都是**数据侧信号**，不是脚本坏：
    #   行情真断了，同轮的 B2（日线 OHLC，期望 0）会先红；引擎真坏了，D2/D3 会先红。
    #   故此处三个码都收，避免同一次环境抖动把 D1 也报成 FAIL（与 F2/F3/G1/G2 同口径）。
    add('D1 一键预判数据包 forecast_analyze', 'engine',
        ['{PY}', '{WB}/forecast_analyze.py', '000001'], (0, 1, 2), True, True)
    # D2 带 --out 写临时目录（2026-09-23 加）：原先它写死 outputs/000001_四周期联动_<日期>.json，
    #   冒烟每跑一次就往交付目录落一份「冒烟数据」，还会覆盖当天真实数据包。
    #   期望码含 1：新增的数据充足性守卫在行情不足时退 1 且**不写数据包**（数据侧信号，
    #   与 D1 同口径；真崩了由「崩栈即失败」那条硬判据兜住）。
    add('D2 四周期联动 analyze_000001_multi', 'engine',
        ['{PY}', '{WB}/analyze_000001_multi.py', '--out', '{TMP}/multi_000001.json'],
        (0, 1), True, True)
    add('D3 申万行业缠论 run_sw_chansignal', 'engine',
        ['{PY}', '{WB}/run_sw_chansignal.py', '--code', '801080'], (0,), True, True)
    add('D4 引擎有效性复盘 engine_effectiveness', 'engine',
        ['{PY}', '{WB}/engine_effectiveness.py'], (0,), False, False)

    # ---- E. 行业层 ----
    add('E1 申万实时行情 scan_sw_realtime', 'industry',
        ['{PY}', '{WB}/scan_sw_realtime.py'], (0,), True, True)
    add('E2 同花顺行业方向分 scan_ths', 'industry',
        ['{PY}', '{WB}/scan_ths.py'], (0, 2), True, True)
    add('E3 行业强弱榜 industry_rank', 'industry',
        ['{PY}', '{WB}/industry_rank.py'], (0,), False, False)

    # ---- F. 链层 ----
    add('F1 链状态自检 chainlib', 'chain', ['{PY}', '{WB}/chainlib.py'], (0,), False, False)
    add('F2 偏差重算 chain_apply --bias-only', 'chain',
        ['{PY}', '{WB}/chain_apply.py', '--bias-only'], (0, 2), False, False)
    if pay:
        add('F3 链操作幂等预演 chain_apply --dry-run', 'chain',
            ['{PY}', '{WB}/chain_apply.py', '--payload', pay, '--dry-run'], (0, 1, 2), False, False)

    # ---- G. 校验层 ----
    if rep:
        add('G1 版面体检 check_layout（最新报告）', 'validate',
            ['{PY}', '{WB}/check_layout.py', rep], (0, 1, 2), False, False)
    add('G2 数据完整性 check_integrity', 'validate',
        ['{PY}', '{WB}/check_integrity.py'], (0, 1, 2), False, False)
    add('G3 显示名守卫 check_display_name', 'validate',
        ['{PY}', '{WB}/check_display_name.py', '--today', time.strftime('%Y-%m-%d')], (0, 1), False, False)
    # rc=1 = audit_coverage 判出「有真盲区」（源码 `return 1 if blind else 0`），
    # 属**信号**而非故障，所以 1 也是预期值。（首轮冒烟漏了它 → 一次假 FAIL。）
    add('G4 行业覆盖审计 audit_coverage', 'validate',
        ['{PY}', '{WB}/audit_coverage.py'], (0, 1, 2), False, False)

    # ---- H. 输出层 ----
    add('H1 走势图 SVG（重绘到临时路径）', 'output',
        ['{PY}', '{WB}/gen_forecast_svg.py', '--out', '{TMP}/forecast.svg'], (0,), False, False)
    add('H2 md_to_html 无参守卫', 'output',
        ['{PY}', '{WB}/md_to_html_report.py'], (1,), False, False)
    add('H3 md_to_html 不存在文件守卫', 'output',
        ['{PY}', '{WB}/md_to_html_report.py', '{TMP}/nosuch.md'], (1,), False, False)
    if rep:
        # 2026-09-23：改前这里不带 --out，而该脚本当时把输出路径写死为「与输入同目录同名 .html」
        # → **每次都往真实交付目录 outputs/ 落一个 HTML**，与冒烟「零副作用」的自述冲突
        # （实测被 `受保护范围新增文件 1 个：outputs/作战报告_午间_2026-09-23.html` 抓到）。
        # 已给脚本加 --out，本阶段随之重定向到临时目录。
        add('H4 md_to_html 正常路径（重定向到临时路径）', 'output',
            ['{PY}', '{WB}/md_to_html_report.py', rep, '--out', '{TMP}/report.html'],
            (0,), False, False)
        # H4b：--out 指向不存在的目录必须**有意报错**（rc=1 + [FAIL]），不许静默落到别处
        add('H4b md_to_html --out 目录不存在守卫', 'output',
            ['{PY}', '{WB}/md_to_html_report.py', rep, '--out', '{TMP}/nodir/x.html'],
            (1,), False, False)
    # H5 失败路径：输入不存在时必须**有意报错**（rc=1 + [FAIL]），而不是 traceback。
    #   2026-09-23 之前它不带参数跑，当天晨报没生成时就是 FileNotFoundError 崩栈 ——
    #   期望集合含 1，所以旧冒烟判 [OK]；「崩栈即失败」那条硬判据一上就抓出来了。
    #   现在显式给一个**一定不存在**的 --src：判据不再依赖「今天有没有生成晨报」。
    #   「失败时不产出产物」这一条由 test_degrade_exitcodes §9 断言（阶段模型只管退出码）。
    add('H5 匿名化 缺输入必须有意报错', 'output',
        ['{PY}', '{WB}/anonymize_report.py',
         '--src', '{TMP}/_anon_nosuch.md', '--out', '{TMP}/_anon_must_not_exist.md'],
        (1,), False, False)
    # H5b 正向路径：真跑一遍匿名化（输入/输出都在临时目录），验证映射表真的能脱敏。
    #   为什么不直接用当天晨报：那会往 outputs/ 落一份 `_匿名版.md`，冒烟就有了副作用。
    _seed_anon_probe(tmp)
    add('H5b 匿名化 正向（真名→代号）', 'output',
        ['{PY}', '{WB}/anonymize_report.py',
         '--src', '{TMP}/' + ANON_SRC, '--out', '{TMP}/' + ANON_DST],
        (0,), False, False)

    meta = {'report': rep, 'payload': pay}
    return s, meta


def main(argv=None):
    ap = argparse.ArgumentParser(description='全链路冒烟测试（默认零副作用）')
    ap.add_argument('--no-net', action='store_true', help='跳过联网阶段')
    ap.add_argument('--no-slow', action='store_true', help='跳过慢阶段（回归测试/引擎/扫描）')
    ap.add_argument('--only', default=None, metavar='SUBSTR', help='只跑名字含该子串的阶段')
    ap.add_argument('--tmp', default=DEFAULT_TMP, help='临时目录（默认 .workbuddy/_smoke_tmp）')
    ap.add_argument('--out', default=None, help='报告落盘路径（默认系统临时目录）')
    ap.add_argument('--keep-tmp', action='store_true', help='保留临时目录')
    a = ap.parse_args(argv)

    tmp = os.path.join(a.tmp, 'run_%s' % time.strftime('%Y%m%d_%H%M%S'))
    os.makedirs(tmp, exist_ok=True)

    stages, meta = build_stages(tmp)
    if a.only:
        stages = [x for x in stages if a.only in x[0] or a.only in x[1]]
    if a.no_net:
        stages = [x for x in stages if not x[4]]
    if a.no_slow:
        stages = [x for x in stages if not x[5]]
    if not stages:
        sys.stderr.write('[FAIL] 没有匹配的阶段\n')
        return 1

    L = []
    W = L.append
    W('=' * 78)
    W('全链路冒烟测试 · %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
    W('临时目录 %s' % tmp)
    W('最新报告 %s' % (meta['report'] or '(无)'))
    W('最新 payload %s' % (os.path.basename(meta['payload']) if meta['payload'] else '(无)'))
    W('阶段 %d 个%s' % (len(stages), '（已过滤）' if a.only or a.no_net or a.no_slow else ''))
    W('=' * 78)

    # ── 跑前快照 ──
    prot_before = collect()
    may_before = collect_may()
    files_before = list_scope()
    # 备份收进**单个 zip**，不做几百个散文件拷贝：散文件会让临时目录膨胀到 700+ 个，
    # 清理时直接撞环境的安全删除闸门（2026-09-21 实测：冒烟在第一行就被拦死）。
    BKZIP = os.path.join(tmp, 'protected_backup.zip')
    with zipfile.ZipFile(BKZIP, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel in prot_before:
            z.write(os.path.join(ROOT, rel), rel)
    W('受保护文件 %d 个已取快照（备份为单个 zip，可回滚）' % len(prot_before))

    # ── 执行 ──
    results = []
    for name, cat, cmd, expect, net, slow in stages:
        t0 = time.time()
        # 慢阶段（build_stages 第 6 字段 slow=True）用放宽后的额度，其余阶段维持 TIMEOUT。
        _to = TIMEOUT_SLOW if slow else TIMEOUT
        try:
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=_to,
                               env=dict(os.environ, PYTHONIOENCODING='utf-8'))
            rc, out, err, to = r.returncode, r.stdout or '', r.stderr or '', False
        except subprocess.TimeoutExpired as e:
            rc, out, err, to = 124, (e.stdout or '') if isinstance(e.stdout, str) else '', '', True
            # 超时是真失败，不是噪声 —— 把额度写进输出，便于区分「额度不够」与「脚本卡死」
            err = '[TIMEOUT] 超过本阶段墙钟上限 %ds（慢阶段额度 %ds）\n' % (_to, TIMEOUT_SLOW)
        dt = time.time() - t0
        blob = out + err
        tb = TB_MARK in blob and name not in ALLOW_TB
        ok = (rc in expect) and not tb
        results.append({'name': name, 'cat': cat, 'rc': rc, 'expect': expect, 'ok': ok,
                        'tb': tb, 'to': to, 'dt': dt, 'out': out, 'err': err})
        W('  [%s] %-42s rc=%-4s %6.1fs%s' % (
            'OK  ' if ok else ('TIME' if to else 'FAIL'), name, rc, dt,
            '  ← 崩栈（有 traceback，退出码合格也不算过）' if tb else
            ('  ← 超时（额度 %ds；慢阶段 %ds）' % (_to, TIMEOUT_SLOW) if to else '')))

    # ── 跑后核对：受保护文件 ──
    # 口径：MAY_CHANGE 优先。命中 MAY_CHANGE 的文件不参与「受保护」判定，
    # 否则一个文件同时命中两边就会永久假 FAIL。
    may_hit = lambda rel: _match(rel, MAY_CHANGE_GLOBS)
    prot_after = collect()
    changed = sorted(r for r in prot_before
                     if not may_hit(r) and prot_before[r] != prot_after.get(r))
    missing = sorted(r for r in prot_before if not may_hit(r) and r not in prot_after)
    added_prot = sorted(r for r in prot_after
                        if r not in prot_before and not may_hit(r))

    # ── 跑后核对：允许变化 / 新增文件 ──
    files_after = list_scope()
    # new_files 要排除 MAY_CHANGE 命中项，否则同一个文件会被**双重报告**：
    # 既进「按设计新增」的 INFO，又进「需要人工归置」的 WARN。
    # （2026-09-21 实测：.workbuddy/_bias_test_tmp.json 同时出现在两处，制造了一次假 WARN。）
    new_files = sorted(f for f in (files_after - files_before)
                       if not _match(f, MAY_CHANGE_GLOBS))
    may_changed, may_new = [], []
    for rel, h in sorted(may_before.items()):
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            may_changed.append(rel + '（被删除）')
        elif md5(p) != h:
            may_changed.append(rel)
    for g in MAY_CHANGE_GLOBS:
        for p in glob.glob(os.path.join(ROOT, g)):
            rel = os.path.relpath(p, ROOT).replace('\\', '/')
            if rel not in may_before:
                may_new.append(rel)

    W('')
    W('-' * 78)
    W('① 阶段结果')
    fail = [r for r in results if not r['ok']]
    if fail:
        for r in fail:
            why = []
            if r['rc'] not in r['expect']:
                why.append('退出码 %s 不在期望 %s 内'
                           % (r['rc'], '/'.join(map(str, r['expect']))))
            if r.get('tb'):
                why.append('输出含 traceback（未捕获异常，崩栈不是失败路径）')
            W('  [FAIL] %s  rc=%s —— %s' % (r['name'], r['rc'], '；'.join(why) or '?'))
            tail = [x for x in (r['out'] + r['err']).splitlines() if x.strip()][-12:]
            for ln in tail:
                W('         | %s' % ln[:150])
    else:
        W('  全部 %d 个阶段退出码符合预期，且无一阶段崩栈' % len(results))
    W('')
    W('② 副作用核对（冒烟不该改动交付物与链）')
    if changed:
        W('  [FAIL] 受保护文件被改动 %d 个 —— 这是 BUG，已回滚：' % len(changed))
        for rel in changed:
            try:
                with zipfile.ZipFile(BKZIP) as z:
                    data = z.read(rel)
                with open(os.path.join(ROOT, rel), 'wb') as o:
                    o.write(data)
                W('         %s（已回滚）' % rel)
            except Exception as e:
                W('         %s（**回滚失败**：%s）' % (rel, e))
    if missing:
        W('  [FAIL] 受保护文件消失 %d 个：%s' % (len(missing), ', '.join(missing)))
    if added_prot:
        W('  [WARN] 受保护范围新增文件 %d 个：%s' % (len(added_prot), ', '.join(added_prot)))
    if not (changed or missing or added_prot):
        W('  受保护文件 %d 个全部未变（两条链 + outputs 交付物 + 文档 + 脚本）' % len(prot_before))
    if may_changed:
        W('  [INFO] 以下文件按设计发生变化（抓取/扫描阶段的正常产出）：')
        for rel in may_changed:
            W('         %s' % rel)
    if may_new:
        W('  [INFO] 按设计新增的抓取/缓存产物 %d 个：' % len(may_new))
        for rel in may_new:
            W('         %s' % rel)
    if new_files:
        W('  [WARN] 新增文件 %d 个（冒烟产生的旁路产物，需要人工归置）：' % len(new_files))
        for f in new_files:
            W('         %s' % f)

    W('')
    W('③ 语义核对（**独立于 md5**：直接看产物内容对不对，不是只看有没有被改）')
    W('   为什么要有这一节：「没被改过」与「内容是对的」是两件事 ——'
      '脚本 rc=0 但产物写错时，md5 前后一致，全链路照样全绿。')
    sem_warns = []
    sem_infos = []
    sem_checked, sem_problems = semantic_check(sem_warns, sem_infos)
    if sem_problems:
        for rule, rel, msg in sem_problems:
            W('  [WARN] %s' % rel)
            W('         %s' % msg)
        W('   注：语义问题**不参与 FAIL 判定**（降级为 WARN），因为它是"存量内容"判据 ——'
          '若因一条历史产物不合规就把整轮冒烟判红，闸门会被无视（与 2026-09-17 清掉的'
          '「永久噪声」同类）。但每期都会打印出来，不会被埋掉。')
    else:
        W('  ✅ %d 份受保护交付物身份自洽（走势图自述目标日 == 文件名日期；报告文件名日期在正文中可见）'
          % sem_checked)
    # INFO 通道：已知历史遗留（旧格式 <desc> 等）。**必须打印但不算问题** ——
    # 不打印就变成了「静默豁免」，那和没有这条规则一样；
    # 算成 WARN 又会每轮刷屏，把真 WARN 淹掉。折中是：列出来、说清自愈路径、退出码不动。
    if sem_infos:
        W('  [INFO] 已知历史遗留 %d 条（不需处理，重跑该档即自愈）：' % len(sem_infos))
        for s in sem_infos:
            W('         %s' % s)

    rc = 1 if (fail or changed or missing) else (2 if (added_prot or new_files or sem_problems) else 0)
    W('')
    W('=' * 78)
    W('汇总：阶段 %d · 通过 %d · 失败 %d（其中崩栈 %d）· 受保护文件被改 %d · 新增文件 %d'
      % (len(results), len(results) - len(fail), len(fail),
         sum(1 for r in results if r.get('tb')), len(changed), len(new_files)))
    W('      语义核对 %d 份 / 问题 %d 条' % (sem_checked, len(sem_problems)))
    W('')
    W('⚠️ 结论边界（必读）：本轮「0 改动」只证明**这段时间没有脚本乱写**，')
    W('   **不证明产物内容正确**。内容正确性由三处独立保证：')
    W('     · 本节③ 语义核对（身份自洽，弱判据，覆盖存量）；')
    W('     · `check_integrity.py`【5】【7】【8】（链-报告-走势图三者对应）；')
    W('     · `run_tests.py` 的单元/回归断言（强判据，覆盖逻辑）。')
    W('   三者都不覆盖的，属尚未被发现 —— 不要因为本条打印 ALL PASS 就认定产物无误。')
    W('RESULT: %s' % ('ALL PASS' if rc == 0 else ('WARN' if rc == 2 else 'FAIL')))
    W('=' * 78)

    blob = '\n'.join(L)
    print(blob)
    outp = a.out or os.path.join(os.environ.get('TEMP', HERE),
                                 'wb_smoke_%s.txt' % time.strftime('%Y%m%d_%H%M%S'))
    try:
        with open(outp, 'w', encoding='utf-8') as f:
            f.write(blob)
        print('\n[报告已写出] %s' % outp)
    except Exception as e:
        print('\n[WARN] 报告写盘失败：%s' % e)

    if not a.keep_tmp:
        _cleanup(tmp)
    return rc


if __name__ == '__main__':
    sys.exit(main())
