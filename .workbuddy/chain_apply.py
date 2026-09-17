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
import os, sys, json, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chainlib as CL


def _apply_section(chain_name, section, dry_run=False):
    """处理一条链的 review + record，返回 (changed, msgs, expects, errors)"""
    msgs, expects, errors = [], {}, {}
    if not section:
        return False, msgs, expects, errors

    recs, is_dict = CL.load(chain_name)
    changed = False

    # 1) 校验上一条
    vp = section.get('validate_prev')
    if vp:
        st = CL.status_of(chain_name, vp)
        # 本次 payload 是否就要复盘这一条？是的话 pending 属预期内，
        # 不应再报「可能上一档脚本未落盘」（2026-09-17 修正：原先会误报，噪音淹没真告警）
        reviewing_now = ((section.get('review') or {}).get('id') == vp)
        if st is None:
            msgs.append(f'[警告] 未找到 {vp}')
        elif st == 'verified':
            rv = (CL.find(recs, vp) or {}).get('review') or {}
            if ('per_topic' in rv) or ('opposite_review' in rv):
                # 共识链 review 没有四维字段，按共识 schema 回显（否则会打出误导性的 4 个 ?）
                pt = rv.get('per_topic') or []
                hits = sum(1 for it in pt if isinstance(it, dict)
                           and str(it.get('verdict', '')).startswith('\u2705'))
                msgs.append('[校验通过] %s 已 verified；共识复盘 %d 条（\u2705 %d 条）、对立观点复盘：%s' % (
                    vp, len(pt), hits, (rv.get('opposite_review') or {}).get('verdict', '?')))
            else:
                msgs.append('[校验通过] %s 已 verified；四维：%s / %s / %s / %s' % (
                    vp, rv.get('direction_verdict') or rv.get('direction', '?'),
                    rv.get('range_verdict') or rv.get('range', '?'),
                    rv.get('support_verdict') or rv.get('support', '?'),
                    rv.get('resistance_verdict') or rv.get('resistance', '?')))
        elif reviewing_now:
            msgs.append(f'[待复盘] {vp} 仍为 {st}——本次 payload 已包含其 review，将在本步骤内转 verified')
        else:
            msgs.append(f'[警告] {vp} 仍为 {st}，需先复盘（可能上一档脚本未落盘）')

    # 2) 复盘上一条
    rv = section.get('review')
    if rv:
        rid = rv.get('id')
        c, m = CL.apply_review(recs, rid, rv.get('review'), rv.get('verified_at'))
        changed |= c
        msgs.append(m)
        if m.startswith(CL.REJECT_PREFIX):
            errors[rid] = m
        elif c:
            expects[rid] = 'verified'

    # 3) 追加本期
    rec = section.get('record')
    if rec:
        c, m = CL.upsert_pending(recs, rec)
        changed |= c
        msgs.append(m)
        if m.startswith(CL.REJECT_PREFIX):
            errors[rec.get('id') or '<record 缺 id>'] = m
        elif c:
            expects[rec['id']] = 'pending'

    if changed and not dry_run:
        CL.save(chain_name, recs, is_dict)
    return changed, msgs, expects, errors


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
        # 预填「上一条」id：取该链最后一条。原先留 'YYYY-MM-DD-<tier>' 字面量，
        # 与已填好的 record.id 不一致，极易忘改（2026-09-16 巡检修复）。
        prev_ids = {}
        for n in ('forecast', 'consensus'):
            try:
                recs, _ = CL.load(n)
                prev_ids[n] = recs[-1].get('id') if recs else ''
            except Exception:
                prev_ids[n] = ''
        S = CL.PLACEHOLDER_MARK + ' 必填'
        tpl = {
            'forecast': {
                'validate_prev': prev_ids['forecast'],
                'review': {'id': prev_ids['forecast'],
                           'review': {'reviewed_at': f'{date} HH:MM（复盘）',
                                      'actual': {'date': '', 'open': 0, 'high': 0, 'low': 0,
                                                 'close': 0, 'pct_chg': 0, 'prev_close': 0, 'note': ''},
                                      'direction_verdict': f'{S}：✅/⚠️/❌ + 说明',
                                      'range_verdict': f'{S}：✅/⚠️/❌ + 说明',
                                      'support_verdict': f'{S}：✅/⚠️/❌ + 说明',
                                      'resistance_verdict': f'{S}：✅/⚠️/❌ + 说明',
                                      'bias_type': [], 'foreseeable': '', 'foresee_reason': '', 'note': ''}},
                'record': {'id': f'{date}-{tier}', 'report_type': '', 'created_at': f'{date} HH:MM',
                           'target': '', 'code': '000001',
                           'direction': f'{S}：偏多/偏空/震荡',
                           'range': f'{S}：下沿~上沿',
                           'support': {'primary': 0, 'primary_basis': ''},
                           'support_basis': '', 'resistance': {'primary': 0, 'primary_basis': ''},
                           'resistance_basis': '', 'confidence': f'{S}：高/中/低',
                           'evidence': {}, 'summary': '', 'scenario': {}, 'macd_factor': '',
                           'reversal_discipline': '', 'levels': {}, 'status': 'pending'}
            },
            'consensus': {
                'validate_prev': prev_ids['consensus'],
                'review': {'id': prev_ids['consensus'],
                           'review': {'review_time': '', 'items': []}},
                'record': {'id': f'{date}-{tier}', 'report_type': '', 'created_at': f'{date} HH:MM',
                           'window': '', 'consensus': [], 'opposing': []}
            },
            'bias': {'print': True}
        }
        p = os.path.join(CL.HERE, f'payload_{date}_{tier}.json')
        CL.write_json(p, tpl)
        print('模板已生成:', p)
        print(f'  已预填 validate_prev / review.id = {prev_ids["forecast"]}（forecast 链最后一条）')
        print(f'  所有「{S}」标记处必须替换为实填内容。')
        print(f'  残留占位符或四维判定全空 → 会被空壳校验拒绝并以退出码 2 结束（不会污染链）。')
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
        print(f'{CL.sym("bad")} payload 不存在: {args.payload}')
        return 1

    payload = CL.read_payload(args.payload)
    all_expects = {}
    all_errors = {}
    any_changed = False

    for chain_name in ('forecast', 'consensus'):
        section = payload.get(chain_name)
        if not section:
            continue
        print(f'--- {chain_name} ---')
        changed, msgs, expects, errors = _apply_section(chain_name, section, args.dry_run)
        for m in msgs:
            print(' ', m)
        all_expects[chain_name] = expects
        all_errors.update(errors)
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
                line += '  %s pending > 1，检查是否漏复盘上一条' % CL.sym('warn')
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
            # 相对路径统一按 .workbuddy/ 解析（payload 里惯写 ".workbuddy/_bias_xxx.json"
            # 或 "_bias_xxx.json" 两种形态）。2026-09-17 修复：原先直接按 cwd 解析，
            # 从 .workbuddy 内执行时会变成 .workbuddy/.workbuddy/... 而 FileNotFound 崩掉；
            # 且崩溃发生在链已成功落盘之后，导致退出码 1 误导为「链没写成功」。
            try:
                wp2 = wp
                if not os.path.isabs(wp2):
                    norm = wp2.replace('\\', '/')
                    if norm.startswith('.workbuddy/'):
                        norm = norm[len('.workbuddy/'):]
                    wp2 = os.path.join(CL.HERE, norm)
                d = os.path.dirname(wp2)
                if d:
                    os.makedirs(d, exist_ok=True)
                CL.write_json(wp2, st)
                print('\n已写出:', wp2)
            except Exception as e:
                # 附属统计文件写失败不应污染「链是否落盘」的判定，降级为警告
                print('\n%s 偏差统计文件写出失败（不影响链落盘）：%r' % (CL.sym('warn'), e))

    if all_errors or not ok_all:
        print()
        if all_errors:
            print('%s 有 %d 条 review 被拒（空壳/校验未过），本次未完整落盘，请填完再跑。'
                  % (CL.sym('bad'), len(all_errors)))
        if not ok_all:
            print('%s 回读断言失败：有记录未按预期落盘，请检查！' % CL.sym('bad'))
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
