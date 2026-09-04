# -*- coding: utf-8 -*-
"""append_consensus.py —— consensus_chain.json 通用追加脚本（恢复维护机制）。

背景：consensus_chain.json 在 2026-08-28 ~ 2026-09-04 期间停更（共识/对立观点
只写在各日「作战报告」第二块，未结构化进链）。自 2026-09-04 起恢复维护。

用法：
    python append_consensus.py <record.json>

record.json 是一条完整的 consensus 记录 dict，字段：
    id          如 "2026-09-04-noon"
    report_type 如 "午间快报（手动 12:00）"
    created_at  如 "2026-09-04 12:00"
    window      如 "2026-09-04 08:00 ~ 12:00"
    consensus   [ {topic, view, type, sources?}, ... ]  共识
    opposite    [ {topic, side_a, side_b, judgment_note}, ... ]  对立
    status      "pending"（待复盘）或 "verified"
    review      可选，复盘时再填

幂等：若 id 已存在则跳过，不重复追加。
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHAIN = os.path.join(HERE, 'consensus_chain.json')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    with open(sys.argv[1], encoding='utf-8') as f:
        rec = json.load(f)

    required = ['id', 'report_type', 'created_at', 'window', 'consensus', 'opposite']
    missing = [k for k in required if k not in rec]
    if missing:
        print(f'错误：record.json 缺字段 {missing}')
        sys.exit(1)

    if not os.path.exists(CHAIN):
        chain = []
    else:
        with open(CHAIN, encoding='utf-8') as f:
            chain = json.load(f)

    if any(r.get('id') == rec['id'] for r in chain):
        print(f'已存在 {rec["id"]}，跳过')
        return

    chain.append(rec)
    chain.sort(key=lambda r: r.get('id', ''))

    with open(CHAIN, 'w', encoding='utf-8') as f:
        json.dump(chain, f, ensure_ascii=False, indent=2)

    print(f'已追加 {rec["id"]}，总记录 {len(chain)} 条')


if __name__ == '__main__':
    main()
