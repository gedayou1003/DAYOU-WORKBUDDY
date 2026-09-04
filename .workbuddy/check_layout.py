# -*- coding: utf-8 -*-
"""报告版面体检器：检查一份作战报告是否缺块 / 错位 / 附录 A·B 语义对调 / 偏差期数过时。

检查项：
  1. 缺块（ERROR=required 缺失 / WARN=optional 缺失）
  2. 顺序错位（WARN）：区块出现顺序与规范不符
  3. 附录 A·B 语义（WARN）：A 应为「抓取通道」、B 应为「星球代号」，若对调则提示
  4. 偏差期数一致性（WARN）：报告标注期数 vs forecast_chain.json verified 条数

用法：
    $PY check_layout.py [报告.md ...]
    不传参数：自动扫描 outputs/ 下最新 4 档报告（晨/午/盘/复）。

退出码：0=通过，1=有 ERROR，2=仅 WARN。
"""
import os, re, sys, json, glob

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import layout_spec as spec

FORECAST = os.path.join(HERE, 'forecast_chain.json')


def detect_tier(filename):
    for kw, tier in spec.TIER_ALIAS.items():
        if kw in filename:
            return tier
    return None


def extract_headings(text):
    """抓取 H2~H4 标题，返回 [(行号, 标题文本)]。"""
    out = []
    for i, line in enumerate(text.split('\n')):
        m = re.match(r'^(#{2,4})\s+(.+?)\s*$', line)
        if m:
            out.append((i + 1, m.group(2)))
    return out


def find_block(headings, key):
    """在标题列表中找第一个匹配 key 的标题，返回 (行号, 标题) 或 (None, None)。"""
    for p in spec.BLOCKS[key][1]:
        for lineno, title in headings:
            if re.search(p, title):
                return lineno, title
    return None, None


def _block_body(text, lineno):
    """取标题行之后到下一个 H2（或 15 行）之间的正文。"""
    lines = text.split('\n')
    out = []
    for l in lines[lineno: lineno + 15]:
        if re.match(r'^##\s', l):
            break
        out.append(l)
    return '\n'.join(out)


def _appendix_role(title, body):
    """判断附录实际承载的角色：'通道' / '代号' / '未知'。"""
    blob = (title or '') + '\n' + body
    has_chan = bool(re.search(r'通道|抓取|Cookie|Skill|窗口', blob))
    has_code = bool(re.search(r'代号|星球名', blob))
    if has_chan and not has_code:
        return '通道'
    if has_code and not has_chan:
        return '代号'
    return '未知'


def _verified_count():
    if not os.path.exists(FORECAST):
        return None
    try:
        d = json.load(open(FORECAST, encoding='utf-8'))
        return sum(1 for r in d if r.get('status') == 'verified')
    except Exception:
        return None


def _sub_required_check(text, pos, res):
    """块内部子内容校验：某些块除标题外，内部还必须含指定子标题（如信息判断块内须有「共同观点」「相反观点」）。"""
    if not getattr(spec, 'SUB_REQUIRED', None):
        return
    lines = text.split('\n')
    for key, subs in spec.SUB_REQUIRED.items():
        if key not in pos:
            continue
        start_idx = pos[key] - 1  # 0-based 标题行索引
        end_idx = len(lines)
        for j in range(start_idx + 1, len(lines)):
            if re.match(r'^##\s', lines[j]):
                end_idx = j
                break
        body = '\n'.join(lines[start_idx:end_idx])
        for sub_name, sub_pats in subs:
            if not any(re.search(p, body) for p in sub_pats):
                res['errors'].append(
                    '块内缺子内容：%s 内缺「%s」' % (spec.BLOCKS[key][0], sub_name))


def check(path):
    tier = detect_tier(os.path.basename(path))
    res = {'path': path, 'tier': tier, 'errors': [], 'warns': []}
    if tier is None:
        res['errors'].append('无法从文件名识别档位（需含 晨报/午间/盘中/收盘/复盘）')
        return res
    if tier not in spec.SLOTS:
        res['errors'].append('档位 %s 未在 layout_spec.SLOTS 中定义' % tier)
        return res

    text = open(path, encoding='utf-8').read()
    headings = extract_headings(text)
    slots = spec.SLOTS[tier]

    # 1) 缺块
    pos = {}  # key -> lineno
    for key in slots['required']:
        ln, title = find_block(headings, key)
        if ln is None:
            res['errors'].append('缺块（required）：%s（%s）' % (spec.BLOCKS[key][0], key))
        else:
            pos[key] = ln
    for key in slots['optional']:
        ln, title = find_block(headings, key)
        if ln is None:
            res['warns'].append('缺块（optional）：%s（%s）' % (spec.BLOCKS[key][0], key))
        else:
            pos[key] = ln

    # 2) 顺序错位（只对出现的块，按规范顺序检查单调递增）
    order = spec.slot_order(tier)
    ordered = [(k, pos[k]) for k in order if k in pos]
    for i in range(1, len(ordered)):
        k_prev, ln_prev = ordered[i - 1]
        k_cur, ln_cur = ordered[i]
        if ln_cur < ln_prev:
            res['warns'].append(
                '顺序错位：%s(L%d) 出现在 %s(L%d) 之前'
                % (spec.BLOCKS[k_cur][0], ln_cur, spec.BLOCKS[k_prev][0], ln_prev))

    # 3) 附录 A·B 语义
    if 'appendix_a' in pos:
        ln, title = find_block(headings, 'appendix_a')
        role = _appendix_role(title, _block_body(text, ln))
        if role == '代号':
            res['warns'].append('附录 A 语义疑似对调：应为「抓取通道」，实际写成了「星球代号」')
    if 'appendix_b' in pos:
        ln, title = find_block(headings, 'appendix_b')
        role = _appendix_role(title, _block_body(text, ln))
        if role == '通道':
            res['warns'].append('附录 B 语义疑似对调：应为「星球代号」，实际写成了「抓取通道」')

    # 4) 偏差期数一致性
    if 'bias' in pos:
        m = re.search(r'[（(](\d+)\s*期', text)
        report_n = int(m.group(1)) if m else None
        chain_n = _verified_count()
        if report_n is not None and chain_n is not None and report_n != chain_n:
            res['warns'].append(
                '偏差期数过时：报告标 %d 期，链当前 %d 期（历史报告为快照属正常，当日报告需核对）'
                % (report_n, chain_n))

    # 5) 块内部子内容校验（防止「块标题在、内部核心子内容缺失」）
    _sub_required_check(text, pos, res)

    return res


def render(res):
    name = os.path.basename(res['path'])
    tier = res['tier'] or '?'
    L = ['===== %s（%s）=====' % (name, tier)]
    if res['errors']:
        for e in res['errors']:
            L.append('  [ERROR] %s' % e)
    if res['warns']:
        for w in res['warns']:
            L.append('  [WARN ] %s' % w)
    if not res['errors'] and not res['warns']:
        L.append('  通过：无缺块 / 无错位 / 无语义问题')
    return '\n'.join(L)


def _latest_reports():
    out = os.path.join(ROOT, 'outputs')
    files = []
    for t in ['晨报', '午间', '盘中', '复盘']:
        g = glob.glob(os.path.join(out, '作战报告_%s_*.md' % t))
        if g:
            files.append(sorted(g)[-1])
    return files


def main():
    files = sys.argv[1:]
    if not files:
        files = _latest_reports()
    n_err = n_warn = 0
    for f in files:
        if not os.path.exists(f):
            print('跳过（不存在）：%s' % f)
            continue
        res = check(f)
        print(render(res))
        print()
        n_err += len(res['errors'])
        n_warn += len(res['warns'])
    print('汇总：%d 份，ERROR %d，WARN %d' % (len(files), n_err, n_warn))
    sys.exit(1 if n_err else (2 if n_warn else 0))


if __name__ == '__main__':
    main()
