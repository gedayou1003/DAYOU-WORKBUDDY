# -*- coding: utf-8 -*-
"""星球抓取结果摘要：按星球分组 + 时间排序 + 全文（供报告第一块取材）。

2026-09-16 维护（I-6）：合并 digest_0916.py（新版）与 digest_zsxq.py（旧版），
两者 4 个函数（norm/txt/gname/ttime）完全同构。改进：
  - 输出文件名不再写死日期，改为 --out 或默认 _zsxq_digest_<今日>.txt
  - 键名兼容探测保留（group/gid/topic_id/type/text/create_time/images/files）

用法：
    python digest_zsxq.py [--src .workbuddy/zsxq_fetch_raw.json] [--out ...] [--limit 3000]
"""
import json, os, re, sys, argparse, datetime

BASE = os.path.dirname(os.path.abspath(__file__))


def norm(raw):
    if isinstance(raw, list):
        return raw
    for k in ('topics', 'data', 'items', 'records', 'result'):
        if isinstance(raw.get(k), list):
            return raw[k]
    out = []
    for k, v in raw.items():
        if isinstance(v, list):
            for t in v:
                if isinstance(t, dict):
                    t.setdefault('_group', k)
                    out.append(t)
    return out


def txt(t):
    for k in ('text', 'content', 'body', 'talk_text'):
        v = t.get(k)
        if v:
            return str(v)
    return ''


def gname(t):
    for k in ('group_name', '_group', 'group', 'groupName'):
        v = t.get(k)
        if v:
            return str(v)
    return '?'


def ttime(t):
    for k in ('create_time', 'created_at', 'time', 'createTime'):
        v = t.get(k)
        if v:
            return str(v)
    return '?'


def atts(t):
    imgs = t.get('images') or []
    fls = t.get('files') or []
    s = []
    if imgs:
        s.append('IMG%d' % len(imgs))
    if fls:
        s.append('FILE%d' % len(fls))
    return (' ' + ' '.join(s)) if s else ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=os.path.join(BASE, 'zsxq_fetch_raw.json'))
    ap.add_argument('--out', default=None)
    ap.add_argument('--limit', type=int, default=3000, help='单条正文截断字数')
    args = ap.parse_args()

    if not os.path.exists(args.src):
        print(f'❌ 原始数据不存在: {args.src}（先跑 fetch_zsxq.py）')
        return 1
    with open(args.src, encoding='utf-8') as f:
        topics = norm(json.load(f))

    L = ['总条数: %d' % len(topics)]
    if topics:
        L.append('样例键: ' + ', '.join(list(topics[0].keys())[:25]))
    L.append('')

    groups = {}
    for t in topics:
        groups.setdefault(gname(t), []).append(t)

    for g in sorted(groups, key=lambda k: -len(groups[k])):
        ts = sorted(groups[g], key=lambda t: ttime(t))
        L.append('=' * 70)
        L.append('### 星球: %s （%d 条）' % (g, len(ts)))
        L.append('=' * 70)
        for i, t in enumerate(ts, 1):
            body = re.sub(r'[ \t]+', ' ', txt(t)).strip()
            L.append('')
            L.append('--- [%s#%d] %s%s ---' % (g, i, ttime(t), atts(t)))
            L.append(body if len(body) <= args.limit else body[:args.limit] + ' ……[截断]')

    p = args.out or os.path.join(
        BASE, '_zsxq_digest_%s.txt' % datetime.datetime.now().strftime('%Y-%m-%d'))
    with open(p, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))
    print('OK %d 条 -> %s' % (len(topics), p))
    return 0


if __name__ == '__main__':
    sys.exit(main())
