# -*- coding: utf-8 -*-
"""P0-2 回归测试：save_snapshot 的三种路径（正常 / 正常覆盖留备份 / 降级不碰主快照）。

用法：$PY .workbuddy/test_fetch_snapshot.py（沙箱 tempfile 内跑，不碰真实快照与项目文件）
"""
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, 'fetch_zsxq.py')

spec = importlib.util.spec_from_file_location('fz', TARGET)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

d = tempfile.mkdtemp(prefix='p02_')
m._HERE = d
m.MAIN_SNAPSHOT = os.path.join(d, 'zsxq_fetch_raw.json')
m.PREV_SNAPSHOT = os.path.join(d, 'zsxq_fetch_raw.prev.json')
m.META_FILE = os.path.join(d, 'zsxq_fetch_meta.json')

fails = []


def ck(cond, msg):
    if cond:
        print('  [OK]   %s' % msg)
    else:
        print('  [FAIL] %s' % msg)
        fails.append(msg)


print('1) 正常路径：写主快照')
p, is_main = m.save_snapshot([{'a': 1}], [])
ck(is_main and p == m.MAIN_SNAPSHOT, '正常时返回主快照路径且 is_main=True')
ck(json.load(open(m.MAIN_SNAPSHOT, encoding='utf-8')) == [{'a': 1}], '主快照内容正确')

print('2) 正常路径再写一次：旧内容应滚进 .prev 备份')
p, is_main = m.save_snapshot([{'a': 2}, {'b': 3}], [])
ck(json.load(open(m.PREV_SNAPSHOT, encoding='utf-8')) == [{'a': 1}],
   '覆盖前旧快照已备份到 .prev（覆盖可回溯）')
ck(len(json.load(open(m.MAIN_SNAPSHOT, encoding='utf-8'))) == 2, '主快照已更新为 2 条')

print('3) 降级路径（鉴权失败）：不得碰主快照')
before = open(m.MAIN_SNAPSHOT, encoding='utf-8').read()
p, is_main = m.save_snapshot([], ['Cookie 鉴权失败 2 个星球（48841181481248, 28888222154481）'])
ck(not is_main, '降级时 is_main=False')
ck(open(m.MAIN_SNAPSHOT, encoding='utf-8').read() == before,
   '主快照字节级未被改动（旧实现会在此被清空覆盖）')
ck(os.path.basename(p).startswith('zsxq_fetch_raw_degraded_'), '降级结果落在带时间戳的旁路文件')
ck(json.load(open(p, encoding='utf-8')) == [], '旁路文件内容为本轮真实结果（0 条）')

print('4) 原子写入不留 .tmp 残渣')
ck(not [f for f in os.listdir(d) if f.endswith('.tmp')], '无遗留 .tmp 文件')

print('4b) meta 记录本轮实际写到哪个文件（供下游分辨快照新旧）')
meta = json.load(open(m.META_FILE, encoding='utf-8'))
ck(meta['snapshot'].startswith('zsxq_fetch_raw_degraded_') and meta['updated_main'] is False,
   '降级轮 meta 指向旁路文件且 updated_main=False')
ck(meta['total'] == 0 and meta['degraded'], 'meta 记录了条数与降级原因')
ck('window' in meta and meta['win_start'] and meta['win_end'], 'meta 记录了窗口档位与起止时间')

print('5) 回读断言：写入异常时不得留下半截文件')
bad = os.path.join(d, 'bad.json')


class Boom(list):
    def __len__(self):
        return 99          # 谎报长度，触发回读断言


try:
    m._atomic_write_json(bad, Boom([1]))
    ck(False, '回读断言应抛 RuntimeError')
except RuntimeError:
    ck(not os.path.exists(bad) and not os.path.exists(bad + '.tmp'),
       '回读断言失败时已清理临时文件、未产出坏文件')

print('6) main() 端到端退出码（monkeypatch 抓取函数，不触网）')
m.SKILL_GROUPS = {}
m.COOKIE_GROUPS = {'48841181481248': 'fake'}

# 6a) 鉴权失败 → 退出码 1（ERROR），且不覆盖主快照
# 注意：**不能「先塞 m.auth_failed 再调 main()」** —— main() 现在开头会清计数器
# （2026-09-23：防同进程内重复调用 main() 时跨轮串味，旧版只清了 _BAD_CT）。
# 所以必须让 stub 在**运行期**记账，这也正是真实路径（fetch_cookie 命中 401/403）。
m.auth_failed = set()
m.flaky_failed = set()


def _auth_fail(gid, count=20):
    m.auth_failed.add(gid)
    return []


m.fetch_cookie = _auth_fail
before = open(m.MAIN_SNAPSHOT, encoding='utf-8').read()
rc = m.main()
ck(rc == 1, '鉴权失败时 main() 返回 1（旧实现返回 None→退出 0）')
ck(open(m.MAIN_SNAPSHOT, encoding='utf-8').read() == before, '鉴权失败时主快照未被覆盖')

# 6b) 鉴权正常但窗口内 0 条 → 退出码 2（WARN），仍不覆盖主快照
m.auth_failed = set()
m.fetch_cookie = lambda gid, count=20: []
rc = m.main()
ck(rc == 2, '窗口内 0 条时 main() 返回 2（WARN）')
ck(open(m.MAIN_SNAPSHOT, encoding='utf-8').read() == before, '0 条时主快照未被覆盖')

# 6c) 正常有数据 → 退出码 0，且主快照被更新
m.fetch_cookie = lambda gid, count=20: [{
    'topic_id': 1, 'type': 'talk', 'create_time': '2099-01-01T12:00:00.000+0800',
    'text': 'hello', 'group': {'group_id': gid}, 'talk': {'text': 'hello'},
}]
import datetime as _dt
_future = _dt.datetime(2099, 1, 1, 12, 0, tzinfo=m.CST)
m.WIN_START, m.WIN_END = _future - _dt.timedelta(hours=1), _future + _dt.timedelta(hours=1)
rc = m.main()
ck(rc == 0, '正常抓到数据时 main() 返回 0')
ck(json.load(open(m.MAIN_SNAPSHOT, encoding='utf-8')) != [], '正常路径已更新主快照')

print('7) 窗口时间解析失败不许静默丢弃（2026-09-23 加固）')
# 改前：in_window 解析不了直接返回 False，**零痕迹** —— 报告里「少了几条」与
# 「本来就没有」在输出上无法区分。现在记名、stderr 出声、并落进 meta。
del m._BAD_CT[:]
_fut = _dt.datetime(2099, 1, 1, 12, 0, tzinfo=m.CST)
m.WIN_START, m.WIN_END = _fut - _dt.timedelta(hours=1), _fut + _dt.timedelta(hours=1)
ck(m.in_window('2099-01-01T12:30:00+08:00') is True, '窗口内时间 → True（判定口径未变）')
ck(m.in_window('not-a-time') is False, '解析不了 → False（判定口径未变）')
ck(m._BAD_CT == ['not-a-time'], '解析失败被记名（旧实现零痕迹）')
ck(m.in_window('') is False and len(m._BAD_CT) == 2, '空串同样记名')

# 端到端：坏 create_time 的条数要真的落进 meta，且不影响好条目入快照
m.SKILL_GROUPS = {}
m.COOKIE_GROUPS = {'48841181481248': 'fake'}
m.auth_failed, m.flaky_failed = set(), set()
m.fetch_cookie = lambda gid, count=20: [
    {'topic_id': 2, 'type': 'talk', 'create_time': 'not-a-time', 'text': 'x',
     'group': {'group_id': gid}, 'talk': {'text': 'x'}},
    {'topic_id': 3, 'type': 'talk', 'create_time': '2099-01-01T12:00:00.000+0800', 'text': 'y',
     'group': {'group_id': gid}, 'talk': {'text': 'y'}},
]
import contextlib as _cl
import io as _io
_ebuf = _io.StringIO()
with _cl.redirect_stderr(_ebuf):
    rc = m.main()
meta2 = json.load(open(m.META_FILE, encoding='utf-8'))
ck(meta2['unparsed_ct'] == 1, 'meta.unparsed_ct = 1（解析失败条数落盘，下游可见）')
ck(meta2.get('unparsed_ct_sample') == ['not-a-time'], 'meta 带上原值样本，便于判断是哪种格式坏了')
ck('[WARN]' in _ebuf.getvalue() and 'not-a-time' in _ebuf.getvalue(),
   'stderr 打出 [WARN] 并带上原值（不再无声）')
ck(rc == 0 and meta2['total'] == 1, '坏条目仍按窗口外丢弃（口径未变），好条目照常入快照')

print()
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
sys.exit(1 if fails else 0)
