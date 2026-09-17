# -*- coding: utf-8 -*-
"""多周期技术位快照：5F / 15F / 30F / 60F / 120F(合成) / 日线的 MA55 / MA20 / MACD。

用途：T&J 常点名具体级别（如「5F55 不能跌破」「30F55 反抽压制」「60F55 上涨目标」
「120F 金叉传导」），而 `calc_tech.py` 只算 日线/m15/m60，覆盖不到。

2026-09-17 从一次性脚本 `_tech_extra.py` 升级而来，改动：
  - **删掉写死的绝对路径** `BASE = r'C:\\Users\\gedayou\\...\\'`
    （家↔公司走 GitHub 同步，写死绝对路径到公司机器直接崩）
  - 输出文件名不再写死 `_tech_extra_2026-09-17.json`，改 `_tech_multi_<日期>.json`
  - 加 argparse，可换标的、可指定输出

用法：
    python calc_tech_multi.py                                  # 000001，默认输出
    python calc_tech_multi.py --code sh000300
    python calc_tech_multi.py --code sh000001 --out /tmp/m.json
    python calc_tech_multi.py --quiet                          # 只写文件不打印
"""
import argparse
import datetime
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from calc_tech import mkline, dkline, report      # noqa: E402

LEVELS = (('5F', 'm5', 800), ('15F', 'm15', 800),
          ('30F', 'm30', 800), ('60F', 'm60', 800))
ORDER = ('5F', '15F', '30F', '60F', '120F(合成)', '日线')


def build(code):
    out = {}
    for label, p, n in LEVELS:
        try:
            rows = mkline(code, p, n)
            out[label] = report(label, rows)
            out[label]['bars'] = len(rows)
        except Exception as e:
            out[label] = {'error': '%s: %s' % (type(e).__name__, e)}

    # 120F：腾讯无 m120 接口，用 60F 每 2 根合成
    try:
        r60 = mkline(code, 'm60', 800)
        syn = []
        for i in range(0, len(r60) - 1, 2):
            a, b = r60[i], r60[i + 1]
            syn.append({'t': b['t'], 'o': a['o'], 'c': b['c'],
                        'h': max(a['h'], b['h']), 'l': min(a['l'], b['l'])})
        out['120F(合成)'] = report('120F(合成)', syn)
        out['120F(合成)']['bars'] = len(syn)
    except Exception as e:
        out['120F(合成)'] = {'error': '%s: %s' % (type(e).__name__, e)}

    try:
        out['日线'] = report('日线', dkline(code, 160))
        out['现价'] = out['日线']['close']
    except Exception as e:
        out['日线'] = {'error': '%s: %s' % (type(e).__name__, e)}
        out['现价'] = None
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='多周期技术位快照（MA55/MA20/MACD）')
    ap.add_argument('--code', default='sh000001', help='标的代码（腾讯格式，默认 sh000001）')
    ap.add_argument('--out', default=None, help='输出 JSON（默认 .workbuddy/_tech_multi_<今日>.json）')
    ap.add_argument('--quiet', action='store_true', help='只写文件，不打印表格')
    a = ap.parse_args(argv)

    out = build(a.code)
    p = a.out or os.path.join(
        BASE, '_tech_multi_%s.json' % datetime.date.today().strftime('%Y-%m-%d'))

    errs = [k for k in ORDER if 'error' in (out.get(k) or {})]
    if len(errs) == len(ORDER):
        raise SystemExit('[FAIL] 全部级别取数失败，未写出文件。首个错误：%s'
                         % (out.get(ORDER[0]) or {}).get('error'))

    with open(p, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    if not a.quiet:
        print('现价 =', out.get('现价'), '  code =', a.code)
        print('')
        for k in ORDER:
            v = out.get(k) or {}
            if 'error' in v:
                print('%-10s ERROR %s' % (k, v['error']))
                continue
            print('%-10s bars=%-4s t=%-14s MA55=%-9s (%+.2f%%) | MA20=%-9s (%+.2f%%) '
                  '| %s | DIF=%s DEA=%s gap=%s DIF%s'
                  % (k, v.get('bars'), v.get('t'), v.get('ma55'), v.get('ma55_pct') or 0,
                     v.get('ma20'), v.get('ma20_pct') or 0, v.get('zone'),
                     v.get('dif'), v.get('dea'), v.get('gap'), v.get('dif_dir')))
    if errs:
        sys.stderr.write('[WARN] 以下级别取数失败：%s\n' % ', '.join(errs))
    print('SAVED=', p)
    return 0


if __name__ == '__main__':
    sys.exit(main())
