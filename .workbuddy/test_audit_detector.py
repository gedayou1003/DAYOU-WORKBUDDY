# -*- coding: utf-8 -*-
"""审计器自检（闸门的闸门）：证明 audit_pipeline 的「高危」判定**真的会红、也真的不误红**。

为什么必须有这个测试：
  2026-09-18 的审计里，4 个**自检型脚本**（chainlib / market_codes / qt_api /
  backtest_forecast_multiperiod）被报成「会打印失败字样却退出 0」的高危，实际它们的
  `❌` 是**表格渲染符号**、命中的「失败/无法」在 **docstring** 里 —— 纯假阳性。
  假阳性 = 噪声 = 闸门被无视。收紧判定后，必须用变异测试反过来证明：
    · 真·失败打印（无退出码）→ **必须**被标记
    · 假阳性形态（渲染符号 / docstring / raise）→ **必须不**被标记
  否则这次的「降噪」就等于把闸门一起关掉了。

用法：$PY .workbuddy/test_audit_detector.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('ap', os.path.join(HERE, 'audit_pipeline.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

fails = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


def scan(src):
    return m.scan_exit_codes({'x.py': src})


# ── 真阳性：这些形态必须被标记为高危 ──────────────────────────────
print('1) 真阳性（必须红）')
cases_red = [
    ('print + [FAIL]，无退出码',
     'def main():\n    print("[FAIL] 链文件缺失")\n\nif __name__ == "__main__":\n    main()\n'),
    ('except 里 print 失败后继续，无退出码',
     'def main():\n    try:\n        go()\n    except Exception as e:\n'
     '        print(f"失败: {e}")\n\nif __name__ == "__main__":\n    main()\n'),
    ('sys.stderr.write 报错，无退出码',
     'def main():\n    sys.stderr.write("无法解析链文件\\n")\n\n'
     'if __name__ == "__main__":\n    main()\n'),
    ('logging.error 报错，无退出码',
     'def main():\n    logging.error("不存在该标的")\n\n'
     'if __name__ == "__main__":\n    main()\n'),
]
for label, src in cases_red:
    _nc, risky = scan(src)
    ck('x.py' in risky, '%s → 被标记为高危' % label)

# ── 假阳性回归：这些形态必须**不**被标记 ─────────────────────────────
print('\n2) 假阳性回归（必须不红）')
cases_green = [
    ('表格渲染符号 ❌（无输出语句）',
     'def main():\n    dir_v = ("❌相反" if pct > 0.15 else "✅同向")\n'
     '    print(dir_v)\n\nif __name__ == "__main__":\n    main()\n'),
    ('docstring 里的「失败/无法/返回 1」',
     '"""doc：全部域名失败时抛错；缺 created_at 时返回 1（说明文字）。\n'
     '不存在的字段一律忽略。"""\ndef main():\n    pass\n\n'
     'if __name__ == "__main__":\n    main()\n'),
    ('注释里的「失败」',
     'def main():\n    # 逐个域名试，失败仅记录（注释）\n    pass\n\n'
     'if __name__ == "__main__":\n    main()\n'),
    ('raise（抛异常自带非零退出，不算失败当成功）',
     'def main():\n    raise RuntimeError("全部域名均失败")\n\n'
     'if __name__ == "__main__":\n    main()\n'),
]
for label, src in cases_green:
    _nc, risky = scan(src)
    ck('x.py' not in risky, '%s → 未被误标' % label)

# ── 有退出码就不该进任何清单 ────────────────────────────────────────
print('\n3) 已有失败退出码 → 两个清单都不进')
with_code = ('def main():\n    print("[FAIL] 缺数据")\n    return 1\n\n'
             'if __name__ == "__main__":\n    sys.exit(main())\n')
nc, risky = scan(with_code)
ck('x.py' not in risky and 'x.py' not in nc, 'return 1 + sys.exit(main()) → 完全出列')

# ── no_code 与 risky 的分工：无退出码但不打印失败 → 只在 no_code ──────
print('\n4) 无退出码但也不打印失败 → 只进 no_code，不进高危')
quiet = 'def main():\n    compute()\n\nif __name__ == "__main__":\n    main()\n'
nc, risky = scan(quiet)
ck('x.py' in nc and 'x.py' not in risky, '静默脚本进 no_code、不进高危（两级如实体现在数据上）')

# ── 文档腐烂判定（scan_docs）的双向元测试 ────────────────────────────
# 为什么单列一节：2026-09-21 之前的判定是「文件名在文档里出现 + 仓库里没有 = 文档腐烂」，
# 把「已交代归档」「脚本在技能目录」和「真腐烂」混成一个数字（37 处里 33 处是噪声），
# 且 stale 分支忘了查重（同名文件被记多次）、按文件去重又会吃掉「后面的真问题」。
# 降噪的同时必须守住：**真的会红**，且**不能靠声明蒙混**。
import shutil
import tempfile

print('\n5) 文档腐烂判定（scan_docs）—— 该红的红、该绿的不报')


def run_docs(docs, files, want_raw=False):
    """沙箱化跑 scan_docs：docs={文档名: 内容}，files=要真实创建的相对路径列表。"""
    d = tempfile.mkdtemp(prefix='audit_docrot_')
    try:
        wk = os.path.join(d, 'wk')
        os.makedirs(os.path.join(wk, 'archive'), exist_ok=True)
        for rel in files:
            p = os.path.join(wk, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as fh:
                fh.write('x')
        for name, body in docs.items():
            with open(os.path.join(wk, name), 'w', encoding='utf-8') as fh:
                fh.write(body)
        # 打桩：把审计器的三个根目录指向沙箱，并清空归档缓存
        old = (m.HERE, m.ROOT, m.ARCHIVE, m._ARCH_CACHE, m.DOCS)
        m.HERE, m.ROOT = wk, wk
        m.ARCHIVE, m._ARCH_CACHE = os.path.join(wk, 'archive'), None
        m.DOCS = list(docs)
        try:
            r = m.scan_docs({'only.py': ''})
        finally:
            m.HERE, m.ROOT, m.ARCHIVE, m._ARCH_CACHE, m.DOCS = old
        return r if want_raw else r[2:6]    # stale, missing, explained, external
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ① 真阳性：已归档脚本 + 未交代 → 必须进 stale，且带行号
s, mi, ex, xt = run_docs({'a.md': '第一行\n跑 `gone.py` 就行\n'},
                         ['archive/gone.py'])
ck(len(s) == 1 and 'L2' in s[0][2], '① 引用已归档脚本且未交代 → 进 stale 并给出行号（%s）' % (s[0][2] if s else '—'))

# ② 真阳性：真不存在 + 未交代 → 必须进 missing
s, mi, ex, xt = run_docs({'a.md': '跑 `nosuch.py` 就行\n'}, [])
ck(len(mi) == 1 and mi[0][0] == 'nosuch.py', '② 引用真不存在且未交代 → 进 missing')

# ③ 假阳性回归：同行有「已归档」标注 → 只进 explained，不进 stale
s, mi, ex, xt = run_docs({'a.md': '`gone.py` 已归档至 archive/\n'}, ['archive/gone.py'])
ck(not s and len(ex) == 1, '③ 已交代归档 → 不计入腐烂（进 explained）')

# ④ 假阳性回归：带路径前缀且磁盘存在 → 只进 external
s, mi, ex, xt = run_docs({'a.md': '| `skills/chan-signal__skillhub/eng.py` |\n'},
                         ['skills/chan-signal__skillhub/eng.py'])
ck(not s and not mi and len(xt) == 1, '④ 行内路径前缀磁盘可解析 → 不计入腐烂（进 external）')

# ⑤ 文档声明外部根 + 磁盘存在 → 裸文件名也不报
s, mi, ex, xt = run_docs({'a.md': '技能目录：`skills/engdir/`\n\n跑 `eng.py`\n'},
                         ['skills/engdir/eng.py'])
ck(not mi and len(xt) == 1, '⑤ 文档声明技能目录且磁盘存在 → 裸文件名不报')

# ⑥ 【旧实现的漏网之鱼】同一文件多次出现，前一处已交代、后一处未交代 → 仍必须红
s, mi, ex, xt = run_docs(
    {'a.md': '`gone.py` 已归档至 archive/\n\n自某日起用 `gone.py` 恢复维护\n'},
    ['archive/gone.py'])
ck(len(s) == 1 and 'L3' in s[0][2], '⑥ 前一处已交代、后一处未交代 → 仍判腐烂且指向 L3（%s）' % (
    s[0][2] if s else '未报 ← 真问题被吃掉'))

# ⑦ 反向：声明的技能目录**不存在** → 不许靠声明蒙混，照旧算腐烂
s, mi, ex, xt = run_docs({'a.md': '技能目录：`skills/ghostdir/`\n\n跑 `phantom.py`\n'}, [])
ck(len(mi) == 1, '⑦ 声明了不存在的目录 → 仍判腐烂（声明不能当白名单用）')

# ⑧ 占位符与仓库内存在的脚本一律不报
s, mi, ex, xt = run_docs({'a.md': '`calc_tech_MMDD.py` → `xxx.py`\n'}, [])
ck(not s and not mi, '⑧ 命名占位符（MMDD / xxx）不报')

# ⑨ 契约守卫：返回值元数固定为 7 —— 防止调用方与实现悄悄错位
ck(len(run_docs({'a.md': '`calc_tech_MMDD.py`\n'}, [], want_raw=True)) == 7,
   '⑨ scan_docs 返回 7 元组（契约未漂移）')

# ── 静默失败扫描（scan_silent）的双向元测试 ─────────────────────────
# 为什么单列一节（2026-09-23）：旧实现是三条正则，用一次性 AST 探针实测**把 31 处漏成 15 处**：
#   ① body 是 continue/return 而不是 pass（正则只认 pass）；
#   ② except 与 pass 之间夹了注释行；③ 同行写 `except Exception: pass`。
# 改用 AST 后必须反过来证明：四类真形态都抓得到、声明过的真豁免不误红、空声明蒙混不过去、
# 正常处理逻辑与注释/docstring 里的示例一律不算。否则这次「换实现」可能只是把闸门关掉了。
print('\n6) 静默失败扫描（scan_silent）—— 该红的红、该绿的不报')


def sl(src):
    return m.scan_silent({'x.py': src})


CASES_RED = [
    ('跨行 pass', 'def f():\n    try:\n        go()\n    except Exception:\n        pass\n'),
    ('continue（旧正则漏）',
     'def f():\n    for x in y:\n        try:\n            g()\n        except Exception:\n            continue\n'),
    ('return None（旧正则漏）',
     'def f():\n    try:\n        g()\n    except Exception:\n        return None\n'),
    ('return 字面量（静默回退默认值）',
     'def f():\n    try:\n        g()\n    except Exception:\n        return False\n'),
    ('同行 pass（旧正则漏）', 'def f():\n    try:\n        g()\n    except Exception: pass\n'),
    ('except 与 pass 之间夹注释（旧正则漏）',
     'def f():\n    try:\n        g()\n    except Exception:\n        # 说明\n        pass\n'),
    ('裸 except（无异常类型）', 'def f():\n    try:\n        g()\n    except:\n        pass\n'),
    ('带类型 except + pass', 'def f():\n    try:\n        g()\n    except ValueError:\n        pass\n'),
]
for label, src in CASES_RED:
    und, dec = sl(src)
    ck(len(und) >= 1 and not dec, '%s → 计入未声明' % label)

_und, _dec = sl('def f():\n    try:\n        g()\n    except:\n        pass\n')
ck(len(_und) == 1 and 'BARE' in _und[0][2], '裸 except 只记一次（不因 body 是 pass 而二次计数）')

CASES_GREEN = [
    ('body 有实质处理（多语句）',
     'def f():\n    try:\n        g()\n    except Exception as e:\n        log(e)\n        raise\n'),
    ('docstring 里的示例代码',
     '"""示例：\n    except Exception:\n        pass\n"""\ndef f():\n    pass\n'),
    ('字符串里的示例代码', 'S = "except Exception:\\n    pass"\n'),
    ('只有 raise（抛异常自带非零退出）', 'def f():\n    raise RuntimeError("x")\n'),
    ('try 正常收尾、无 except', 'def f():\n    try:\n        g()\n    finally:\n        pass\n'),
]
for label, src in CASES_GREEN:
    und, dec = sl(src)
    ck(not und and not dec, '%s → 不进任何清单' % label)

print('\n7) 声明豁免（`# silent-ok: 原因`）—— 声明了才不计入，空声明蒙混不过去')
und, dec = sl('def f():\n    try:\n        g()\n'
              '    except Exception:  # silent-ok: 终端编码收口尽力而为\n        pass\n')
ck(not und and len(dec) == 1 and '终端编码收口' in dec[0][2],
   '写了原因 → 只进「已声明豁免」，且把原因带出来供人复核')

und, dec = sl('def f():\n    try:\n        g()\n'
              '    except Exception:  # silent-ok: abc\n        pass\n')
ck(len(und) == 1 and not dec, '原因过短（3 字）→ 视为未声明（空声明不能当白名单用）')

und, dec = sl('def f():\n    try:\n        g()\n'
              '    # silent-ok: 写在别的行\n    except Exception:\n        pass\n')
ck(len(und) == 1 and not dec, '声明没写在 except 行尾 → 不算声明')

und, dec = sl('def f():\n    try:\n        g()\n'
              '    except Exception:  # silent-ok: 注释里顺嘴提一句 silent-ok 不算\n        return None\n')
ck(not und and len(dec) == 1, '声明对四类形态一律生效（含静默 return）')

# ── 契约守卫：返回值元数固定 ────────────────────────────────────────
_pack = sl(CASES_RED[0][1])
ck(isinstance(_pack, tuple) and len(_pack) == 2
   and all(len(r) == 3 for r in _pack[0] + _pack[1]),
   'scan_silent 返回 2 元组、每项 3 元组（契约未漂移）')

print('\n8) 危险默认值（ASSIGN 类）—— 「读不动就回退到写死的字面量」')
# 为什么单列：审计 docstring 一直声称覆盖「危险默认值/静默回退」，但旧正则与 AST 四类
# 都漏了它。2026-09-23 实测它在 gen_tj_archive 里让「人工精修版不许覆盖」的生成戳守卫
# **整条跳过**（`if old_txt and ...` 短路）—— 与 2026-09-21 那次 P0 数据丢失同族。
CASES_ASSIGN = [
    ('只有赋值 + 裸字面量，异常未绑定名',
     "def f():\n    try:\n        g()\n    except OSError:\n        old = ''\n"),
    ('赋数字默认值',
     'def f():\n    try:\n        g()\n    except Exception:\n        n = 0\n'),
]
for label, src in CASES_ASSIGN:
    und, dec = sl(src)
    ck(len(und) == 1 and 'ASSIGN' in und[0][2], '%s → 计入未声明' % label)

CASES_ASSIGN_GREEN = [
    ('异常被绑定（as e）→ 视为有意的降级记录，不误红',
     'def f():\n    try:\n        g()\n    except Exception as e:\n        msg = str(e)\n'),
    ('RHS 是表达式，不是写死的默认值',
     'def f():\n    try:\n        g()\n    except Exception:\n        n = len(x)\n'),
    ('赋值之外还有别的语句（不止是赋值）',
     'def f():\n    try:\n        g()\n    except Exception:\n        n = 0\n        print(n)\n'),
]
for label, src in CASES_ASSIGN_GREEN:
    und, dec = sl(src)
    ck(not und and not dec, '%s → 不进任何清单' % label)

print()
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
sys.exit(1 if fails else 0)
