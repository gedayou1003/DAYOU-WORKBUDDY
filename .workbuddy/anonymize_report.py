# -*- coding: utf-8 -*-
"""生成晨报匿名版：星球名+人名 -> 代号，文末附解密表

用法：
    $PY .workbuddy/anonymize_report.py                         # 今天，读/写 outputs/
    $PY .workbuddy/anonymize_report.py 2026-08-21               # 指定日期（匿名化历史报告）
    $PY .workbuddy/anonymize_report.py --src A.md --out B.md    # 显式指定输入/输出
    $PY .workbuddy/anonymize_report.py 2026-08-21 --out B.md    # 混用
    $PY .workbuddy/anonymize_report.py -h                       # 本说明，退 0

退出码：
    0 生成成功，且正文无真名残留
    1 参数不合法 / 输入读不到 / 输出写不了 / **正文仍有真名残留**（不写产物）
    2 产物已写出，但真名只出现在**受保护的文件路径**里（需人工判断能否外发）

为什么退出码要管「真名残留」（2026-09-23 加固）
--------------------------------------------
旧实现把残留检查只做成一句 print —— 命中真名照样退 0。而本脚本的**唯一职责**就是脱敏：
真名残留 = 隐私泄漏 = 职责失败，却与「干净」在退出码上完全同形，调用方（人或脚本）
只能靠肉眼去读那一行 print 才分辨得出。现改为：正文残留 -> `[FAIL]` + 退 1 +
**不写产物**，与 `analyze_000001_multi.py`「失败不产出半成品」同口径 ——
否则一份带真名的「匿名版」会被当成成品交付出去。

为什么分成 1 与 2 两档
--------------------
路径必须**逐字保留**（改了文件名，报告里的链接就失效，见 `anonymize()` 的占位保护），
于是「路径里含真名」与「正文里含真名」处置不同：前者写出来但明确报 2，后者一律拦住。
两档都不许静默 —— 降噪不等于放宽。

为什么缺输入必须有意报错（2026-09-23 加固）
------------------------------------------
旧实现在这里裸 `io.open(SRC)`，当天报告还没生成时直接 FileNotFoundError 崩栈 ——
「该档还没生成」这种完全正常的时序，与「脚本坏了」在输出与退出码上一模一样
（都是 rc=1 + 一段 traceback）。现在改为一句 `[FAIL]` + 退 1，且不产出半成品。
"""
import io
import os
import re
import sys
from datetime import datetime

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # silent-ok: 终端编码收口尽力而为，失败不影响结论
        pass

# 路径解析统一走 ~/.workbuddy/paths.py（跨设备迁移核心）。
# 导入失败也必须是**有意报错**：配置一变就一段 traceback 的话，
# 「环境没配好」与「脚本有 BUG」又分不清了。
sys.path.insert(0, os.path.expanduser("~/.workbuddy"))
try:
    from paths import OUTPUTS
except Exception as e:                                   # noqa: BLE001
    sys.stderr.write('[FAIL] 路径配置读不到（%s：%s）—— 无法定位 outputs/，未做任何事\n'
                     % (type(e).__name__, e))
    sys.exit(1)

# 替换映射：先长名后短名，避免交叉污染
# 2026-09-18：报告一律以「DRAGON BALL模型」称呼该星球（原名隐藏）。
# 下面前两条原名映射**刻意保留** —— 它们用于匿名化**历史报告**（8 月的老快报里写的是
# 原名），删掉会导致老报告匿名化后仍暴露星球名。属「功能必需的匹配串」。
REPLACEMENTS = [
    ("卫斯李的投研笔记", "星球②"),
    ("AI 产业链地图·Serenity 速报", "星球⑦"),
    ("DRAGON BALL模型", "星球③"),
    ("Truth and Justice", "星球③"),
    ("180K Research", "星球⑥"),
    ("大鹏鸟笔记", "星球④"),
    ("基业长青+", "星球①"),
    ("短评&信息（可接ai）", "星球⑤"),
    ("短评&信息", "星球⑤"),
    ("基业长青", "知识库A"),
    ("浑水调研", "知识库B"),
    ("xxpq", "知识库C"),
    ("游资流沙河", "游资A"),
    ("流沙河", "游资A"),
    ("好运哥", "游资B"),
    ("卫斯李", "星球②"),
    ("大鹏鸟", "星球④"),
    ("T\\&J", "星球③"),  # 转义形式
    ("T&J", "星球③"),
    ("180K", "星球⑥"),
    ("AI 产业链", "星球⑦"),
]

# 匿名化后**不许再出现**的真名（漏配映射的哨兵）。
# 注意：`知识库B知识库` 不是真名，而是相邻替换产生的粘连残渣，
# 与双代号粘连同族，一并当残留拦住。
RESIDUAL_NAMES = [
    "卫斯李", "大鹏鸟", "流沙河", "T&J", "T\\&J", "Truth and Justice",
    "基业长青+", "180K Research", "AI 产业链地图", "短评&信息",
    "好运哥", "浑水调研", "xxpq", "知识库B知识库",
]

# 文末解密表（**刻意含真名**，供追溯用；不参与残留判定）
DECODE_TABLE = """---

## 附：匿名代号解密表（仅供追溯，阅后可删除本节）

| 代号 | 对应星球/知识库 |
|------|----------------|
| 星球① | ⭕ 基业长青+ |
| 星球② | 卫斯李的投研笔记 |
| 星球③ | DRAGON BALL模型 |
| 星球④ | 大鹏鸟笔记 |
| 星球⑤ | 短评&信息 |
| 星球⑥ | 180K Research |
| 星球⑦ | AI 产业链地图·Serenity 速报 |
| 游资A | 流沙河（大鹏鸟转述的游资观点） |
| 游资B | 好运哥 |
| 知识库A | IMA【基业长青】浑水投研🥈 |
| 知识库B | IMA【浑水调研】叫我第一名🥇 |
| 知识库C | IMA xxpq |

> 匿名原则：所有星球名、人名、游资名一律以代号呈现，阅读时只看观点本身，避免主观锚定。
"""

USAGE = ('用法：anonymize_report.py [YYYY-MM-DD] [--src 输入.md] [--out 输出.md]\n'
         '      -h/--help 看完整说明\n')


def parse_args(argv):
    """解析命令行。返回 (opts, err) —— err 非空即为**有意报错**（调用方退 1）。

    opts 为 'HELP' 表示请求帮助；否则是 {'date','src','out'}。
    为什么不用 argparse：本仓其他脚本一律手写解析（见 analyze_000001_multi.py），
    保持同一种风格便于统一体检；且这里只有 3 个参数。
    """
    opts = {'date': None, 'src': None, 'out': None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--src', '--out'):
            if i + 1 >= len(argv):
                return None, '[FAIL] %s 后面要跟路径（例：%s D:\\x.md）' % (a, a)
            key = a[2:]
            if opts[key] is not None:
                return None, '[FAIL] %s 给重了（已给 %s）' % (a, opts[key])
            opts[key] = argv[i + 1]
            i += 2
        elif a in ('-h', '--help'):
            return 'HELP', None
        elif a.startswith('-') and len(a) > 1:
            return None, '[FAIL] 不认识的参数：%s（可用：日期 / --src / --out / -h）' % a
        else:
            # 位置参数只认日期。**必须校验**：旧实现把它当日期直接拼路径，
            # 参数写错时表现成「文件不存在」而不是「参数错了」（误导诊断）。
            if opts['date'] is not None:
                return None, ('[FAIL] 日期只能给一个（已给 %s，又给 %s）'
                              % (opts['date'], a))
            opts['date'] = a
            i += 1
    if opts['date'] is not None and not re.match(r'^\d{4}-\d{2}-\d{2}$', opts['date']):
        return None, ('[FAIL] 日期格式不对：%r（要 YYYY-MM-DD）\n%s' % (opts['date'], USAGE))
    return opts, None


def anonymize(text):
    """返回 (匿名化正文, 正文残留列表, 仅路径残留列表)。

    顺序刻意如此：**先占位保护路径 → 再替换 → 占位还原前判正文残留**。
    先保护是因为路径要逐字保留（`` `outputs/知识星球晨报_x.md` `` 改名则链接失效）；
    在还原前判残留，是因为此刻路径已被占位符挡住，命中的必然在正文里 ——
    这样「正文泄漏」与「路径含真名」才能分成两档（退 1 / 退 2），不混成一条。
    """
    holders = []

    def _hold(m):
        holders.append(m.group(0))
        return '@@PATH%d@@' % (len(holders) - 1)

    body = re.sub(r'`[^`]*\.(md|html|json|PDF|pdf|docx|txt)`', _hold, text)

    for old, new in REPLACEMENTS:
        body = body.replace(old, new)

    # 修正可能的双代号粘连（如 "星球② 星球②" 由相邻替换产生）
    body = re.sub(r'(星球[①②③④⑤⑥⑦⑧⑨⑩])\s*\1', r'\1', body)
    # 修正 "知识库B知识库" 这类重复
    body = re.sub(r'(知识库[ABC])\s*知识库', r'\1', body)

    in_body = [n for n in RESIDUAL_NAMES if n in body]

    restored = body
    for i, p in enumerate(holders):
        restored = restored.replace('@@PATH%d@@' % i, p)
    in_path = [n for n in RESIDUAL_NAMES if n in restored and n not in in_body]
    return restored, in_body, in_path


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    opts, err = parse_args(argv)
    if err:
        sys.stderr.write(err)
        return 1
    if opts == 'HELP':
        print(__doc__)
        return 0

    date = opts['date'] or datetime.now().strftime('%Y-%m-%d')
    src = opts['src'] or os.path.join(OUTPUTS, '知识星球晨报_%s.md' % date)
    dst = opts['out'] or os.path.join(OUTPUTS, '知识星球晨报_%s_匿名版.md' % date)

    if not os.path.isfile(src):
        sys.stderr.write('[FAIL] 找不到待匿名化报告：%s\n' % src)
        sys.stderr.write('       日期 %s —— 该档报告尚未生成时属正常，'
                         '也可用 --src 显式指定输入\n' % date)
        sys.stderr.write('       未生成匿名版（不产出半成品）\n')
        return 1
    try:
        with io.open(src, encoding='utf-8') as f:
            text = f.read()
    except Exception as e:                               # noqa: BLE001
        sys.stderr.write('[FAIL] 报告读不动（%s：%s）—— 未生成匿名版\n'
                         % (type(e).__name__, e))
        return 1

    body, in_body, in_path = anonymize(text)

    if in_body:
        sys.stderr.write('[FAIL] 匿名化未完成：正文仍有 %d 类真名残留 —— %s\n'
                         % (len(in_body), '、'.join(in_body)))
        sys.stderr.write('       真名残留 = 隐私泄漏，故**不写产物**；'
                         '请把它们补进 REPLACEMENTS 后重跑\n')
        if os.path.isfile(dst):
            sys.stderr.write('       注意：已存在的同名旧文件未被改动，'
                             '可能是过期版本：%s\n' % dst)
        return 1

    # 写：目录不存在/权限不足同样是有意报错，不是崩栈
    try:
        with io.open(dst, 'w', encoding='utf-8') as f:
            f.write(body + DECODE_TABLE)
    except Exception as e:                               # noqa: BLE001
        sys.stderr.write('[FAIL] 匿名版写不了（%s：%s）—— 未产出\n'
                         % (type(e).__name__, e))
        return 1

    print('匿名版已生成: %s' % dst)
    print('残留名字检查: 正文无残留')   # 只声明正文：文末解密表**刻意含真名**，不在判定范围
    print('字节数: %d' % len(body.encode('utf-8')))

    if in_path:
        sys.stderr.write('[WARN] 真名只出现在受保护的文件路径里，未被替换'
                         '（路径须逐字保留）：%s\n' % '、'.join(in_path))
        sys.stderr.write('       产物已写出，但请人工确认这些路径能否外发\n')
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
