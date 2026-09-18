# -*- coding: utf-8 -*-
"""生成「DRAGON BALL模型」原始记录归档，一字不差原文。

从 zsxq_fetch_raw.json 筛选目标星球帖子
→ 生成 outputs/DRAGON_BALL_原始记录_YYYY-MM-DD.md

用法：python gen_tj_archive.py [--force]
  --force  跳过「缩水守卫」，允许用更少条数覆盖当天已有归档

2026-09-18 改名（用户要求隐藏星球原名）：
  1) 输出文件名由旧前缀 `*_原始记录_*.md` 改为 `DRAGON_BALL_原始记录_*.md`
     （check_integrity.py 的归档缺口检测已同步；23 个历史归档已一并改名）
  2) 筛选口径由「按 group 显示名匹配」改为「按 gid 匹配」——
     gid 是稳定标识、与显示名解耦。改名前那种「拿星球名当匹配串」的写法
     会在改名后直接失效，且会把原名永久留在脚本里。

2026-09-18 审计 P0-3 加固（四道守卫）
------------------------------------
改前：无论筛出几条都**无条件 `open(out,'w')` 覆盖**当天归档，且无条件打印
「归档完成，N 条」并退出 0。抓取空转一次（Cookie 失效 / 限流 / 窗口错位），
当天的归档就被清成 0 条空壳，而输出看起来仍是成功 —— 失败被伪装成成功。

改后：
  0) **降级守卫**：读 zsxq_fetch_meta.json，若主快照不是最新一轮抓取的结果
     （上一轮降级 → 主快照按 P0-2 守卫保持旧内容），拒绝归档并退出 2。
     否则会把**上一轮内容**写成今天的记录，比空壳更隐蔽。
  1) **0 条守卫**：筛出 0 条时既不写文件也不打印「完成」，改为告警 + 退出码 2。
     不写空文件是刻意的：`check_integrity.py`【1】用「归档文件是否存在」判定缺口，
     若允许产出 0 条空壳，那道检测就会变绿 —— 又一个假绿。
  2) **缩水守卫**：当天已有归档且条数 ≥ 本轮时，不覆盖（避免残缺抓取把完整归档冲掉），
     退出码 2；确实想覆盖用 `--force`。
  3) **原子写**：临时文件 → 回读断言（条目数 > 0 且与源数据一致）→ 原子替换。
     杜绝写到一半崩溃留下半截 md。
另：归档里的「抓取通道」不再写死 `zsxq-cli Skill`、窗口档位也不再靠猜，
均按快照/元信息里的实际值渲染，取不到就如实写「未记录」。
"""
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, 'zsxq_fetch_raw.json')
META = os.path.join(HERE, 'zsxq_fetch_meta.json')

# 目标星球按 gid 识别（唯一、稳定，不受显示名变更影响）
TARGET_GID = '88512145458842'

# 抓取通道 gid/名称 → 归档里的人类可读说明
CHANNEL_LABEL = {
    'skill': 'zsxq-cli Skill 通道',
    'cookie': 'Cookie 直连官方 API',
}


def _channel_text(items):
    """按快照里实际记录的 channel 渲染通道说明（旧快照无该字段则如实说明未记录）"""
    chans = sorted({t.get('channel') for t in items if t.get('channel')})
    if not chans:
        return '未记录（该快照生成于 channel 字段引入之前）'
    return ' + '.join(CHANNEL_LABEL.get(c, c) for c in chans)


def read_meta(snapshot_total):
    """读抓取元信息，返回 {'label': 窗口档位说明, 'stale': 阻断原因或 None, 'info': 提示或 None}。

    `stale` 非空 = 手上这份快照**不是最新一轮抓取的结果**：
    上一轮抓取降级时（Cookie 失效 / 限流 / 0 条），主快照按 P0-2 守卫保持为旧内容，
    最新结果落在 zsxq_fetch_raw_degraded_*.json。此时若照常归档，就会把
    **上一轮的内容**标成今天的归档 —— 比 0 条空壳更隐蔽的一类错误。
    """
    out = {'label': '', 'stale': None, 'info': None}
    if not os.path.exists(META):
        return out                       # 旧快照无 meta：向后兼容，不阻断、不标注
    try:
        with open(META, encoding='utf-8') as f:
            meta = json.load(f)
    except (OSError, ValueError) as e:
        out['info'] = 'meta 不可读（%s），本条归档不标注窗口档位' % e
        return out
    if meta.get('snapshot') != os.path.basename(SRC):
        out['stale'] = ('最新一轮抓取写的是 %s（%s），主快照 %s 未被更新'
                        % (meta.get('snapshot'),
                           '；'.join(meta.get('degraded') or ['无降级说明']),
                           os.path.basename(SRC)))
        return out
    if meta.get('total') != snapshot_total:
        out['info'] = ('meta 记 %s 条、快照实为 %d 条（快照被改过或 meta 过期），'
                       '本条归档不标注窗口档位' % (meta.get('total'), snapshot_total))
        return out
    out['label'] = meta.get('window') or ''
    return out


def build_md(items, all_items, today, window_label=''):
    """拼归档正文。items 为目标星球条目，all_items 为本轮快照全部条目（用于算窗口）。"""
    ts = sorted(x.get('create_time', '') for x in all_items if x.get('create_time'))
    win_start = ts[0][:19] if ts else '未知'
    win_end = ts[-1][:19] if ts else '未知'
    win_note = '（%s）' % window_label if window_label else ''

    md = f'''# DRAGON BALL模型 原始记录归档 · {today}

> 一字不差原文归档 · 摘自知识星球「DRAGON BALL模型」频道 · 仅供本人查阅使用

## 抓取窗口

- 抓取时段：{win_start} ~ {win_end}{win_note}
- 本期共 **{len(items)}** 条
- 抓取通道：{_channel_text(items)}

---

'''
    for i, t in enumerate(items, 1):
        title = t.get('text', '').replace('\n', ' ')[:80]
        files = t.get('files') or []
        file_txt = '、'.join("%s (%dKB)" % (f.get('name', '?'), f.get('size', 0) // 1024)
                             for f in files) or '无'
        md += f'''## [{i}] {t['create_time']} · {title}...

- **topic_id**: {t.get('topic_id')}
- **发布时间**: {t.get('create_time')}
- **类型**: {t.get('type', 'text')}
- **正文（原文一字不差）**:

```
{t.get('text', '')}
```

- **附件**（{len(files)}）: {file_txt}
- **图片**（{len(t.get('images') or [])}）: {len(t.get('images') or [])} 张

---

'''
    return md


def _entry_count(text):
    """数归档正文里的条目块数（'## [n]' 行数）—— 用于缩水守卫与回读断言"""
    return sum(1 for ln in text.split('\n') if ln.startswith('## ['))


def _atomic_write(path, md, expect_n):
    """临时文件 → 回读断言 → 原子替换。expect_n 为期望条目数（须 > 0）。"""
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(md)
    with open(tmp, encoding='utf-8') as f:
        back = f.read()
    n = _entry_count(back)
    if expect_n <= 0 or n != expect_n:
        os.remove(tmp)
        raise RuntimeError('归档回读断言失败：期望 %d 条，落盘后读回 %d 条' % (expect_n, n))
    os.replace(tmp, path)


def main():
    force = '--force' in sys.argv

    if not os.path.exists(SRC):
        print('[FAIL] 找不到抓取快照：%s（先跑 fetch_zsxq.py）' % SRC, file=sys.stderr)
        return 1
    with open(SRC, encoding='utf-8') as f:
        d = json.load(f)

    meta = read_meta(len(d))
    if meta['info']:
        print('[INFO] %s' % meta['info'])
    # 守卫 0：主快照不是本轮结果 —— 归档会把上一轮内容标成今天，必须拦住
    if meta['stale']:
        print('[WARN] 主快照不是最新一轮抓取的结果：%s' % meta['stale'])
        print('       已跳过归档：照常归档会把**上一轮的内容**写成今天的记录（比空壳更隐蔽）。')
        print('       处理：① 先解决抓取降级并重跑 fetch_zsxq.py；'
              '② 或把 SRC 指向 zsxq_fetch_raw_degraded_*.json 再归档。')
        return 2

    items = [t for t in d if str(t.get('gid')) == TARGET_GID]
    items.sort(key=lambda x: x['create_time'])

    today = datetime.now().strftime('%Y-%m-%d')
    out = os.path.join(ROOT, 'outputs', 'DRAGON_BALL_原始记录_%s.md' % today)

    # 守卫 1：0 条 —— 不写文件（写空壳会让 check_integrity 的归档缺口检测变假绿）
    if not items:
        print('[WARN] 本轮筛出 0 条 DRAGON BALL模型 内容（快照共 %d 条，目标 gid=%s）。'
              % (len(d), TARGET_GID))
        print('       已跳过归档：不覆盖 %s，也不创建空壳文件。' % out)
        print('       排查顺序：① 抓取窗口是否错位（看快照里 gid 分布）'
              '② 该星球是否确实无新帖 ③ Cookie/限流是否异常。')
        return 2

    md = build_md(items, d, today, meta['label'])

    # 守卫 2：缩水 —— 已有归档条数 ≥ 本轮时默认不覆盖
    if os.path.exists(out) and not force:
        try:
            with open(out, encoding='utf-8') as f:
                old_n = _entry_count(f.read())
        except OSError:
            old_n = 0
        if old_n > len(items):
            print('[WARN] 当天归档已有 %d 条，本轮只筛出 %d 条 —— 疑似抓取残缺。' % (old_n, len(items)))
            print('       已保留原归档（不覆盖）：%s' % out)
            print('       确认要用本轮覆盖，加 --force 重跑。')
            return 2

    _atomic_write(out, md, len(items))
    print('DRAGON BALL模型 归档完成，%d 条 -> %s' % (len(items), out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
