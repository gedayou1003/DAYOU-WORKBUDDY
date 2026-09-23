# -*- coding: utf-8 -*-
"""「失败无声」与「假绿」修复的回归闸门（2026-09-23 第九轮）。

六处病灶同族 —— 都让「出错了」与「本来就这样」在输出/退出码上不可区分：

  1) forecast_analyze.py
     · `run_py` 只回 stdout，退出码与被 capture 的 stderr 全丢 → 报错字段只剩空串；
     · `main()` 没有返回值（无 `sys.exit`）→ **行情取不到也照样打印数据包并退出 0**，
       而数据包的核心就是行情（第一原则·无退出码语义）。
  2) fetch_zsxq.py
     · skill 通道（zsxq-cli）超时 / 退出码非 0 / 返回非 JSON，只 print 到 stderr；
       不计数、不进 degraded、不影响退出码 → zsxq-cli 挂了而 Cookie 通道还有数据时，
       脚本退 0、快照照写，**报告静默缺掉整个星球**（含 DRAGON BALL模型 原文归档的上游）。
  3) check_cookie.py
     · `read_clipboard` 把「powershell 起不来」与「剪贴板为空」塌缩成同一个空串，
       还把系统级故障说成用户没复制东西。
  4) chainlib.py 自检
     · `__main__` 裸 open 读链：缺文件 → FileNotFoundError 崩栈。退出码同为 1，
       「脚本崩了」与「自检查出问题」不可区分，输出里没有一句诊断。
  5) check_integrity.py
     · 裸 `open(FORECAST)`：缺链 → 崩栈（同上）；现改为有意报错 + 明说「无法给出任何结论」。
  6) check_layout.py
     · 候选报告全不存在时打「汇总：2 份，ERROR 0，WARN 0」并退 0 ——
       **一份都没检查却报「通过」**（「证据缺失 == 通过」型假绿）。
  7) anonymize_report.py（2026-09-23 补，由冒烟新加的「崩栈即失败」硬判据抓出）
     · 裸 `io.open(SRC)`：当天报告还没生成（完全正常的时序）→ FileNotFoundError 崩栈，
       与「自检查出问题」在输出与退出码上不可区分；
     · 残留检查只做成一句 print —— 真名没被替换掉照样退 0、照样写出「匿名版」。
       本脚本的**唯一职责**就是脱敏，故这是「交付了一份泄漏真名的匿名报告却报成功」；
       现改为正文残留 → `[FAIL]` + 退 1 + **不写产物**；真名只落在受保护路径里 → 退 2。
     · 另加 `--src/--out`：否则冒烟只能让它写**真实 outputs/**（相当于冒烟往交付目录
       塞产物），且「缺输入」这条路径在当天报告恰好存在时根本跑不到。

全部用 monkeypatch + 沙箱，**不联网、不碰仓库文件、不写任何产物**。
§2c / §5b / §7b / §9C 是变异自证：还原旧行为后，本测试的判据必须翻转。

用法：$PY .workbuddy/test_degrade_exitcodes.py
"""
import contextlib
import io
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
# 显式把本目录加入模块搜索路径：被测脚本 import 同目录模块（market_codes / qt_api / chainlib…），
# 变异体写在临时目录时那里没有它们 —— 依赖必须从**仓库正本目录**解析（第四原则的坑）。
sys.path.insert(0, HERE)
fails = []


def ck(cond, msg):
    print('  [%s] %s' % ('OK' if cond else 'FAIL', msg))
    if not cond:
        fails.append(msg)


def load(name, path=None):
    p = path or os.path.join(HERE, name + '.py')
    spec = importlib.util.spec_from_file_location('mod_' + name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run_main(mod, argv):
    """在进程内跑 mod.main()，返回 (rc, stdout, stderr)。"""
    so, se = io.StringIO(), io.StringIO()
    saved_argv = sys.argv
    sys.argv = [getattr(mod, '__file__', 'x')] + list(argv)
    try:
        with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
            rc = mod.main()
    finally:
        sys.argv = saved_argv
    return rc, so.getvalue(), se.getvalue()


def code_only(src):
    """只看代码区：剔掉整行注释（docstring 里的说明不算命中，本项目老坑）。"""
    return '\n'.join(ln.split('#')[0] for ln in src.split('\n'))


def fake_proc(rc=0, out='', err=''):
    return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)


# ==================================================== 1. forecast_analyze
print('1) forecast_analyze.py · 行情失败必须带出原因（rc + stderr）')
fa = load('forecast_analyze')
saved_run_py = fa.run_py
try:
    fa.run_py = lambda *a: ('', 1, 'boom: 腾讯接口无响应')
    d = fa.fetch_ohlc('000001')
    ck('error' in d and '退出码 1' in d['error'] and 'boom' in d['error'],
       'rc≠0 且无输出 → error 里带退出码与 stderr：%s' % d.get('error'))

    fa.run_py = lambda *a: ('not a json', 0, '')
    d = fa.fetch_ohlc('000001')
    ck('error' in d and 'JSON' in d['error'], '输出不是 JSON → error 说明是解析问题：%s' % d.get('error'))

    fa.run_py = lambda *a: ('{"error": "无法识别的标的: xxx"}', 1, '')
    d = fa.fetch_ohlc('000001')
    ck(d.get('error') == '无法识别的标的: xxx', '上游已有的结构化 error 原样透传（不覆盖成笼统文案）')

    fa.run_py = lambda *a: ('{"close": 3100}', 0, '')
    d = fa.fetch_ohlc('000001')
    ck(d.get('close') == 3100 and 'error' not in d, '正常路径：无 error 字段（判定口径不变）')

    fa.run_py = lambda *a: ('{"close": 3100}', 2, 'warn')
    d = fa.fetch_ohlc('000001')
    ck('error' in d and '退出码 2' in d['error'], 'rc≠0 却给出看似正常的行情 → 就地标注，不静默采信')
finally:
    fa.run_py = saved_run_py

print('\n2) forecast_analyze.py · main() 的三态退出码（0 完整 / 1 行情缺失 / 2 引擎降级）')
_saved = {k: getattr(fa, k) for k in ('resolve', 'fetch_ohlc', 'run_engine', 'load_chain', 'compute_tj_bypass')}
try:
    fa.resolve = lambda c: {'code': '000001', 'name': '上证综指',
                            'tencent': 'sh000001', 'data_source': 'tencent'}
    fa.load_chain = lambda: []
    fa.compute_tj_bypass = lambda tc: {'signal': None}

    fa.fetch_ohlc = lambda c: {'close': 3100, 'open': 3090, 'prev_close': 3080}
    fa.run_engine = lambda c: ({'signals': []}, None)
    rc, out, err = run_main(fa, [])
    ck(rc == 0, '行情+引擎都正常 → rc=0（rc=%s）' % rc)
    ck('"ohlc"' in out and 'engine_error' not in out, '数据包内含行情、无降级字段')

    fa.fetch_ohlc = lambda c: {'error': 'get_daily_ohlc.py 退出码 1：网络不通'}
    rc, out, err = run_main(fa, [])
    # 失败路径四连：非零退出 / 有意报错而非裸崩 / 诊断含关键词 / 仍打印数据包供排查
    ck(rc == 1, '行情缺失 → rc=1（旧行为是 rc=0，见 §2c 变异自证）')
    ck('[FAIL]' in err and '行情未取到' in err, 'stderr 有意报错且点明「行情未取到」')
    ck('Traceback' not in err, '不是裸崩溃（有意报错）')
    ck('网络不通' in err, '诊断里带上了底层原因（旧实现这里是空串）')
    ck('"ohlc"' in out, '数据包照样打印（供人工排查），但退出码已表明不可用')

    fa.fetch_ohlc = lambda c: {'close': 3100, 'open': 3090, 'prev_close': 3080}
    fa.run_engine = lambda c: (None, '引擎退出码 3：找不到引擎脚本')
    rc, out, err = run_main(fa, [])
    ck(rc == 2, '引擎降级但行情/链路仍在 → rc=2（WARN，不是 ERROR）')
    ck('engine_error' in out, '降级原因落进数据包（调用方/AI 可读）')

    print('\n2b) 契约守卫：退出码与文档必须同时在位')
    src = code_only(io.open(os.path.join(HERE, 'forecast_analyze.py'), encoding='utf-8').read())
    ck(re.search(r'^if __name__ == .__main__.:\s*\n\s*sys\.exit\(main\(\)\)', src, re.M) is not None,
       '入口用 sys.exit(main()) 传递退出码')
    ck(src.count('return 1') >= 1 and src.count('return 2') >= 1,
       'main() 里既有 1（行情缺失）也有 2（引擎降级）')
    raw = io.open(os.path.join(HERE, 'forecast_analyze.py'), encoding='utf-8').read()
    ck('退出码（2026-09-23 起' in raw and '1 = ERROR' in raw and '2 = WARN' in raw,
       'docstring 写明 0/1/2 口径（调用方不必读源码猜）')

    print('\n2c) 变异自证：把退出码那段还原成旧行为，本测试的判据必须翻转')
    mutated = raw[:raw.index('    # 退出码语义（2026-09-23 新增')] + '    return None\n\n\n' \
        + raw[raw.index("if __name__ == '__main__':"):]
    # 自证①：变异应用成功且覆盖完整（该删的整块都删了）
    ck('[FAIL] 行情未取到' not in mutated and 'return None' in mutated and 'print(json.dumps(result' in mutated,
       '变异体构造成功：退出码整块已移除，数据包打印仍在')
    sb = tempfile.mkdtemp(prefix='mut_fa_')
    try:
        mp = os.path.join(sb, 'forecast_analyze.py')
        io.open(mp, 'w', encoding='utf-8').write(mutated)
        fm = load('forecast_analyze_mut', mp)
        for k, v in _saved.items():
            setattr(fm, k, v)
        fm.resolve = fa.resolve
        fm.load_chain = lambda: []
        fm.compute_tj_bypass = lambda tc: {'signal': None}
        fm.fetch_ohlc = lambda c: {'error': 'get_daily_ohlc.py 退出码 1：网络不通'}
        rc_m, out_m, err_m = run_main(fm, [])
        # 自证②：变异体确实复现了旧反模式（行情缺失仍退 0）
        ck(rc_m in (0, None), '变异体复现旧反模式：行情缺失却 rc=%r（即本测试真的盯着这个缺陷）' % rc_m)
        ck(rc_m != 1, '同一夹具下正本 rc=1、变异体 rc≠1 —— 闸门对该缺陷敏感')
    finally:
        shutil.rmtree(sb, ignore_errors=True)
finally:
    for k, v in _saved.items():
        setattr(fa, k, v)


# ==================================================== 3. fetch_zsxq
print('\n3) fetch_zsxq.py · skill 通道失败必须进降级并影响退出码')
fz = load('fetch_zsxq')
saved_sub_run = fz.subprocess.run
saved_net = {k: getattr(fz, k) for k in ('SKILL_GROUPS', 'COOKIE_GROUPS', 'fetch_cookie',
                                         'save_snapshot', 'time', 'WIN_START', 'WIN_END')}
try:
    print('  3a) fetch_skill 的三种失败都记入 skill_errored')
    fz.subprocess.run = lambda *a, **k: fake_proc(rc=1, out='', err='cmd not found')
    fz.skill_errored.clear()
    ck(fz.fetch_skill('111') == [] and '111' in fz.skill_errored,
       'zsxq-cli 退出码非 0 → 返回空且记入 skill_errored')

    def _timeout(*a, **k):
        raise fz.subprocess.TimeoutExpired('zsxq-cli', 90)
    fz.subprocess.run = _timeout
    fz.skill_errored.clear()
    fz.fetch_skill('222')
    ck('222' in fz.skill_errored, '超时 → 记入 skill_errored')

    fz.subprocess.run = lambda *a, **k: fake_proc(rc=0, out='oops not json', err='')
    fz.skill_errored.clear()
    fz.fetch_skill('333')
    ck('333' in fz.skill_errored, 'stdout 非 JSON → 记入 skill_errored')

    print('\n  3b) main()：skill 全挂 + cookie 有数据 → 降级、不覆盖主快照、退 2')
    fz.subprocess.run = lambda *a, **k: fake_proc(rc=1, out='', err='cli broken')  # skill 通道走真实失败分支
    fz.SKILL_GROUPS = {'111': 'A星球'}
    fz.COOKIE_GROUPS = {'222': 'B星球'}
    now = fz.datetime.now(fz.CST)
    fz.WIN_START, fz.WIN_END = now - fz.timedelta(hours=1), now + fz.timedelta(hours=1)
    fz.fetch_cookie = lambda gid, count=20: [
        {'topic_id': 't1', 'type': 'talk', 'create_time': now.isoformat(), 'talk': {'text': 'hi'}}]
    seen = {}
    fz.save_snapshot = lambda results, degraded: (
        seen.update(results=results, degraded=degraded), ('SB.json', False))[1]
    fz.time = types.SimpleNamespace(sleep=lambda s: None)   # 免掉 3s/5s 空等

    rc, out, err = run_main(fz, [])
    ck(rc == 2, 'skill 通道失败 → rc=2（旧行为 rc=0）')
    ck(len(seen.get('results', [])) == 1, 'cookie 通道的 1 条数据仍在（不是整轮失败）')
    ck(any('skill 通道失败' in d for d in seen.get('degraded', [])),
       '降级原因进 degraded（→ save_snapshot 不覆盖主快照）：%s' % seen.get('degraded'))
    ck('SKILL_FAILED=1' in out, '收尾打印 SKILL_FAILED=1（机器可读计数）')
    ck('111' in out, '计数里点明是哪个星球（gid 可追）')

    print('\n  3c) 契约守卫：module 级计数器必须每轮清零（否则 import 后重复调用会串味）')
    src = code_only(io.open(os.path.join(HERE, 'fetch_zsxq.py'), encoding='utf-8').read())
    ck(re.search(r'skill_errored\.clear\(\)', src) is not None
       and re.search(r'auth_failed\.clear\(\)', src) is not None
       and re.search(r'flaky_failed\.clear\(\)', src) is not None,
       'main() 开头清 _BAD_CT / auth_failed / flaky_failed / skill_errored')
    ck(re.search(r'if r\.returncode != 0:', src) is not None
       and re.search(r'skill_errored\.add\(gid\)', src) is not None,
       'fetch_skill 里「退出码非 0」有显式分支并记账')
finally:
    fz.subprocess.run = saved_sub_run
    for k, v in saved_net.items():
        setattr(fz, k, v)


# ==================================================== 4. check_cookie
print('\n4) check_cookie.py · 剪贴板失败要说清是系统故障还是真没内容')
cc = load('check_cookie')
saved_cc = cc.subprocess.run
try:
    cc.subprocess.run = lambda *a, **k: fake_proc(rc=0, out='  token=abc  ', err='')
    ck(cc.read_clipboard() == ('token=abc', None), '正常：返回 (文本, None)')

    cc.subprocess.run = lambda *a, **k: fake_proc(rc=1, out='', err='Get-Clipboard : 拒绝访问')
    t, why = cc.read_clipboard()
    ck(t == '' and '退出码 1' in (why or '') and '拒绝访问' in (why or ''),
       'rc≠0 → 带回原因（旧实现只回空串）：%s' % why)

    def _boom(*a, **k):
        raise FileNotFoundError('powershell')
    cc.subprocess.run = _boom
    t, why = cc.read_clipboard()
    ck(t == '' and 'powershell 调用失败' in (why or ''), '异常 → 带回原因：%s' % why)

    src = code_only(io.open(os.path.join(HERE, 'check_cookie.py'), encoding='utf-8').read())
    ck(re.search(r'raw,\s*why\s*=\s*read_clipboard\(\)', src) is not None,
       '调用点解包 (raw, why)')
    ck(re.search(r'"\[FAIL\] 未取到内容%s"\s*%\s*\("：" \+ why', src) is not None,
       '失败时把 why 打进提示（系统故障不再伪装成「剪贴板为空」）')
    ck('errors="replace"' in src, '读剪贴板用 errors=replace（非法字节不再塌成「空」）')
finally:
    cc.subprocess.run = saved_cc


# ==================================================== 5. chainlib 自检
print('\n5) chainlib.py · 自检失败路径必须「有意报错」而不是崩栈')
# 病灶：`__main__` 里裸 io.open 读链，缺文件 → FileNotFoundError 崩栈。
# 退出码同样是 1，于是「脚本崩了」与「自检查出问题」在退出码上完全不可区分，
# 调用方（smoke F1 / 人）拿到的只有一坨栈、没有一句诊断。§5b 是变异自证。
box = tempfile.mkdtemp(prefix='tde_chainlib_')


def run_script(path, extra_env=None, argv=()):
    """子进程跑一个脚本，返回 (rc, stdout+stderr)。"""
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    env.update(extra_env or {})
    r = subprocess.run([sys.executable, path] + list(argv), capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env=env, timeout=180)
    return r.returncode, (r.stdout or '') + (r.stderr or '')


def run_main_safe(mod, argv):
    """进程内跑 main()，把 sys.exit / 异常统一折成 rc，并保留 stdout/stderr。

    ⚠️ 教训（2026-09-23 实测）：`sys.exit()` 抛的是 **SystemExit，它继承 BaseException
    而不是 Exception** —— 只 `except Exception` 会让整个测试进程跟着退出
    （现象：§7 打印完标题就没有下文、退出码 1，看着像「测试自己崩了」）。
    这里显式接住 SystemExit 并把 `e.code` 当 rc（字符串 code 按解释器语义折成 1）。
    """
    so, se = io.StringIO(), io.StringIO()
    saved = sys.argv
    sys.argv = [getattr(mod, '__file__', 'x')] + list(argv)
    try:
        with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
            try:
                rc = mod.main()
            except SystemExit as e:
                rc = e.code
    except Exception as e:                                  # noqa: BLE001
        rc = 99
        se.write('%s: %s' % (type(e).__name__, e))
    finally:
        sys.argv = saved
    if rc is None:
        rc = 0
    elif not isinstance(rc, int):
        rc = 1                                              # sys.exit('原因') → 解释器语义为 1
    return rc, so.getvalue(), se.getvalue()


def copy_with_deps(name, dest_dir):
    """把脚本正本 + **同目录真实存在的依赖模块**一起复制进沙箱。

    教训（2026-09-18 实证）：只复制脚本正本 → 变异体 import 同目录模块时
    ModuleNotFoundError，30 条断言里 19 条是**假失败**，闸门哑了一整轮。
    """
    src = os.path.join(HERE, name)
    shutil.copy2(src, os.path.join(dest_dir, name))
    body = io.open(src, encoding='utf-8').read()
    for mod in sorted(set(re.findall(r'^\s*(?:import|from)\s+([A-Za-z_]\w*)', body, re.M))):
        cand = os.path.join(HERE, mod + '.py')
        if os.path.exists(cand):
            shutil.copy2(cand, os.path.join(dest_dir, mod + '.py'))
    return os.path.join(dest_dir, name)


try:
    empty = os.path.join(box, 'empty'); os.makedirs(empty)
    okd = os.path.join(box, 'ok'); os.makedirs(okd)
    badd = os.path.join(box, 'bad'); os.makedirs(badd)
    for n in ('forecast_chain.json', 'consensus_chain.json'):
        with io.open(os.path.join(okd, n), 'w', encoding='utf-8') as f:
            json.dump({'records': []}, f, ensure_ascii=False)
        with io.open(os.path.join(badd, n), 'w', encoding='utf-8') as f:
            f.write('{ 这不是 JSON')

    CL = os.path.join(HERE, 'chainlib.py')
    rc, blob = run_script(CL, {'CHAIN_DIR': empty})
    ck(rc == 1, 'A 缺链文件 → rc=1（rc=%s）' % rc)
    ck('[FAIL]' in blob, 'A 有 [FAIL] 诊断 —— 不是无声失败（第三原则·有意报错）')
    ck('Traceback' not in blob, 'A 没有 traceback —— 崩栈不算「有意报错」')
    ck('FileNotFoundError' in blob or '链读不动' in blob, 'A 诊断里带出具体原因')

    rc, blob = run_script(CL, {'CHAIN_DIR': okd})
    ck(rc == 0, 'B 对照组：链正常 → rc=0（守卫不误伤，rc=%s）' % rc)
    ck('[FAIL]' not in blob, 'B 对照组：不刷 [FAIL]')

    rc, blob = run_script(CL, {'CHAIN_DIR': badd})
    ck(rc == 1 and '[FAIL]' in blob and 'Traceback' not in blob,
       'C 链是坏 JSON → rc=1 + [FAIL] + 不崩栈（rc=%s）' % rc)

    # ---- §5b 变异自证：把 __main__ 还原成旧写法，判据必须翻转 ----
    src = io.open(CL, encoding='utf-8').read()
    new_tail = ("if __name__ == '__main__':\n"
                "    # 自检：py chainlib.py  → 打印两条链状态 + 偏差统计\n"
                "    sys.exit(_selfcheck())")
    old_tail = ("if __name__ == '__main__':\n"
                "    for n in ('forecast', 'consensus'):\n"
                "        print(chain_status(n))\n"
                "        print()\n"
                "    print('--- 偏差统计（forecast）---')\n"
                "    print(render_bias_table(bias_stats('forecast')))")
    ck(new_tail in src, '变异自证·前置：正本里能定位到新写法（否则变异无从下手）')
    mut = os.path.join(box, 'chainlib_mut.py')
    mutated = src.replace(new_tail, old_tail)
    with io.open(mut, 'w', encoding='utf-8') as f:
        f.write(mutated)
    ck(mutated != src and old_tail in mutated, '变异自证·变异已应用，且复现旧反模式')
    rc, blob = run_script(mut, {'CHAIN_DIR': empty})
    ck('Traceback' in blob and '[FAIL]' not in blob,
       '变异自证·判定翻转：旧写法缺链时崩栈且无 [FAIL]（rc=%s）' % rc)
finally:
    shutil.rmtree(box, ignore_errors=True)


# ==================================================== 6. check_integrity
print('\n6) check_integrity.py · 缺链时必须 [FAIL]，不许裸崩')
# 病灶：裸 open(FORECAST) → 缺文件时 FileNotFoundError 崩栈，退出码同为 1，
# 与「查到 ERROR」不可区分，且输出里没有一句 [FAIL]。修法是**有意报错** + 明说无结论。
ci = load('check_integrity')
saved_ci = (ci.FORECAST, ci.CONSENSUS)
box2 = tempfile.mkdtemp(prefix='tde_integrity_')
try:
    ci.FORECAST = os.path.join(box2, 'forecast_chain.json')
    ci.CONSENSUS = os.path.join(box2, 'consensus_chain.json')

    rc, so, se = run_main_safe(ci, [])
    ck(rc == 1, '缺链 → rc=1（不再是未捕获异常，rc=%s）' % rc)
    ck('[FAIL]' in se, '[FAIL] 进 stderr（不是一坨栈）')
    ck('Traceback' not in (so + se), '缺链不崩栈')
    ck('无法给出任何结论' in se, '明说「无法给出任何结论」——不许让人误读成通过')

    for n in ('forecast_chain.json', 'consensus_chain.json'):
        with io.open(os.path.join(box2, n), 'w', encoding='utf-8') as f:
            f.write('{ 这不是 JSON')
    rc, so, se = run_main_safe(ci, [])
    ck(rc == 1 and '[FAIL]' in se and 'Traceback' not in (so + se),
       '坏 JSON → rc=1 + [FAIL] + 不崩栈（rc=%s）' % rc)
    ck('链文件读不动' in se, '坏 JSON 的诊断与「文件不存在」区分开')

    # 对照组：链可读时不得刷「链文件」相关 [FAIL]（守卫不误伤）
    ci.FORECAST, ci.CONSENSUS = saved_ci
    rc, so, se = run_main_safe(ci, [])
    ck('Traceback' not in (so + se), '对照组：真链可读 → 不崩栈（rc=%s）' % rc)
    ck('[FAIL] 链文件' not in se, '对照组：不刷链文件类 [FAIL]')
finally:
    ci.FORECAST, ci.CONSENSUS = saved_ci
    shutil.rmtree(box2, ignore_errors=True)


# ==================================================== 7. check_layout
print('\n7) check_layout.py · 「一份都没查到」不许报绿')
# 病灶：候选报告全不存在时，原实现打「汇总：2 份，ERROR 0，WARN 0」并以 0 退出 ——
# 一份都没检查却报「通过」，是「证据缺失 == 通过」型的假绿。§7b 是变异自证。
cl = load('check_layout')
box3 = tempfile.mkdtemp(prefix='tde_layout_')
try:
    miss_a = os.path.join(box3, '不存在A.md')
    miss_b = os.path.join(box3, '不存在B.md')
    rc, so, se = run_main_safe(cl, [miss_a, miss_b])
    ck(rc == 1, '候选全不存在 → rc=1（旧行为 rc=0，见 §7b，rc=%s）' % rc)
    ck('[FAIL]' in se and '未做任何检查' in se, '明说「未做任何检查（不是通过）」')
    ck('不是通过' in so, 'stdout 汇总也不说「通过」')

    # 对照组：真报告在 → 正常汇总，且不刷「未做任何检查」
    reps = cl._latest_reports()
    if reps:
        rc, so, se = run_main_safe(cl, [reps[0]])
        ck('被检查' in so and '不是通过' not in so, '对照组：真报告 → 正常汇总（rc=%s）' % rc)
        rc, so, se = run_main_safe(cl, [reps[0], miss_a])
        ck('[WARN]' in se and '未被检查' in se, '部分缺失 → [WARN] 点名未被检查的候选')
        ck(rc in (1, 2), '部分缺失 → rc 不为 0（缺证据就不能报全绿，rc=%s）' % rc)
    else:
        ck(False, '对照组：outputs 下应有报告可查（找不到就无法验证不误伤）')

    # ---- §7b 变异自证：把 main() 尾部整段还原成旧写法，旧行为必须复活 ----
    # 注意：必须删掉**两处**新增判定（空检查集守卫 + 部分缺失警告），
    # 只删前者会留下 `if missing:` 分支 → 变异体拿到 rc=2，判据不翻转、自证无效。
    mut = copy_with_deps('check_layout.py', box3)
    msrc = io.open(mut, encoding='utf-8').read()
    old_tail = ("    print('汇总：%d 份，ERROR %d，WARN %d，INFO %d'"
                " % (len(files), n_err, n_warn, n_info))\n"
                "    sys.exit(1 if n_err else (2 if n_warn else 0))\n")
    pat = re.compile(r'    # 空检查集必须.*?'
                     r'    sys\.exit\(1 if n_err else \(2 if n_warn else 0\)\)\n', re.S)
    mnew, nsub = pat.subn(old_tail, msrc)
    ck(nsub == 1, '变异自证·前置：定位到新增的两处判定（匹配 %d 次）' % nsub)
    ck('if checked == 0:' not in mnew and '\n    if missing:\n' not in mnew,
       '变异自证·变异已应用：两处新增判定都已移除（否则判据不会翻转）')
    with io.open(mut, 'w', encoding='utf-8') as f:
        f.write(mnew)
    rc, blob = run_script(mut, argv=[miss_a, miss_b])
    ck(rc == 0 and '[FAIL]' not in blob,
       '变异自证·判定翻转：还原旧写法后「零份被检查」报 rc=0 假绿（rc=%s）' % rc)
finally:
    shutil.rmtree(box3, ignore_errors=True)


# ==================================================== 8. analyze_000001_multi
print('\n8) analyze_000001_multi.py · 行情不足要「有意报错」，不许产废数据包/崩栈')
# 病灶：main() 无返回值（永远退 0）；取数失败 → traceback；数据不足 55 根 →
# ma.iloc[-1] 是 NaN（打印一片 nan、JSON 里写裸 NaN）或 0 根时直接 IndexError。
# 三种都让「生成成功」与「生成了一份废数据包」不可区分。全部 stub 掉取数，不联网。
am = load('analyze_000001_multi')
saved_am = (am.fetch_day, am.fetch_mk)
box4 = tempfile.mkdtemp(prefix='tde_multi_')
try:
    def _raise(*a, **k):
        raise RuntimeError('网络断')

    # A. 取数抛异常 → 有意报错（rc=1 + [FAIL] + 不崩栈 + 不写数据包）
    am.fetch_day = _raise
    am.fetch_mk = _raise
    out_pack = os.path.join(box4, 'pack.json')
    rc, so, se = run_main_safe(am, ['--out', out_pack])
    ck(rc == 1, '取数失败 → rc=1（旧行为：traceback 崩栈，rc 也是 1 但无诊断，rc=%s）' % rc)
    ck('[FAIL]' in se and '行情取不到' in se, '[FAIL] 说清是取数失败')
    ck('网络断' in se, '诊断带出具体原因（RuntimeError 的网络断）')
    ck('Traceback' not in (so + se), '不崩栈 —— 崩栈不是失败路径')
    ck(not os.path.exists(out_pack), '失败时不产出数据包（旧行为会写出一份「成功」样子的包）')

    # B. 取到 0 根 → 数据不足守卫（旧行为：analyze 里 ma.iloc[-1] 直接 IndexError 崩栈）
    am.fetch_day = lambda *a, **k: []
    am.fetch_mk = lambda *a, **k: []
    rc, so, se = run_main_safe(am, ['--out', out_pack])
    ck(rc == 1, '0 根 → rc=1（不再是 IndexError 崩栈，rc=%s）' % rc)
    ck('[FAIL]' in se and '数据不足' in se, '明说数据不足（MA55 需 ≥60 根）')
    ck('Traceback' not in (so + se), '0 根不崩栈')
    ck(not os.path.exists(out_pack), '0 根时不产出数据包')

    # C. --out 参数守卫：给了旗标不给路径要说清楚
    rc, so, se = run_main_safe(am, ['--out'])
    ck(rc == 1 and '[FAIL]' in se, '--out 缺参数 → rc=1 + [FAIL]（不是默默写默认路径）')

    # D. 契约：默认路径与 --out 解析都在（防止日后把重定向删掉）
    src_am = code_only(io.open(os.path.join(HERE, 'analyze_000001_multi.py'),
                               encoding='utf-8').read())
    ck("'--out' in sys.argv" in src_am, '保留 --out 可重定向（冒烟靠它不写真实 outputs/）')
    ck('sys.exit(main())' in src_am, '__main__ 把 main() 的返回码传给上游')
    ck("return 0" in src_am and "return 1" in src_am, 'main() 有 0/1 失败退出码语义')
finally:
    am.fetch_day, am.fetch_mk = saved_am
    shutil.rmtree(box4, ignore_errors=True)


# ==================================================== 9. anonymize_report
print('\n9) anonymize_report.py · 缺输入不崩栈 / 脱敏失败必须红（不许只 print）')
# 病灶（2026-09-23 冒烟首次抓到 —— 抓它的是本轮新加的「崩栈即失败」硬判据）：
#   · 裸 io.open(SRC)：当天报告没生成 → FileNotFoundError 崩栈，rc=1 与「有意报错」同形；
#   · 残留检查只做成一句 print —— 真名没被替换掉照样退 0、照样写出「匿名版」。
# 判据要用**子进程**跑（与冒烟同口径）：脚本的入口语义在 __main__ 里，
# 且缺输入那条路径正是「解释器里跑起来」才知道会不会崩栈。
_TJ = 'T' + '&' + 'J'   # 拆开拼接：本文件若出现连续的星球③原名，display-name 守卫（G3）会当泄漏命中
box5 = tempfile.mkdtemp(prefix='tde_anon_')
try:
    ANON = os.path.join(HERE, 'anonymize_report.py')

    # A. 缺输入：有意报错 + 不崩栈 + **不产出半成品**
    dst_miss = os.path.join(box5, 'must_not_exist.md')
    rc, blob = run_script(ANON, argv=['--src', os.path.join(box5, 'nosuch.md'),
                                      '--out', dst_miss])
    ck(rc == 1, 'A 缺输入 → rc=1（rc=%s）' % rc)
    ck('[FAIL]' in blob and '找不到待匿名化报告' in blob, 'A 有 [FAIL] 诊断，且说清缺的是哪份')
    ck('Traceback' not in blob and 'FileNotFoundError' not in blob,
       'A 不崩栈 —— 旧行为就是一行 FileNotFoundError traceback（rc 同样是 1，无从分辨）')
    ck(not os.path.exists(dst_miss), 'A 失败时不产出半成品（不写匿名版）')

    # B. 控制组：输入干净 → 绿，且**正文段**零真名、受保护路径逐字保留
    src_ok = os.path.join(box5, 'ok.md')
    with io.open(src_ok, 'w', encoding='utf-8') as f:
        f.write('# 知识星球晨报\n\n## 卫斯李的投研笔记\n'
                '- 大鹏鸟 转述：流沙河 减仓；' + _TJ + ' 与 180K Research 同向，'
                'AI 产业链 走强\n\n'
                '延伸：`outputs/知识星球晨报_2026-09-23.md`\n')
    dst_ok = os.path.join(box5, 'ok_out.md')
    rc, blob = run_script(ANON, argv=['--src', src_ok, '--out', dst_ok])
    full = (io.open(dst_ok, encoding='utf-8').read() if os.path.exists(dst_ok) else '')
    body = full.split('## 附：匿名代号解密表')[0]
    leaks = [n for n in ('卫斯李', '大鹏鸟', '流沙河', _TJ, '180K Research',
                         '基业长青+', 'AI 产业链地图', '短评&信息', '好运哥',
                         '浑水调研', 'xxpq') if n in body]
    ck(rc == 0 and full, 'B 干净输入 → rc=0 且产物已写出（rc=%s）' % rc)
    ck(not leaks, 'B 正文段零真名残留（残留=%s）' % ('、'.join(leaks) or '无'))
    ck('`outputs/知识星球晨报_2026-09-23.md`' in full,
       'B 受保护的文件路径逐字保留（改了文件名，报告里的链接就断）')
    ck('匿名代号解密表' in full, 'B 文末解密表仍在（它**刻意含真名**，不参与残留判定）')

    # C. 正文残留这条闸门：**靠变异自证**才验得动
    #    当前映射表把 RESIDUAL_NAMES 全覆盖 → 正确的脚本上残留永远不会非空
    #    （这正是它作为后置断言的价值）。要验证闸门会拦，只能故意删一条映射。
    src_leak = os.path.join(box5, 'leak.md')
    with io.open(src_leak, 'w', encoding='utf-8') as f:
        f.write('正文：浑水调研 认为市场在筑底。\n')

    dst_c = os.path.join(box5, 'leak_ctl.md')
    rc_c, _ = run_script(ANON, argv=['--src', src_leak, '--out', dst_c])
    ck(rc_c == 0 and os.path.exists(dst_c),
       'C·控制组：映射覆盖它时同一输入 rc=0（否则「M1 红了」不能归因于闸门，rc=%s）' % rc_c)

    MUT_MAP = '    ("浑水调研", "知识库B"),\n'
    osrc = io.open(ANON, encoding='utf-8').read()
    ck(osrc.count(MUT_MAP) == 1,
       'C·变异自证·前置：映射靶点存在且唯一（找到 %d 处）' % osrc.count(MUT_MAP))
    m1 = osrc.replace(MUT_MAP, '')
    ck(MUT_MAP not in m1 and len(m1) < len(osrc),
       'C·变异自证·M1 已应用：删掉 1 条映射，长度 %d → %d' % (len(osrc), len(m1)))
    p1 = os.path.join(box5, 'm1.py')
    with io.open(p1, 'w', encoding='utf-8') as f:
        f.write(m1)
    dst1 = os.path.join(box5, 'm1_out.md')
    rc1, blob1 = run_script(p1, argv=['--src', src_leak, '--out', dst1])
    ck(rc1 == 1, 'C 覆盖缺口 → rc=1（旧行为 rc=0 假绿，rc=%s）' % rc1)
    ck('[FAIL]' in blob1 and '匿名化未完成' in blob1, 'C 诊断说清是「真名残留」，不是无声失败')
    ck('Traceback' not in blob1, 'C 不崩栈')
    ck(not os.path.exists(dst1), 'C 有残留时不产出匿名版（免得带真名的半成品被当成品交付）')

    # M2 = M1 + 把残留判定整段删掉（还原旧写法）→ 同一输入必须翻回假绿。
    # 两段变异体只差这一个判定，于是「rc=1 / 不产出」唯一地归因于该判定。
    pat_in = re.compile(r'    if in_body:\n(?:.*\n)*?        return 1\n')
    m2, n2 = pat_in.subn('', m1)
    ck(n2 == 1, 'C·变异自证·M2 前置：定位到残留判定整段（匹配 %d 次）' % n2)
    ck('if in_body:' not in m2, 'C·变异自证·M2 已应用：残留判定已整段移除')
    p2 = os.path.join(box5, 'm2.py')
    with io.open(p2, 'w', encoding='utf-8') as f:
        f.write(m2)
    dst2 = os.path.join(box5, 'm2_out.md')
    rc2, blob2 = run_script(p2, argv=['--src', src_leak, '--out', dst2])
    ck(rc2 == 0 and os.path.exists(dst2),
       'C·变异自证·判据翻转：还原「只 print 不判定」后同一输入 rc=0 且写出产物（rc=%s 产物=%s）'
       % (rc2, os.path.exists(dst2)))
    ck('匿名化未完成' not in blob2, 'C·变异自证：旧写法连一句诊断都没有 —— 这正是本次要修的病灶')

    # D. 真名只落在受保护路径里 → 退 2（写产物，但明确降级，让人看见）
    src_p = os.path.join(box5, 'path.md')
    with io.open(src_p, 'w', encoding='utf-8') as f:
        f.write('正文：星球② 观点\n\n延伸：`outputs/' + _TJ + '_原始记录.md`\n')
    dst_p = os.path.join(box5, 'path_out.md')
    rc_p, blob_p = run_script(ANON, argv=['--src', src_p, '--out', dst_p])
    ck(rc_p == 2, 'D 真名只在受保护路径里 → rc=2（rc=%s）' % rc_p)
    ck('[WARN]' in blob_p and '受保护的文件路径' in blob_p, 'D 说清「仅路径命中」并提示人工确认')
    ck(os.path.exists(dst_p), 'D 该情形仍写产物 —— 路径要逐字保留，属需人工判断而非直接拦')

    # E. 参数守卫：写错参数要报「参数错」，不是伪装成「文件不存在」
    for argv, why in ((['--out'], '--out 无值'), (['--foo'], '不认识的参数'),
                      (['2026/08/21'], '日期格式错')):
        rc_e, blob_e = run_script(ANON, argv=argv)
        ck(rc_e == 1 and '[FAIL]' in blob_e and 'Traceback' not in blob_e,
           'E %s → rc=1 + [FAIL] 且不崩栈（rc=%s）' % (why, rc_e))
    rc_h, blob_h = run_script(ANON, argv=['-h'])
    ck(rc_h == 0 and '用法' in blob_h, 'E -h 打印用法并退 0（rc=%s）' % rc_h)

    # F. 写不出去（--out 指向一个目录）也是有意报错：旧行为是 PermissionError 崩栈
    src_ok2 = os.path.join(box5, 'ok2.md')
    with io.open(src_ok2, 'w', encoding='utf-8') as f:
        f.write('正文：无真名。\n')
    rc_f, blob_f = run_script(ANON, argv=['--src', src_ok2, '--out', box5])
    ck(rc_f == 1 and '[FAIL]' in blob_f and 'Traceback' not in blob_f,
       'F 输出写不了 → rc=1 + [FAIL]，不是 PermissionError 崩栈（rc=%s）' % rc_f)

    # G. 契约：防止日后把新增的判定/入口悄悄删回去
    src_anon = code_only(osrc)
    ck('sys.exit(main())' in src_anon,
       '契约：__main__ 把 main() 返回码传上游（旧版没有入口，永远退 0）')
    ck("'--src'" in src_anon and "'--out'" in src_anon,
       '契约：保留 --src/--out（冒烟靠它不往真实 outputs/ 落产物）')
    ck('remaining if remaining else' not in src_anon,
       '契约：旧的「只 print 残留」写法已消失（判定不得被降级回 print）')
    # 用**块结构**断言（pat_in = `if in_body:` … `return 1`），不用「距离 N 字符」——
    # 距离窗口对块内文案长度敏感：这里改一句诊断文案就可能把断言的边界顶穿（本轮实测过）。
    ck(pat_in.search(src_anon) is not None,
       '契约：残留判定块内含失败退出码（判定必须影响退出码，不得降级成 print）')
finally:
    shutil.rmtree(box5, ignore_errors=True)


print()
print('RESULT: %s' % ('ALL PASS' if not fails else 'FAIL %d 项' % len(fails)))
sys.exit(1 if fails else 0)