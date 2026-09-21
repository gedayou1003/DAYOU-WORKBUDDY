# -*- coding: utf-8 -*-
"""check_layout 排版读感三项新检查（审计 5.1/5.3/5.4）与 5.2 阈值扩容的变异测试。

为什么要写这个测试
------------------
2026-09-18 全链路审计第 5 章指出三类「机器完全能查、却没人查」的排版问题：
  5.1 长文本列被挤成竖条（第二块「说明」列实测 202 字/格）
  5.3 同一对象两种术语写法（`30F55` vs `30F MA55`；MA20 与 BOLL 中轨实为同一数）
  5.4 附录 B 列 10 个星球、附录 A 只列 7 个，没有一句「本期未覆盖」
为此给 check_layout 加了第 9~11 类检查（规则见 layout_spec 的
TABLE_CELL_RULES / TERM_RULES / APPENDIX_COVERAGE），并给第 6 类的结论短语表扩了容。

但**加了检查 ≠ 检查有效**：一个永远报绿的检查器等于没有检查器（《脚本地图》教训 3）。
本测试按 assertion-gate-hardening 的方法做**双向元测试**：

  正向 —— 注入问题，必须真的报 WARN（该红的要红）；
  反向 —— 合法写法必须不报（不该红的不红）。
          **闸门最贵的故障是假阳性**：它会让「0 WARN」这道门槛被无视 ——
          人的反应是「又来了」，然后就再也不看告警了。

另单独验证「规则生效起点（since）」机制本身：规则在 t 时刻确立，只约束 t 之后生成的报告；
早于起点的报告要**打 INFO 明示豁免**（不是静默跳过，也不是照旧判红）——
静默跳过等于把闸门偷偷调松却不说。

组织方式
--------
§0 基线：一份合规报告 → 0 ERROR / 0 WARN（证明新检查不会把干净报告搞红）
§1 表格宽度（5.1）：分层阈值 + 边界 + 标记符号不计入
§2 术语口径（5.3）：三条判据的正反两面，含「跨级别不算混用」这类精度用例
§3 附录覆盖（5.4）：缺失要红、显式「未覆盖」不红、无附录不误报
§4 结论短语阈值（5.2）：超限要红、临界不红、since 未到要豁免
§5 since 机制：起点前一天全豁免、起点当天生效（边界含当天）

用法：$PY .workbuddy/test_layout_typography.py
退出码：0=全部通过，1=有断言失败
"""
import contextlib
import datetime
import importlib.util
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_s = importlib.util.spec_from_file_location('cl', os.path.join(HERE, 'check_layout.py'))
cl = importlib.util.module_from_spec(_s)
_s.loader.exec_module(cl)

import layout_spec as spec_mod  # noqa: E402  （check_layout 内部 import 的就是它）

fails = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------
LEVEL_TABLE_OK = (
    '| 关键位 | 价格 | 相对现价 | 属性 | 依据 |\n'
    '|---|---|---|---|---|\n'
    '| 周线一卖 | 3995.18 | +3.09% | 压力（远期） | 周线中枢下沿上方 |\n'
    '| 30F MA20（贴身第一支撑） | 3874.69 | -0.02% | 支撑 | 现价正下方最近的均线 |\n'
)

LEVEL_TABLE_DASH = (
    '| 关键位 | 价格 | 相对现价 | 属性 | 依据 |\n'
    '|---|---|---|---|---|\n'
    '| 周线一卖 | 3995.18 | +3.09% | 压力（远期） | 周线中枢下沿上方 |\n'
    '| **现价** | **3875.60** | **0.00%** | — | 9/17 收盘 |\n'
    '| 30F MA20（贴身第一支撑） | 3874.69 | -0.02% | 支撑 | 现价正下方最近的均线 |\n'
)

LEVEL_TABLE_NOATTR = (          # 没有「属性」列 —— 不该被误报
    '| 关键位 | 价格 | 相对现价 |\n'
    '|---|---|---|\n'
    '| 周线一卖 | 3995.18 | +3.09% |\n'
)

APPENDIX_A_OK = (
    '| 通道 | 工具 | 星球 | 条数 | 备注 |\n'
    '|---|---|---|---|---|\n'
    '| 通道 A | `zsxq-cli` | 卫斯李的投研笔记 | 11 | 隔夜机构观点 |\n'
    '| 通道 B | api.zsxq.com | 大鹏鸟笔记 | 2 | 盘前热榜 |\n'
)

# 与附录 B 相比少一行「信息平权」——正是 9/18 版本的实际缺口（B 列 10 个、A 只列 7 个）
APPENDIX_A_MISS = APPENDIX_A_OK

# 补齐后覆盖完整（基线用）
APPENDIX_A_FULL = APPENDIX_A_MISS + \
    '| 通道 B | api.zsxq.com | 信息平权 | 0 | 窗口内无新增 |\n'

# 显式点名说明：读者知道是谁没覆盖、为什么 —— 不该报红
APPENDIX_A_DECLARED = APPENDIX_A_MISS + \
    '\n- **本期未覆盖**：星球 ③ 信息平权（通道未返回数据）\n'

# 说了"有没覆盖的"但**不点名** —— 读者仍被通知到，故不报红，只提示一句
APPENDIX_A_VAGUE = APPENDIX_A_MISS + \
    '\n- **本期有 1 个星球未覆盖**（通道未返回数据），明细见附录 B 的抓取通道列。\n'

APPENDIX_B = (
    '| 代号 | 星球 | 内容侧重 | 抓取通道 |\n'
    '|---|---|---|---|\n'
    '| 星球 ① | 卫斯李的投研笔记 | 海外研报 | A (zsxq-cli) |\n'
    '| 星球 ② | 大鹏鸟笔记 | 盘前热榜 | B (Cookie) |\n'
    '| 星球 ③ | 信息平权 | 资讯平权 | B (Cookie) |\n'
)


def report(date, tech='正文。', level_table=LEVEL_TABLE_OK,
           app_a=APPENDIX_A_FULL, app_b=APPENDIX_B):
    """一份结构完整的晨报夹具。app_a/app_b 传 None 表示整节不出现（如复盘档）。

    注意：模板里含 `+1.2%` 这类字面百分号，所以不能用 `%` 格式化拼串（会当成格式符），
    一律用拼接。
    """
    sec_a = ('## 附录 A 抓取通道信息\n\n' + app_a + '\n\n') if app_a is not None else ''
    sec_b = ('## 附录 B 星球代号对照表\n\n' + app_b + '\n\n') if app_b is not None else ''
    return (
        '# 作战报告 · 晨报（变异测试样本）\n\n'
        '## 核心主线速览\n\n- 一句话结论\n\n'
        '## 第一块 星球信息\n\n事实落地。\n\n'
        '## 第二块 信息判断（跨星球观点对比）\n\n'
        '#### 共同观点\n\n- 一点\n\n#### 相反观点\n\n- 一点\n\n'
        '## 第三块 技术分析\n\n' + tech + '\n\n'
        '## 第四块 预判\n\n![走势图](forecast_x.svg)\n\n' + level_table + '\n\n'
        '## 四、偏差观察统计表\n\n（表略）\n\n'
        '## 第五块 行业强弱榜\n\n'
        '| 行业 | 涨跌幅 | 方向 | 置信度 |\n|---|---|---|---|\n| 电子 | +1.2% | BULL | 0.7 |\n\n'
        + sec_a + sec_b +
        '## 产物清单\n\n| 路径 | 类型 | 说明 |\n|---|---|---|\n| a.svg | 图 | 走势图 |\n'
    )


def run(text, date):
    """在沙箱 outputs/ 里落一份报告并体检。ROOT 也要指向沙箱（同日报查重会扫 outputs/）。"""
    sb = tempfile.mkdtemp(prefix='layout_typo_')
    os.makedirs(os.path.join(sb, 'outputs'))
    p = os.path.join(sb, 'outputs', '作战报告_晨报_%s.md' % date)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)
    saved = cl.ROOT
    cl.ROOT = sb
    try:
        return cl.check(p)
    finally:
        cl.ROOT = saved
        shutil.rmtree(sb, ignore_errors=True)


def W(res, prefix):
    return [w for w in res['warns'] if w.startswith(prefix)]


def I(res, sub):
    return [i for i in res.get('infos', []) if sub in i]


def ncell(n, wrap=False):
    """造一个「读者可见宽度」为 n 字的单元格；wrap=True 时套 ** 加粗（标记不该计入）。"""
    body = '依' * n
    return ('**%s**' % body) if wrap else body


def tbl(*cols):
    """cols = 每列 (表头, 数据)。"""
    header = '| ' + ' | '.join(c[0] for c in cols) + ' |'
    sep = '|' + '---|' * len(cols)
    row = '| ' + ' | '.join(c[1] for c in cols) + ' |'
    return '\n'.join([header, sep, row])


# 生效起点：直接从 spec 取，别把 2026-09-19 抄进测试（改规则时要跟着改）
SINCE = min([spec_mod.TABLE_CELL_RULES['since'], spec_mod.APPENDIX_COVERAGE['since']]
            + [v['since'] for v in spec_mod.TERM_RULES.values()])
D_BEFORE = (datetime.date.fromisoformat(SINCE) - datetime.timedelta(days=1)).isoformat()
D_AT = SINCE
TODAY = datetime.date.today().isoformat()


@contextlib.contextmanager
def active_since():
    """把所有新规则的 since 临时挪到 2000-01-01 —— 本轮只测**逻辑**，不测日期门槛。

    日期门槛由 §5 单独测。两者混在一起会把「检查写错了」和「规则还没生效」
    两种完全不同的失败原因搅在一起。
    """
    saved = []

    def patch(obj, key):
        saved.append((obj, key, obj.get(key)))
        obj[key] = '2000-01-01'

    patch(spec_mod.TABLE_CELL_RULES, 'since')
    for v in spec_mod.TERM_RULES.values():
        patch(v, 'since')
    patch(spec_mod.APPENDIX_COVERAGE, 'since')
    sm = spec_mod.DUP_RULES['phrase'].get('since_map') or {}
    for k in list(sm):
        patch(sm, k)
    try:
        yield
    finally:
        for obj, key, val in saved:
            obj[key] = val


ck(cl.spec is spec_mod, 'check_layout 与本测试引用同一个 layout_spec 模块（补丁才生效）')
print('规则生效起点 = %s（起点前一天 %s）｜今天 %s' % (SINCE, D_BEFORE, TODAY))


@contextlib.contextmanager
def pending_since(phrase):
    """把某条新增结论短语的生效起点临时推到**明天** —— 构造「规则尚未生效」的场景。

    ⚠️ 为什么不能改用「把报告日期写成 SINCE 前一天」来构造（2026-09-21 踩过）：
      `check_layout.py` 第 191 行有一道 `_is_today_report()` 早退闸门 ——
      **只对当日报告**做全篇计数，报告日期一旦不是今天，整节直接 return，
      连豁免 INFO 都不会打。
      于是「报告日期 < since」与「报告是今天的」这两个条件，
      在日历越过 SINCE 之后变成**互斥**：「since 未到」这条路径再也没法用真实日期覆盖。
      → 正确做法是反过来：报告仍用今天，把**规则起点**临时推到未来。
        这样断言与日历解耦，不会再自坏。
    """
    sm = spec_mod.DUP_RULES['phrase'].get('since_map') or {}
    saved = sm.get(phrase)
    sm[phrase] = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    try:
        yield sm[phrase]
    finally:
        sm[phrase] = saved


# ---------------------------------------------------------------------------
print('\n§0 基线：合规报告不该被新检查搞红')
with active_since():
    res0 = run(report(D_AT), D_AT)
ck(not res0['errors'], '0 ERROR（实测 %d：%s）' % (len(res0['errors']), res0['errors'][:2]))
ck(not res0['warns'], '0 WARN（实测 %d：%s）' % (len(res0['warns']), res0['warns'][:3]))


# ---------------------------------------------------------------------------
print('\n§1 表格宽度（审计 5.1）—— 阈值按列数分层：≤3列 120 / 4列 90 / ≥5列 80')

with active_since():
    # 1a 3 列表格塞 150 字 → 该红
    t = tbl(('项目', '上期共识'), ('结论', '命中'), ('说明', ncell(150)))
    w = W(run(report(D_AT, tech=t), D_AT), '表格宽度·')
    ck(bool(w), '3 列 × 150字 → 报 WARN（实测 %d 条）' % len(w))
    if w:
        ck('上限 120' in w[0], '提示里点明该表列数对应的上限 120')

    # 1b 恰好 120 字 → 不该红（边界：> 才算超）
    w = W(run(report(D_AT, tech=tbl(('甲', 'x'), ('乙', 'y'), ('说明', ncell(120)))), D_AT),
          '表格宽度·')
    ck(not w, '3 列 × 恰好 120字 → 不报（边界，实测 %d 条）' % len(w))

    # 1c 120 字但套了 ** 加粗 → 不该红（标记符号不计入可见宽度）
    w = W(run(report(D_AT, tech=tbl(('甲', 'x'), ('乙', 'y'), ('说明', ncell(120, True)))),
              D_AT), '表格宽度·')
    ck(not w, '3 列 × 120字（含 ** 标记）→ 不报（标记不计宽，实测 %d 条）' % len(w))

    # 1d 4 列表格塞 100 字 → 该红（上限收紧到 90）
    t4 = tbl(('行业', '电子'), ('方向', 'BULL'), ('依据', ncell(100)), ('置信度', '0.7'))
    w = W(run(report(D_AT, tech=t4), D_AT), '表格宽度·')
    ck(bool(w), '4 列 × 100字 → 报 WARN')
    if w:
        ck('上限 90' in w[0], '4 列表格按 90 字判（列越多越窄）')

    # 1e 5 列表格塞 85 字 → 该红（上限 80）
    t5 = tbl(('行业', '电子'), ('涨跌幅', '+1.2%'), ('方向', 'BULL'),
             ('依据', ncell(85)), ('置信度', '0.7'))
    w = W(run(report(D_AT, tech=t5), D_AT), '表格宽度·')
    ck(bool(w), '5 列 × 85字 → 报 WARN')
    if w:
        ck('上限 80' in w[0], '5 列表格按 80 字判')

    # 1f 全部短单元格 → 不该红（防假阳性：附表/榜单的短表本来就合规）
    w = W(run(report(D_AT), D_AT), '表格宽度·')
    ck(not w, '全为短字段 → 不报（实测 %d 条）' % len(w))


# ---------------------------------------------------------------------------
print('\n§2 术语与口径（审计 5.3）')

with active_since():
    L55 = '术语·55 线写法混用'
    LB = '术语·MA20 与 BOLL 中轨并存且未注明等价'
    LD = '术语·关键位表出现无属性的行'

    # ① 55 线两种写法
    w = W(run(report(D_AT, tech='30F55 压制，30F MA55 同点。'), D_AT), L55)
    ck(bool(w), '同一级别写 30F55 与 30F MA55 → 报 WARN')
    if w:
        ck('30F' in w[0], '报出具体是哪一级别（30F）')

    w = W(run(report(D_AT, tech='15F55 与 30F55 均压制。'), D_AT), L55)
    ck(not w, '全篇只用紧凑写法 15F55/30F55 → 不报（实测 %d 条）' % len(w))

    w = W(run(report(D_AT, tech='15F MA55 与 30F MA55 均压制。'), D_AT), L55)
    ck(not w, '全篇只用全称写法 15F MA55/30F MA55 → 不报（实测 %d 条）' % len(w))

    # 精度用例：级别不同则不算混用 —— 判据建在「级别」这个键上，不是「写法」本身
    w = W(run(report(D_AT, tech='30F55 压制，15F MA55 支撑。'), D_AT), L55)
    ck(not w, '30F 用紧凑 + 15F 用全称（不同级别）→ 不报（实测 %d 条）' % len(w))

    # ② MA20 与 BOLL 中轨
    w = W(run(report(D_AT, tech='日线 MA20 与 60F 中轨同向。'), D_AT), LB)
    ck(bool(w), 'MA20 与「中轨」并存且无等价注明 → 报 WARN')

    w = W(run(report(D_AT, tech='日线 MA20 与 60F 中轨同向。\n\n> BOLL 中轨 ≡ MA20（数学恒等）\n'),
              D_AT), LB)
    ck(not w, '写了「BOLL 中轨 ≡ MA20」→ 不报（实测 %d 条）' % len(w))

    w = W(run(report(D_AT, tech='日线 MA20 与 60F 中轨同向。\n\n> 中轨即 MA20\n'), D_AT), LB)
    ck(not w, '等价注明用「即」的变体也算 → 不报（实测 %d 条）' % len(w))

    w = W(run(report(D_AT, tech='日线 MA20 是贴身第一支撑。'), D_AT), LB)
    ck(not w, '只提 MA20、不提中轨 → 不报（实测 %d 条）' % len(w))

    # ③ 关键位表「属性」列
    w = W(run(report(D_AT, level_table=LEVEL_TABLE_DASH), D_AT), LD)
    ck(bool(w), '关键位表出现「属性 = —」的现价行 → 报 WARN')
    if w:
        ck('现价' in w[0] or '第4列' in w[0], '报出具体是哪一行/哪一列')

    w = W(run(report(D_AT, level_table=LEVEL_TABLE_OK), D_AT), LD)
    ck(not w, '每行属性都填实（压力/支撑）→ 不报（实测 %d 条）' % len(w))

    w = W(run(report(D_AT, level_table=LEVEL_TABLE_NOATTR), D_AT), LD)
    ck(not w, '关键位表本来就没有「属性」列 → 不报、不崩（实测 %d 条）' % len(w))


# ---------------------------------------------------------------------------
print('\n§3 附录 A/B 星球覆盖口径（审计 5.4）')

with active_since():
    LP = '附录口径·'

    w = W(run(report(D_AT, app_a=APPENDIX_A_MISS), D_AT), LP)
    ck(bool(w), '附录 B 列了「信息平权」、附录 A 没有也没说明 → 报 WARN')
    if w:
        ck('信息平权' in w[0], '报出到底是哪个星球没交代（本次复现 9/18 的真实缺口）')

    res = run(report(D_AT, app_a=APPENDIX_A_DECLARED), D_AT)
    w = W(res, LP)
    ck(not w, '补了「本期未覆盖：星球 ③ 信息平权（通道未返回数据）」→ 不报（实测 %d 条）' % len(w))

    res = run(report(D_AT, app_a=APPENDIX_A_VAGUE), D_AT)
    w = W(res, LP)
    ck(not w, '只说「有 1 个星球未覆盖」但不点名 → 也不报（读者同样被通知到了）')
    ck(bool(I(res, '未覆盖')), '降为 INFO 说明「已显式说明未覆盖」——不是静默放过')

    w = W(run(report(D_AT, app_a=APPENDIX_A_FULL), D_AT), LP)
    ck(not w, '附录 B 的星球全在附录 A 里 → 不报（实测 %d 条）' % len(w))

    # 防误报：复盘档根本没有附录，不能因为「找不到附录 A」就报红
    res = run(report(D_AT, app_a=None, app_b=None), D_AT)
    w = W(res, LP)
    ck(not w, '报告没有附录 A/B（如复盘档）→ 不报（实测 %d 条）' % len(w))
    ck(bool(I(res, '未同时找到附录')), '降为 INFO 说明「未找到附录，跳过核对」')


# ---------------------------------------------------------------------------
print('\n§4 结论短语阈值扩容（审计 5.2）—— 这类检查仅对当日报告执行')
print('   阈值判定用 TODAY（配 active_since() 强制规则生效）；')
print('   「since 未到应豁免」用 pending_since() 把规则起点推到明天，')
print('   **不能**靠把报告日期写早 —— 会撞上 _is_today_report 早退闸门，连 INFO 都不打')

with active_since():
    tech7 = '\n'.join('- 第%d处：60F 中轨 是唯一否决点' % i for i in range(1, 8))
    tech6 = '\n'.join('- 第%d处：60F 中轨 是唯一否决点' % i for i in range(1, 7))
    LPHR = '排版重复·结论短语'

    w = W(run(report(TODAY, tech=tech7), TODAY), LPHR)
    ck(bool(w), '「60F 中轨」出现 7 次（上限 6）→ 报 WARN')
    if w:
        ck('60F 中轨×7' in w[0] or ('60F 中轨' in w[0] and '×7' in w[0]),
           '报出短语名与实测次数（60F 中轨×7）')

    w = W(run(report(TODAY, tech=tech6), TODAY), LPHR)
    ck(not w, '恰好 6 次（= 上限）→ 不报（边界）')

# 反向验证：规则起点晚于本报告 → 同样 7 次必须**不报 WARN**，但要打 INFO 说明豁免。
# 报告日期仍用 TODAY（否则撞上 _is_today_report 早退闸门，什么都测不到），
# 靠 pending_since() 把「60F 中轨」的起点临时推到明天来构造豁免场景。
# 2026-09-21 修复：原实现用 TODAY 做日期断言，日历越过 SINCE 后前提永久失效 → 测试连红两天。
with pending_since('60F 中轨') as future:
    res = run(report(TODAY, tech=tech7), TODAY)
    w = W(res, LPHR)
    ck(not w, 'since 未到（起点 %s 晚于报告 %s）时，同样 7 次不判红（实测 %d 条）'
       % (future, TODAY, len(w)))
    ck(bool(I(res, '60F 中轨')),
       '但打 INFO 明示「60F 中轨 阈值自 %s 起生效，本报告不参与」' % SINCE)


# ---------------------------------------------------------------------------
print('\n§5 规则生效起点（since）机制本身：起点前一天豁免、起点当天生效')
print('   （没有这一节，§1~§3 的通过就说明不了任何事 —— 可能只是规则压根没跑）')

# 同时注入三类问题，看它们是否按日期分别"响 / 不响"
bad = dict(tech=tbl(('甲', 'x'), ('乙', 'y'), ('说明', ncell(150))) + '\n30F55 与 30F MA55 同点。\n'
           + '日线 MA20 与 60F 中轨同向。',
           level_table=LEVEL_TABLE_DASH, app_a=APPENDIX_A_MISS)

res_before = run(report(D_BEFORE, **bad), D_BEFORE)
got = [p for p in ('表格宽度·', '术语·55 线', '术语·MA20', '术语·关键位表', '附录口径·')
       if W(res_before, p)]
ck(not got, '起点前一天（%s）注入全部三类问题 → 一条都不报红（实测 %s）' % (D_BEFORE, got or '无'))

labels = ['表格长文本单元格', '55 线写法混用', 'MA20 与 BOLL 中轨并存且未注明等价',
          '关键位表出现无属性的行', '附录 A/B 星球覆盖口径']
exempt_infos = I(res_before, '新增规则')
ck(len(exempt_infos) == 1, '豁免聚合成 1 条 INFO（实测 %d 条）' % len(exempt_infos))
if exempt_infos:
    line = exempt_infos[0]
    missing_lbl = [l for l in labels if l not in line]
    ck(not missing_lbl, '聚合条仍逐一点名 5 条规则（缺 %s）' % (missing_lbl or '无'))
    ck(SINCE in line, '写明生效日期 %s' % SINCE)
    ck('不参与' in line, '措辞是「不参与」——读者能看出是豁免，不是没查')

res_at = run(report(D_AT, **bad), D_AT)
got = [p for p in ('表格宽度·', '术语·55 线', '术语·MA20', '术语·关键位表', '附录口径·')
       if W(res_at, p)]
ck(len(got) == 5, '起点当天（%s，含当天）同样的报告 → 5 类全报红（实测 %d 类：%s）'
   % (D_AT, len(got), '、'.join(got) or '无'))


print()
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
for f in fails:
    print('  - %s' % f)
sys.exit(1 if fails else 0)
