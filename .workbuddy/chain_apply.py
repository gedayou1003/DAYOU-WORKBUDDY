# -*- coding: utf-8 -*-
"""链操作统一入口（2026-09-16 维护新增 I-6）

一处替代原先 42 个「每日新建脚本族」+ 3 个复盘脚本：
    add_morning_YYYY-MM-DD.py            × 9
    review_consensus_morning_YYYY-MM-DD.py × 7
    add_noon_YYYY-MM-DD.py               × 5
    review_close_YYYY-MM-DD.py           × 5
    add_close_YYYY-MM-DD.py              × 3
    review_consensus_close_YYYY-MM-DD.py × 3
    add_evening / add_intraday / calc_tech / digest / bias_stats / review_morning ...
    ────────────────────────────────────────────────────────────
    →  chain_apply.py --payload <payload.json>

用法
----
    python chain_apply.py --payload payload.json [--dry-run] [--bias-only]
    python chain_apply.py --init-template morning 2026-09-17    # 生成空白 payload 骨架

payload.json 结构（各段均可选）
-------------------------------
{
  "forecast": {
    "validate_prev": "2026-09-16-morning",          # 可选：校验上一条是否已 verified
    "review": {"id": "2026-09-16-morning",           # 可选：复盘上一条
               "review": { ...四维判定 dict... }},
    "record": { "id": "2026-09-17-morning", ... }    # 可选：追加本期（status 自动置 pending）
  },
  "consensus": { 同上结构 },
  "bias": {"print": true, "write": ".workbuddy/_bias_2026-09-17.json"}
}

设计要点
--------
1. **幂等**：review 已存在 / record.id 已存在 → 跳过，绝不重复写
2. **机器回读断言（修复 9/15 漏落盘事故根因）**：写盘后从磁盘重新读回，逐条校验 status，
   任一不符即非零退出 —— 不再依赖「跑完记得回读」的人工纪律
3. **pending 数守卫**：写完若 pending > 1 条，提示可能是漏复盘
4. `--dry-run` 全流程预演，不落盘
"""
import os, sys, json, argparse, io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chainlib as CL


def _apply_section(chain_name, section, dry_run=False):
    """处理一条链的 review + record，返回 (changed, msgs, expects)"""
    msgs, expects = [], {}
    if not section:
        return False, msgs, expects

    recs, is_dict = CL.load(chain_name)
    changed = False

    # 1) 校验上一条
    vp = section.get('validate_prev')
    if vp:
        st = CL.status_of(chain_name, vp)
        if st is None:
            msgs.append(f'[警告] 未找到 {vp}')
        elif st == 'verified':
            rv = (CL.find(recs, vp) or {}).get('review') or {}
            msgs.append('[校验通过] %s 已 verified；四维：%s / %s / %s / %s' % (
                vp, rv.get('direction_verdict') or rv.get('direction', '?'),
                rv.get('range_verdict') or rv.get('range', '?'),
                rv.get('support_verdict') or rv.get('support', '?'),
                rv.get('resistance_verdict') or rv.get('resistance', '?')))
        else:
            msgs.append(f'[警告] {vp} 仍为 {st}，需先复盘（可能上一档脚本未落盘）')

    # 2) 复盘上一条
    rv = section.get('review')
    if rv:
        rid = rv.get('id')
        c, m = CL.apply_review(recs, rid, rv.get('review'), rv.get('verified_at'))
        changed |= c
        msgs.append(m)
        if c:
            expects[rid] = 'verified'

    # 3) 追加本期
    rec = section.get('record')
    if rec:
        c, m = CL.upsert_pending(recs, rec)
        changed |= c
        msgs.append(m)
        if c:
            expects[rec['id']] = 'pending'

    if changed and not dry_run:
        CL.save(chain_name, recs, is_dict)
    return changed, msgs, expects


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--payload')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--bias-only', action='store_true')
    ap.add_argument('--init-template', nargs=2, metavar=('TIER', 'DATE'),
                    help='生成空白 payload 骨架并打印路径')
    args = ap.parse_args()

    # ---- 模板生成
    if args.init_template:
        tier, date = args.init_template
        tpl = {
            'forecast': {
                'validate_prev': 'YYYY-MM-DD-<tier>',
                'review': {'id': 'YYYY-MM-DD-<tier>',
                           'review': {'reviewed_at': f'{date} HH:MM（复盘）',
                                      'actual': {'date': '', 'open': 0, 'high': 0, 'low': 0,
                                                 'close': 0, 'pct_chg': 0, 'prev_close': 0, 'note': ''},
                                      'direction_verdict': '', 'range_verdict': '',
                                      'support_verdict': '', 'resistance_verdict': '',
                                      'bias_type': [], 'foreseeable': '', 'foresee_reason': '', 'note': ''}},
                'record': {'id': f'{date}-{tier}', 'report_type': '', 'created_at': f'{date} HH:MM',
                           'target': '', 'code': '000001', 'direction': '', 'range': '',
                           'support': {'primary': 0, 'primary_basis': ''},
                           'support_basis': '', 'resistance': {'primary': 0, 'primary_basis': ''},
                           'resistance_basis': '', 'confidence': '', 'evidence': {},
                           'summary': '', 'scenario': {}, 'macd_factor': '',
                           'reversal_discipline': '', 'levels': {}, 'status': 'pending'}
            },
            'consensus': {
                'validate_prev': 'YYYY-MM-DD-<tier>',
                'review': {'id': 'YYYY-MM-DD-<tier>', 'review': {'review_time': '', 'items': []}},
                'record': {'id': f'{date}-{tier}', 'report_type': '', 'created_at': f'{date} HH:MM',
                           'window': '', 'consensus': [], 'opposing': []}
            },
            'bias': {'print': True}
        }
        p = os.path.join(CL.HERE, f'payload_{date}_{tier}.json')
        CL.write_json(p, tpl)
        print('模板已生成:', p)
        print('填好后执行: python .workbuddy/chain_apply.py --payload', p)
        return 0

    # ---- 纯偏差统计
    if args.bias_only:
        st = CL.bias_stats('forecast')
        print(CL.render_bias_table(st))
        for n in ('forecast', 'consensus'):
            print()
            print(CL.chain_status(n))
        return 0

    if not args.payload:
        ap.print_help()
        return 1
    if not os.path.exists(args.payload):
        print(f'❌ payload 不存在: {args.payload}')
        return 1

    payload = CL.read_payload(args.payload)
    all_expects = {}
    any_changed = False

    for chain_name in ('forecast', 'consensus'):
        section = payload.get(chain_name)
        if not section:
            continue
        print(f'--- {chain_name} ---')
        changed, msgs, expects = _apply_section(chain_name, section, args.dry_run)
        for m in msgs:
            print(' ', m)
        all_expects[chain_name] = expects
        any_changed |= changed
        print()

    if args.dry_run:
        print('[dry-run] 未落盘。以上为预演结果。')

    # ---- 回读断言（机器强制，替代人工回读纪律）
    print('===== 回读断言 =====')
    ok_all = True
    if args.dry_run:
        print('  （dry-run 跳过）')
    else:
        for chain_name, expects in all_expects.items():
            if not expects:
                continue
            ok, msgs = CL.assert_status(chain_name, expects)
            ok_all &= ok
            for m in msgs:
                print(' ', m)

    # ---- pending 守卫
    print()
    for n in ('forecast', 'consensus'):
        if n in all_expects:
            pc = CL.count_pending(n)
            line = f'  {n}: pending={pc}'
            if pc > 1:
                line += '  ⚠️ pending > 1，检查是否漏复盘上一条'
            print(line)

    # ---- 链状态
    for n in ('forecast', 'consensus'):
        if n in all_expects:
            print()
            print(CL.chain_status(n))

    # ---- 偏差统计
    if (payload.get('bias') or {}).get('print'):
        print()
        print('--- 偏差统计（forecast）---')
        st = CL.bias_stats('forecast')
        print(CL.render_bias_table(st))
        wp = (payload.get('bias') or {}).get('write')
        if wp and not args.dry_run:
            CL.write_json(wp, st)
            print('\n已写出:', wp)

    if not ok_all:
        print('\n❌ 回读断言失败：有记录未按预期落盘，请检查！')
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
