# -*- coding: utf-8 -*-
"""链操作公共库（2026-09-16 维护新增 I-6）

背景
----
原先每期报告都要「复制上一份脚本 → 改 8-10 个日期字符串 → 改判定文本」，累积出 42 个
`add_morning_YYYY-MM-DD.py` / `review_consensus_close_YYYY-MM-DD.py` 等同构脚本（~304KB）。
骨架逐字相同，只有 payload 在变，既慢又容易漏改（9/15 共识复盘漏落盘即此类事故）。

本模块把骨架抽出来，payload 变为声明式 JSON。配套入口：
    - `add_forecast.py`  → forecast_chain：复盘上一条 + 追加本期
    - `review_chain.py`  → consensus_chain：复盘 + 追加；另可程序化输出偏差统计

核心保证
--------
1. **幂等**：目标 id 已存在 / 已有 review → 跳过，绝不重复写
2. **机器回读断言**（修复 9/15 事故的根因）：写盘后**重新从磁盘读回**，
   校验目标记录的 status，不一致直接非零退出 —— 不再依赖「人肉回读」
3. 兼容 chain 的 list / dict 两种结构（历史上有过 {'records': [...]} 形态）
"""
import json, os, sys, io

# 控制台编码加固（2026-09-16 巡检补丁）：Windows cmd 默认 cp936，无法编码 ✅/⚠️/❌，
# 直接 print 会 UnicodeEncodeError 崩溃（chainlib 自检 / chain_apply --bias-only 都中过）。
# errors='replace' 保证不崩（中文正常显示，无法表示的符号降级为 ?）；表格另有 ascii_safe 兜底。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except Exception:  # silent-ok: 终端编码收口尽力而为，失败不影响结论
        pass

HERE = os.path.dirname(os.path.abspath(__file__))

# 允许用环境变量重定向链目录（供自测/沙箱验证用，正常运行不设即可）
CHAIN_DIR = os.environ.get('CHAIN_DIR') or HERE

FORECAST = os.path.join(CHAIN_DIR, 'forecast_chain.json')
CONSENSUS = os.path.join(CHAIN_DIR, 'consensus_chain.json')

CHAINS = {'forecast': FORECAST, 'consensus': CONSENSUS}


# ---------------------------------------------------------------- 控制台符号

def _emoji_ok():
    """当前 stdout 能否编码三态 emoji（cp936 控制台不能）"""
    enc = getattr(sys.stdout, 'encoding', None) or 'utf-8'
    try:
        '\u2705\u26a0\ufe0f\u274c'.encode(enc)
        return True
    except Exception:  # silent-ok: 编码能力探测，False 即结论（表格另有 ascii_safe 兜底）
        return False


_SYM = {'hit': '\u2705', 'partial': '\u26a0\ufe0f', 'miss': '\u274c',
        'ok': '\u2705', 'bad': '\u274c', 'warn': '\u26a0\ufe0f'}
_SYM_ASCII = {'hit': '[O]', 'partial': '[~]', 'miss': '[X]',
              'ok': '[OK]', 'bad': '[FAIL]', 'warn': '[WARN]'}


def sym(kind):
    """三态/状态符号：控制台不支持 emoji 时自动降级为 ASCII，避免打印崩溃"""
    tbl = _SYM if _emoji_ok() else _SYM_ASCII
    return tbl.get(kind, '')


# ---------------------------------------------------------------- 读写

def chain_path(name):
    if name not in CHAINS:
        raise ValueError(f'未知链名: {name}（可选 forecast / consensus）')
    return CHAINS[name]


def load(name):
    """返回 (records, is_dict) —— 兼容 list 与 {'records': [...]}"""
    p = chain_path(name)
    with io.open(p, encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict):
        recs = data.get('records', [])
        return recs, True
    return (data if isinstance(data, list) else []), False


def save(name, recs, is_dict):
    p = chain_path(name)
    payload = {'records': recs} if is_dict else recs
    with io.open(p, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def find(recs, rid):
    return next((r for r in recs if r.get('id') == rid), None)


def status_of(name, rid):
    """从磁盘重新读取某条记录的 status（回读断言用）"""
    recs, _ = load(name)
    r = find(recs, rid)
    return None if r is None else r.get('status')


# ---------------------------------------------------------------- 变更

VERDICT_DIMS = ('direction', 'range', 'support', 'resistance')
# apply_review 校验未通过时 msg 的固定前缀，供调用方判定是否应非零退出
REJECT_PREFIX = '[拒绝]'
# 模板占位符标记：值里含此标记即视为「尚未填写」，
# 使 --init-template 既能用哨兵提示该填什么，又仍会被空壳校验拦下
PLACEHOLDER_MARK = '<<<'


def _is_unfilled(v):
    """非空字符串且不含占位符标记，才算真的填了"""
    return not (isinstance(v, str) and v.strip() and PLACEHOLDER_MARK not in v)


def _consensus_review_is_blank(review):
    """共识链（consensus）review 的空壳判定。

    共识链 review 的 schema 与 forecast 完全不同：它用 `per_topic`（逐条观点的
    兑现判定）+ `opposite_review`（对立观点/剧本复盘）承载内容，根本没有
    `direction_verdict` 之类的四维字段、也没有 `actual`。有效标志是：
    per_topic 里至少有一条 verdict 实填，或 opposite_review.verdict 实填。
    """
    pt = review.get('per_topic')
    if isinstance(pt, list):
        for it in pt:
            if isinstance(it, dict) and not _is_unfilled(it.get('verdict')):
                return False
    orv = review.get('opposite_review')
    if isinstance(orv, dict) and not _is_unfilled(orv.get('verdict')):
        return False
    # 兼容 --init-template 生成的早期形态 {review_time, items:[...]}
    items = review.get('items')
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict) and not _is_unfilled(it.get('verdict')):
                return False
    return True


def review_is_blank(review):
    """判断 review 是否为「空壳」（模板占位 / 忘填）。

    forecast 链空壳判定：四个维度判定全部为空，且 actual 无有效 close。
    这正是 `--init-template` 直接产出的形态。若放行，会把上一条 pending 误标为
    verified（四维 verdict 全空、actual.close=0），而幂等规则又使其**永久无法修正**
    （再提交只会打印「已有 review，幂等，不覆盖」），只能手改 JSON。

    2026-09-17 修复：本函数原先只按 forecast schema 判定，而 `chain_apply.py`
    对 consensus 链调用同一个 `apply_review`，导致**共识链 review 一律被判空壳而拒写**
    （共识链 review 里既没有 *_verdict 四维字段、也没有 actual，必然命中空壳条件）。
    现按 schema 分派：含 per_topic / opposite_review / items 的走共识链判定。
    """
    if not isinstance(review, dict):
        return True
    if ('per_topic' in review) or ('opposite_review' in review) or ('items' in review):
        return _consensus_review_is_blank(review)
    filled = 0
    for d in VERDICT_DIMS:
        v = review.get(d + '_verdict')
        if v is None:
            v = review.get(d)
        if not _is_unfilled(v):
            filled += 1
    actual = review.get('actual')
    has_close = bool(actual.get('close')) if isinstance(actual, dict) else False
    return filled == 0 and not has_close


def apply_review(recs, rid, review, verified_at=None, strict=True):
    """给某条记录写 review 并转 verified。幂等：已有 review 则跳过。

    strict=True（默认）时拒绝「空壳 review」：四维判定全空且无 actual.close 一律不写，
    返回 msg 以 '[拒绝]' 开头，调用方应据此非零退出。这是 2026-09-16 巡检发现的
    「模板忘填 → 上一条被误标 verified → 回读断言还报绿」陷阱的修复。

    返回 (changed: bool, msg: str)
    """
    r = find(recs, rid)
    if r is None:
        return False, f'[跳过] 未找到 {rid}'
    if r.get('review'):
        return False, f'[跳过] {rid} 已有 review（幂等，不覆盖）'
    if strict and review_is_blank(review):
        # 按 schema 给出对应的填写指引（共识链没有四维字段，照抄 forecast 的文案会误导）
        is_consensus = isinstance(review, dict) and (
            ('per_topic' in review) or ('opposite_review' in review) or ('items' in review))
        if is_consensus:
            hint = ('请先在 per_topic 中填入至少一条 verdict（✅/⚠️/❌ + 说明），'
                    '或填入 opposite_review.verdict（对立观点/剧本复盘结论）')
        else:
            hint = ('请先填写 %s 与 actual'
                    % ' / '.join(d + '_verdict' for d in VERDICT_DIMS))
        return False, (
            f'{REJECT_PREFIX} {rid} 的 review 是空壳（未填任何实质判定），已拒绝写入。'
            f'{hint}，否则该条会被误标 verified 且因幂等无法再修正。')
    r['review'] = review
    r['status'] = 'verified'
    if verified_at:
        r['verified_at'] = verified_at
    elif isinstance(review, dict) and review.get('reviewed_at'):
        r['verified_at'] = review['reviewed_at']
    return True, f'[复盘] {rid} 已写 review，status -> verified'


def record_has_placeholder(record):
    """record 的定调字段里是否残留模板占位符（说明忘改模板就提交了）"""
    for k in ('direction', 'range', 'confidence'):
        v = record.get(k)
        if isinstance(v, str) and PLACEHOLDER_MARK in v:
            return True
    return False


def upsert_pending(recs, record):
    """追加一条 pending 记录。幂等：id 已存在则跳过。

    返回 (changed: bool, msg: str)；msg 以 REJECT_PREFIX 开头表示被拒。
    """
    rid = record.get('id')
    if not rid:
        return False, '[跳过] record 缺 id 字段'
    if find(recs, rid) is not None:
        return False, f'[跳过] {rid} 已存在（幂等）'
    if record_has_placeholder(record):
        return False, (f'{REJECT_PREFIX} {rid} 的 direction/range/confidence 仍含模板占位符 '
                       f'（{PLACEHOLDER_MARK}），已拒绝写入。请改为实填内容。')
    record.setdefault('status', 'pending')
    recs.append(record)
    return True, f'[追加] {rid} 已写入，status={record["status"]}'


# ---------------------------------------------------------------- 偏差统计

def bias_stats(name='forecast', dims=None, exclude_ids=None):
    """程序化计算四维偏差统计（纯口径 + 含部分口径）。

    四维字段两代格式兼容：早期 review.{dim}，后期 review.{dim}_verdict。
    取值前缀 ✅ / ⚠️ / ❌。纯命中率 = ✅ ÷ (✅+⚠️+❌)，仅统计 status=='verified'。
    返回 {'periods': n, dims: {dim: {hit, partial, miss, pure, weighted}}}

    exclude_ids（2026-09-18 新增）：排除这些记录 id 后再统计。
    用途：`check_layout.py` 的「本期变化·基期对账」要反查**上一期**的四维真值，
    即「当前链去掉本期新增样本后的统计」。若无此入口，调用方只能自己复制一份
    读 verdict 的逻辑 —— 而两代字段（`direction` / `direction_verdict`）的兼容读法
    散落已经是审计点名的隐患（P1-3），不该再多繁殖一份。
    """
    if dims is None:
        dims = ['direction', 'range', 'support', 'resistance']
    recs, _ = load(name)
    skip = set(exclude_ids or ())
    verified = [r for r in recs
                if r.get('status') == 'verified' and r.get('id') not in skip]
    out = {'periods': len(verified), 'dims': {}}
    for d in dims:
        c = {'hit': 0, 'partial': 0, 'miss': 0}
        for r in verified:
            rv = r.get('review') or {}
            v = rv.get(d + '_verdict')
            if v is None:
                v = rv.get(d)
            if not isinstance(v, str):
                continue
            if v.startswith('✅'):
                c['hit'] += 1
            elif v.startswith('⚠️'):
                c['partial'] += 1
            elif v.startswith('❌'):
                c['miss'] += 1
        tot = c['hit'] + c['partial'] + c['miss']
        c['total'] = tot
        c['pure'] = round(c['hit'] / tot * 100, 1) if tot else None
        c['weighted'] = round((c['hit'] + c['partial'] * 0.5) / tot * 100, 1) if tot else None
        out['dims'][d] = c
    return out


def render_bias_table(stats, ascii_safe=None):
    """渲染偏差统计 Markdown 表（供报告直接粘贴）

    ascii_safe=None 时按当前 stdout 能力自动判定：cp936 控制台自动降级为
    [O]/[~]/[X]，避免 UnicodeEncodeError（报告文件仍应写完整 emoji，
    程序化写文件时显式传 ascii_safe=False）。
    """
    if ascii_safe is None:
        ascii_safe = not _emoji_ok()
    sh, sp, sm = ('[O]', '[~]', '[X]') if ascii_safe else ('\u2705', '\u26a0\ufe0f', '\u274c')
    label = {'direction': '方向', 'range': '区间', 'support': '支撑', 'resistance': '压力'}
    lines = ['| 维度 | %s 命中 | %s 部分 | %s 失效 | 纯命中率 | 含部分口径 |' % (sh, sp, sm),
             '|---|---|---|---|---|---|']
    d = stats['dims']
    for k in ['direction', 'range', 'support', 'resistance']:
        if k not in d:
            continue
        c = d[k]
        lines.append('| %s | %d | %d | %d | **%.1f%%**（%d/%d） | %.1f%% |'
                     % (label[k], c['hit'], c['partial'], c['miss'],
                        c['pure'] or 0, c['hit'], c['total'], c['weighted'] or 0))
    lines.append('')
    lines.append('> 统计期数：%d 期（status=verified）' % stats['periods'])
    return '\n'.join(lines)


# ---------------------------------------------------------------- 链状态

def chain_status(name, tail=3):
    recs, _ = load(name)
    verified = sum(1 for r in recs if r.get('status') == 'verified')
    pending = [r.get('id') for r in recs if r.get('status') == 'pending']
    lines = ['=== %s 链状态 ===' % name,
             '总条数: %d' % len(recs),
             'verified: %d | pending: %d' % (verified, len(pending)),
             'pending 明细: %s' % (', '.join(pending) if pending else '无')]
    for r in recs[-tail:]:
        lines.append(' - %s | status=%s' % (r.get('id'), r.get('status')))
    return '\n'.join(lines)


def assert_status(name, expectations):
    """回读断言：expectations = {id: expected_status}

    修复 9/15「脚本 stdout 说写了、链其实没落盘」的根因——写盘后从磁盘重读校验。
    返回 (ok: bool, msgs: list)
    """
    msgs, ok = [], True
    for rid, want in expectations.items():
        got = status_of(name, rid)
        if got == want:
            msgs.append('[回读OK] %s status=%s' % (rid, got))
        else:
            ok = False
            msgs.append('[回读FAIL] %s 期望 status=%s，实际=%s（落盘失败！）' % (rid, want, got))
    return ok, msgs


def count_pending(name):
    recs, _ = load(name)
    return sum(1 for r in recs if r.get('status') == 'pending')


def read_payload(path):
    with io.open(path, encoding='utf-8') as f:
        return json.load(f)


def write_json(path, obj):
    with io.open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    # 自检：py chainlib.py  → 打印两条链状态 + 偏差统计
    for n in ('forecast', 'consensus'):
        print(chain_status(n))
        print()
    print('--- 偏差统计（forecast）---')
    print(render_bias_table(bias_stats('forecast')))
