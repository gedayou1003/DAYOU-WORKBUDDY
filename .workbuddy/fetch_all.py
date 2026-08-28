# -*- coding: utf-8 -*-
"""手动串联 skill+cookie 双通道抓取（规避 main 的整体超时），合并写入 zsxq_fetch_raw.json。
用法：python fetch_all.py [--window noon]
"""
import sys, os, json, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_zsxq as f

results = []
for gid, name in f.SKILL_GROUPS.items():
    try:
        topics = f.fetch_skill(gid)
        for t in topics:
            n = f.norm_topic(t, name)
            if f.in_window(n['create_time']):
                results.append(n)
        print(f'[skill] {name}: {len(topics)}条', flush=True)
    except Exception as e:
        print(f'[skill-err] {name}: {e}', flush=True)
    time.sleep(2)

for gid, name in f.COOKIE_GROUPS.items():
    try:
        topics = f.fetch_cookie(gid)
        for t in topics:
            n = f.norm_topic(t, name)
            if f.in_window(n['create_time']):
                results.append(n)
        print(f'[cookie] {name}: {len(topics)}条', flush=True)
    except Exception as e:
        print(f'[cookie-err] {name}: {e}', flush=True)
    time.sleep(2)

results.sort(key=lambda x: x['create_time'])
seen, uniq = set(), []
for x in results:
    if x['topic_id'] not in seen:
        seen.add(x['topic_id'])
        uniq.append(x)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'zsxq_fetch_raw.json')
with open(out, 'w', encoding='utf-8') as fp:
    json.dump(uniq, fp, ensure_ascii=False, indent=1)
print(f'TOTAL={len(uniq)} SAVED={out}', flush=True)
