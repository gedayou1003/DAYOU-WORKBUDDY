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

HERE = os.path.dirname(os.path.abspath(__file__))

# 允许用环境变量重定向链目录（供自测/沙箱验证用，正常运行不设即可）
CHAIN_DIR = os.environ.get('CHAIN_DIR') or HERE

FORECAST = os.path.join(CHAIN_DIR, 'forecast_chain.json')
CONSENSUS = os.path.join(CHAIN_DIR, 'consensus_chain.json')

CHAINS = {'forecast': FORECAST, 'consensus': CONSENSUS}


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

def apply_review(recs, rid, review, verified_at=None):
    """给某条记录写 review 并转 verified。幂等：已有 review 则跳过。

    返回 (changed: bool, msg: str)
    """
    r = find(recs, rid)
    if r is None:
        return False, f'[跳过] 未找到 {rid}'
    if r.get('review'):
        return False, f'[跳过] {rid} 已有 review（幂等，不覆盖）'
    r['review'] = review
    r['status'] = 'verified'
    if verified_at:
        r['verified_at'] = verified_at
    elif isinstance(review, dict) and review.get('reviewed_at'):
        r['verified_at'] = review['reviewed_at']
    return True, f'[复盘] {rid} 已写 review，status -> verified'


def upsert_pending(recs, record):
    """追加一条 pending 记录。幂等：id 已存在则跳过。

    返回 (changed: bool, msg: str)
    """
    rid = record.get('id')
    if not rid:
        return False, '[跳过] record 缺 id 字段'
    if find(recs, rid) is not None:
        return False, f'[跳过] {rid} 已存在（幂等）'
    record.setdefault('status', 'pending')
    recs.append(record)
    return True, f'[追加] {rid} 已写入，status={record["status"]}'


# ---------------------------------------------------------------- 偏差统计

def bias_stats(name='forecast', dims=None):
    """程序化计算四维偏差统计（纯口径 + 含部分口径）。

    四维字段两代格式兼容：早期 review.{dim}，后期 review.{dim}_verdict。
    取值前缀 ✅ / ⚠️ / ❌。纯命中率 = ✅ ÷ (✅+⚠️+❌)，仅统计 status=='verified'。
    返回 {'periods': n, dims: {dim: {hit, partial, miss, pure, weighted}}}
    """
    if dims is None:
        dims = ['direction', 'range', 'support', 'resistance']
    recs, _ = load(name)
    verified = [r for r in recs if r.get('status') == 'verified']
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


def render_bias_table(stats):
    """渲染偏差统计 Markdown 表（供报告直接粘贴）"""
    label = {'direction': '方向', 'range': '区间', 'support': '支撑', 'resistance': '压力'}
    lines = ['| 维度 | ✅ 命中 | ⚠️ 部分 | ❌ 失效 | 纯命中率 | 含部分口径 |',
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
            msgs.append('[回读✓] %s status=%s' % (rid, got))
        else:
            ok = False
            msgs.append('[回读✗] %s 期望 status=%s，实际=%s（落盘失败！）' % (rid, want, got))
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
