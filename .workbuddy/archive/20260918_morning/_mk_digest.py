import json, os, re, sys, datetime

ROOT = r'C:\Users\gedayou\WorkBuddy\2026-08-14-09-01-12'
src = os.path.join(ROOT, '.workbuddy', 'zsxq_fetch_raw.json')
d = json.load(open(src, encoding='utf-8'))

def clean(t):
    t = t or ''
    t = re.sub(r'<e type="hashtag"[^>]*title="([^"]*)"[^>]*/>', lambda m: '#' + m.group(1).replace('%23','') , t)
    t = re.sub(r'<e[^>]*/>', '', t)
    t = re.sub(r'<[^>]+>', '', t)
    import urllib.parse
    try:
        t = urllib.parse.unquote(t)
    except Exception:
        pass
    return t.strip()

rows = []
for e in d:
    rows.append({
        'group': e.get('group'),
        'time': e.get('create_time',''),
        'type': e.get('type'),
        'text': clean(e.get('text')),
        'nimg': len(e.get('images') or []),
        'nfile': len(e.get('files') or []),
        'files': [ (f.get('name') if isinstance(f, dict) else str(f)) for f in (e.get('files') or []) ],
    })

rows.sort(key=lambda r: r['time'])
print('TOTAL', len(rows))
print('TIME MIN', rows[0]['time'] if rows else '-')
print('TIME MAX', rows[-1]['time'] if rows else '-')
from collections import Counter
c = Counter(r['group'] for r in rows)
print('BY GROUP:')
for k, v in c.most_common():
    print('   ', k, v)
print('IMG_TOTAL', sum(r['nimg'] for r in rows), 'FILE_TOTAL', sum(r['nfile'] for r in rows))

out = os.path.join(ROOT, '.workbuddy', '_zsxq_digest_2026-09-18.txt')
with open(out, 'w', encoding='utf-8') as f:
    cur = None
    for r in rows:
        if r['group'] != cur:
            cur = r['group']
            f.write('\n' + '='*70 + '\n[星球] ' + str(cur) + '\n' + '='*70 + '\n')
        f.write('\n---- %s | %s | IMG %d | FILE %d ----\n' % (r['time'], r['type'], r['nimg'], r['nfile']))
        if r['files']:
            f.write('附件: ' + '; '.join([str(x) for x in r['files']]) + '\n')
        f.write(r['text'] + '\n')
print('SAVED', out)
