# -*- coding: utf-8 -*-
"""P0-3 回归测试：gen_tj_archive 的 0 条守卫 / 缩水守卫 / 原子写 / 通道如实渲染。

用法：$PY .workbuddy/test_gen_tj_archive.py（沙箱 tempfile 内跑，不碰真实 outputs/）
"""
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('gta', os.path.join(HERE, 'gen_tj_archive.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

GID = m.TARGET_GID
SANDBOX = tempfile.mkdtemp(prefix='p03_')
os.makedirs(os.path.join(SANDBOX, 'outputs'), exist_ok=True)
m.ROOT = SANDBOX
m.SRC = os.path.join(SANDBOX, 'zsxq_fetch_raw.json')
# META 也必须指向沙箱，**且要在这里就改**（原来拖到 §8 才改，是个真坑）：
# §1–§7 读的是**真实仓库**的 zsxq_fetch_meta.json，而只要当天有过一次降级抓取
# （例如冒烟 C1 跑出 0 条），降级守卫就会把「正常路径」用例判红 ——
# **测试红得与代码无关**，闸门开始撒谎（2026-09-23 实测：冒烟 A3 阶段早于 C1 是绿的，
# 冒烟结束后单跑就红了，两次跑的是同一份代码）。
# 这里**不创建**该文件 → 走脚本的「旧快照无 meta：向后兼容、不阻断、不标注」分支。
m.META = os.path.join(SANDBOX, 'zsxq_fetch_meta.json')
OUT = os.path.join(SANDBOX, 'outputs', 'DRAGON_BALL_原始记录_%s.md'
                   % __import__('datetime').datetime.now().strftime('%Y-%m-%d'))

fails = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


print('0) 沙箱自检：被测脚本读写的每条路径都必须落在沙箱内')
# 为什么单列成一节、而且是**致命**的：沙箱漏掉一条路径，测试就会读（甚至写）
# 真实仓库状态。症状是「同一份代码，换个时间/换个顺序跑就红」，最容易被当成偶发。
# 本测试会写 m.META（§8–§10 的 write_meta）与 OUT，所以这里**发现漏项必须立刻中止** ——
# 只记一笔失败然后继续跑，等于放任它把测试数据写进真实 meta。
_lost = [n for n in ('SRC', 'META') if SANDBOX not in getattr(m, n)]
if _lost or m.ROOT != SANDBOX:
    sys.stderr.write('[FAIL] 沙箱未覆盖 %s —— 立即中止：本测试会写 META/OUT，'
                     '沙箱没兜住就可能改到真实仓库状态\n'
                     % ('、'.join(_lost) if _lost else 'ROOT'))
    sys.exit(1)
ck(not os.path.exists(m.META), 'META 在沙箱内且不存在 → 走兼容分支，不受真实 meta 影响')


def write_src(items):
    with open(m.SRC, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False)


def topic(tid, ct, text, gid=GID, channel='skill'):
    return {'gid': gid, 'topic_id': tid, 'type': 'talk', 'text': text,
            'create_time': ct, 'images': [], 'files': [], 'channel': channel}


print('1) 0 条守卫：不写文件、不报完成')
write_src([topic(1, '2026-09-18T09:00:00.000+0800', '别的星球的内容', gid='999')])
m.sys.argv = ['gen_tj_archive.py']
rc = m.main()
ck(rc == 2, '筛出 0 条时返回 2（旧实现返回 None→退出 0 且打印「归档完成，0 条」）')
ck(not os.path.exists(OUT), '未创建 0 条空壳文件（否则 check_integrity 归档缺口检测会假绿）')

print('2) 正常路径：写入 + 回读断言')
write_src([topic(11, '2026-09-18T09:10:00.000+0800', '第一条正文'),
           topic(12, '2026-09-18T09:20:00.000+0800', '第二条正文')])
rc = m.main()
ck(rc == 0, '有内容时返回 0')
body = open(OUT, encoding='utf-8').read()
ck(m._entry_count(body) == 2, '落盘条目数 = 2（回读断言通过）')
ck('第一条正文' in body and '第二条正文' in body, '原文已一字不差写入')
ck('抓取通道：zsxq-cli Skill 通道' in body, '通道按实际 channel 渲染')
ck(not os.path.exists(OUT + '.tmp'), '无遗留 .tmp 文件')

print('3) 缩水守卫：残缺抓取不得冲掉完整归档')
write_src([topic(11, '2026-09-18T09:10:00.000+0800', '第一条正文')])
rc = m.main()
ck(rc == 2, '条数从 2 缩到 1 时返回 2')
ck(m._entry_count(open(OUT, encoding='utf-8').read()) == 2, '原 2 条归档未被覆盖')

print('4) --force 可显式覆盖')
m.sys.argv = ['gen_tj_archive.py', '--force']
rc = m.main()
ck(rc == 0, '--force 时返回 0')
ck(m._entry_count(open(OUT, encoding='utf-8').read()) == 1, '--force 后已按本轮覆盖')

print('5) 等量重跑不算缩水（幂等，不报噪声）')
rc = m.main()
ck(rc == 0, '条数相同再次重跑返回 0（不产生永久告警噪声）')

print('6) 旧快照无 channel 字段时如实说明，不谎报通道')
write_src([{'gid': GID, 'topic_id': 21, 'type': 'talk', 'text': '旧格式',
            'create_time': '2026-09-18T10:00:00.000+0800', 'images': [], 'files': []}])
m.sys.argv = ['gen_tj_archive.py', '--force']
rc = m.main()
ck(rc == 0 and '未记录' in open(OUT, encoding='utf-8').read(),
   '旧快照渲染为「未记录」而非写死的 Skill 通道')

print('7) 快照缺失 → 退出码 1')
os.remove(m.SRC)
m.sys.argv = ['gen_tj_archive.py']
ck(m.main() == 1, '快照不存在时返回 1')

print('8) 降级守卫：主快照不是本轮结果时拒绝归档（--force 也不放行）')
write_src([topic(11, '2026-09-18T09:10:00.000+0800', '第一条正文'),
           topic(12, '2026-09-18T09:20:00.000+0800', '第二条正文')])


def write_meta(snapshot, total, window='晨报 morning 窗口', degraded=None):
    with open(m.META, 'w', encoding='utf-8') as f:
        json.dump({'snapshot': snapshot, 'total': total, 'window': window,
                   'degraded': degraded or []}, f, ensure_ascii=False)


write_meta('zsxq_fetch_raw_degraded_20260918_131700.json', 2,
           degraded=['Cookie 鉴权失败 1 个星球（48841181481248）'])
before = open(OUT, encoding='utf-8').read()
m.sys.argv = ['gen_tj_archive.py', '--force']
rc = m.main()
ck(rc == 2, '主快照非本轮结果时返回 2')
ck(open(OUT, encoding='utf-8').read() == before, '归档未被改动（未把上一轮内容写成今天）')

print('9) meta 与快照一致时按实际档位标注窗口')
write_meta('zsxq_fetch_raw.json', 2)
m.sys.argv = ['gen_tj_archive.py']
rc = m.main()
body = open(OUT, encoding='utf-8').read()
ck(rc == 0, 'meta 一致时正常归档返回 0')
ck('（晨报 morning 窗口）' in body, '窗口档位按 meta 实际值标注（不再是瞎猜/写死）')

print('10) meta 条数与快照不符时不标注（不阻断，如实降级为不标注）')
write_meta('zsxq_fetch_raw.json', 99)
rc = m.main()
ck(rc == 0 and '（晨报 morning 窗口）' not in open(OUT, encoding='utf-8').read(),
   'meta 过期时归档不标注档位，但仍能正常产出')

print()
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
sys.exit(1 if fails else 0)
