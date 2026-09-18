# -*- coding: utf-8 -*-
"""报告版面体检器：检查一份作战报告是否缺块 / 错位 / 附录 A·B 语义对调 / 偏差期数过时。

检查项：
  1. 缺块（ERROR=required 缺失 / WARN=optional 缺失）
  2. 顺序错位（WARN）：区块出现顺序与规范不符
  3. 附录 A·B 语义（WARN）：A 应为「抓取通道」、B 应为「星球代号」，若对调则提示
  4. 偏差期数一致性（**仅当日报告**判 WARN，历史报告降为 INFO）：
     报告标注期数 vs forecast_chain.json verified 条数
  5. 块内子内容（ERROR/WARN）：如信息判断块须含「共同观点/相反观点」、预判块须内嵌走势图
  6. 排版重复（WARN，仅当日报告）：信息原子全篇复述超限 / 字段表与关键位表双写
     —— 规则见 layout_spec.DUP_RULES，对应《规范_v2》「信息原子唯一落地」
  7. 篇幅超限（WARN，仅当日报告）：核心速览/第一块/一句话预判/剧本触发条件/纪律节数
     —— 规则见 layout_spec.LENGTH_RULES，对应《规范_v2》3.8
  8. 本期变化·基期对账（ERROR，仅当日报告）：见 `_period_change_check` 说明

「仅当日报告」的口径：这三项对历史报告是快照差异（链每天前进、规范逐步收紧），
判定它们"不达标"没有意义，只会让「0 WARN」这道闸门永久失效。历史报告一律降为 INFO。

用法：
    $PY check_layout.py [报告.md ...]
    不传参数：自动扫描 outputs/ 下最新 4 档报告（晨/午/盘/复）。

退出码：0=通过，1=有 ERROR，2=仅 WARN（INFO 不影响退出码）。
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
    """抓取 H2~H4 标题，返回 [(行号, 层级, 标题文本)]，层级=# 个数（2/3/4）。"""
    out = []
    for i, line in enumerate(text.split('\n')):
        m = re.match(r'^(#{2,4})\s+(.+?)\s*$', line)
        if m:
            out.append((i + 1, len(m.group(1)), m.group(2)))
    return out


def find_block(headings, key):
    """在标题列表中找匹配 key 的块标题，返回 (行号, 标题) 或 (None, None)。

    优先匹配 H2（块标题层级），避免 H3 子标题（如「变盘概率预判」「本期预判」）
    抢在真正的块标题（如「## 五、第四块 · 预判」）之前被误命中。
    无 H2 命中时 fallback 到 H3/H4（兼容「偏差观察统计表」等有时写成 H3 的块）。
    """
    for p in spec.BLOCKS[key][1]:
        for lineno, level, title in headings:
            if level == 2 and re.search(p, title):
                return lineno, title
    for p in spec.BLOCKS[key][1]:
        for lineno, level, title in headings:
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


def _report_date(path):
    m = re.search(r'(\d{4}-\d{2}-\d{2})', os.path.basename(path))
    return m.group(1) if m else None


def _is_today_report(path):
    d = _report_date(path)
    if not d:
        return False
    import datetime
    return d == datetime.datetime.now().strftime('%Y-%m-%d')


def _superseded_same_date(path):
    """当日是否已存在生成更晚的同日期报告？

    用于「偏差期数一致性」判定：晨报 08:55 写入时链为 48 期，收盘档 17:05 复盘后
    链前进到 49 期 —— 此时晨报的「48 期」是对的（它是当时的快照），却会被判 WARN，
    使「0 WARN」这道闸门在每天跑完收盘档后永久失效（2026-09-17 第二次遇到同类噪声）。
    口径：只有**当日最新生成的那一份**才需与链一致，被同日更晚报告取代者降为 INFO。
    """
    d = _report_date(path)
    if not d:
        return False
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return False
    out = os.path.join(ROOT, 'outputs')
    for f in glob.glob(os.path.join(out, '作战报告_*.md')):
        if os.path.abspath(f) == os.path.abspath(path):
            continue
        if d not in os.path.basename(f):
            continue
        try:
            if os.path.getmtime(f) > mt:
                return True
        except OSError:
            continue
    return False


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
                msg = '块内缺子内容：%s 内缺「%s」' % (spec.BLOCKS[key][0], sub_name)
                # 走势图缺失：仅当日报告算 ERROR（硬约束），历史报告快照降级 WARN
                if sub_name == '走势图' and not _is_today_report(res['path']):
                    res['warns'].append(msg + '（历史报告快照，可选回补）')
                else:
                    res['errors'].append(msg)


def _dup_check(text, res):
    """第 6 类检查：排版重复（信息原子唯一落地）。

    规则见 layout_spec.DUP_RULES。仅对「当日报告」执行 —— 历史报告是快照，
    重复检查无意义且会让「0 WARN」这道闸门永久失效。
    """
    rules = getattr(spec, 'DUP_RULES', None)
    if not rules:
        return
    if not _is_today_report(res['path']):
        return

    lines = text.split('\n')

    # --- 价格关键位 / 结论短语 / 事件说明：全篇计数
    for key in ('price', 'phrase', 'event'):
        rule = rules.get(key)
        if not rule:
            continue
        max_n = rule.get('max', 8)
        hits = {}
        if 'pattern' in rule:
            rx = re.compile(rule['pattern'])
            for i, ln in enumerate(lines, 1):
                for m in rx.findall(ln):
                    hits.setdefault(m, []).append(i)
        else:
            for ph in rule.get('phrases', []):
                ls = [i for i, ln in enumerate(lines, 1) if ph in ln]
                if ls:
                    hits[ph] = ls
        over = {k: v for k, v in hits.items() if len(v) > max_n}
        if over:
            top = sorted(over.items(), key=lambda x: -len(x[1]))[:4]
            detail = '；'.join('%s×%d（行 %s）' % (
                k, len(v), ','.join(str(x) for x in v[:10]) + ('…' if len(v) > 10 else ''))
                for k, v in top)
            res['warns'].append(
                '排版重复·%s 超限（阈值 %d）：%s。%s'
                % (rule['label'], max_n, detail, rule.get('hint', '')))

    # --- 结构性双写：字段表 ↔ 关键位表
    st = rules.get('structural')
    if st:
        has_field = bool(re.search(st['field_row'], text))
        has_level = bool(re.search(st['level_section'], text))
        if has_field and has_level:
            res['warns'].append('排版重复·%s：%s' % (st['label'], st.get('hint', '')))


def _nz(s):
    """去空白后的字符数 —— 长度约束的统一计数口径（中文按 1 计）"""
    return len(re.sub(r'\s', '', s))


# ---------------------------------------------------------------- 第 8 类：基期对账

DIM_LABEL = {'方向': 'direction', '区间': 'range', '支撑': 'support', '压力': 'resistance'}


def _parse_bias_table(text):
    """解析报告里的偏差统计表 → {dim: 纯命中率%}"""
    out = {}
    for ln in text.split('\n'):
        if not ln.strip().startswith('|'):
            continue
        cells = [c.strip() for c in ln.strip().strip('|').split('|')]
        if len(cells) < 6:
            continue
        dim = DIM_LABEL.get(cells[0])
        if not dim:
            continue
        for c in cells[1:]:
            m = re.fullmatch(r'\*{0,2}([\d.]+)%\*{0,2}', c)
            if m:
                out[dim] = float(m.group(1))
                break
    return out


def _mentioned_ids(line, path):
    """从「本期变化」行里反引号标注的样本名还原链记录 id（`9/17-close` → 2026-09-17-close）"""
    year = (_report_date(path) or '')[:4]
    ids = set()
    for tok in re.findall(r'`([^`]+)`', line):
        tok = tok.strip()
        m = re.fullmatch(r'(\d{4})-(\d{1,2})-(\d{1,2})-(.+)', tok)
        if m:
            ids.add('%s-%02d-%02d-%s' % (m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)))
            continue
        m = re.fullmatch(r'(\d{1,2})/(\d{1,2})-(.+)', tok)
        if m and year:
            ids.add('%s-%02d-%02d-%s' % (year, int(m.group(1)), int(m.group(2)), m.group(3)))
    return ids


def _period_change_check(text, res):
    """第 8 类检查：本期变化·基期对账（ERROR，仅当日报告）。

    为什么要有这一类（2026-09-18 审计 P0-1）
    ---------------------------------------
    9/18 晨报的「本期变化」把方向的基期写成了**上上期**：标 `56.2%→56.0%`，
    而 56.2% 是 9/17 **晨报**（n=48）的值，真正的基期应是 9/17 **收盘**档的
    n=49 → 57.1%。同一句话里区间的基期（36.7%，n=49）却是对的 —— **同句两套基期**，
    读者（包括复核的人）无从发现，因为两个数看起来都"像真的"。

    这类手写数字错其实**机器完全能查**，两条独立判据：
      1) 「本期值」必须等于报告自己那张偏差统计表的值（表是程序算的）；
      2) 「基期值」必须等于「当前链去掉本期新增样本」的实测值。
    只要有一条对不上就报 ERROR —— 错的是叙述层，而叙述层恰恰没有任何机器检查。
    """
    if not _is_today_report(res['path']) or _superseded_same_date(res['path']):
        return
    hit = [ln for ln in text.split('\n') if '本期变化' in ln]
    if not hit:
        res['infos'].append('本期变化：报告未写「本期变化」段，跳过基期对账')
        return
    line = hit[0]

    m = re.search(r'样本\s*(\d+)\s*→\s*(\d+)\s*期', line)
    if not m:
        res['infos'].append('本期变化：未找到「样本 A→B 期」声明，跳过基期对账')
        return
    before_n, after_n = int(m.group(1)), int(m.group(2))
    ids = _mentioned_ids(line, res['path'])

    try:
        sys.path.insert(0, HERE)
        import chainlib
        cur = chainlib.bias_stats('forecast')
        prev = chainlib.bias_stats('forecast', exclude_ids=ids) if ids else None
    except Exception as e:                                   # noqa: BLE001
        res['infos'].append('本期变化：读链失败（%s），跳过基期对账' % e)
        return

    # 一致性前置：报告写的期数必须与链对得上，否则是快照差异，不该判 ERROR
    if cur.get('periods') != after_n:
        res['infos'].append('本期变化：报告称样本 %d 期、链上 verified %d 期（快照差异），跳过基期对账'
                            % (after_n, cur.get('periods')))
        return
    if prev is None or prev.get('periods') != before_n:
        res['infos'].append(
            '本期变化：无法由链反推基期样本（报称 %d 期；按 `%s` 排除后为 %s 期），跳过基期对账'
            % (before_n, '`、`'.join(sorted(ids)) or '（未识别到新增样本 id）',
               prev.get('periods') if prev else '?'))
        return

    table = _parse_bias_table(text)
    checked = 0
    for seg in line.split('；'):
        labels = [k for k in DIM_LABEL if k in seg]
        if len(labels) != 1:
            continue          # 「支撑/压力」这类合并段落无法归维，跳过
        cn = labels[0]
        dim = DIM_LABEL[cn]
        mm = re.search(r'（\s*([\d.]+)\s*%\s*→\s*\*{0,2}\s*([\d.]+)\s*%', seg)
        if not mm:
            continue          # 「纯命中率不变（65.3% / 59.2%）」这类无箭头，跳过
        base, now = float(mm.group(1)), float(mm.group(2))
        c = (cur.get('dims') or {}).get(dim) or {}
        if c.get('pure') is None:
            continue
        checked += 1
        if abs(now - c['pure']) > 0.05:
            res['errors'].append('本期变化·%s 本期值 %.1f%% 与链实测 %.1f%% 不符'
                                 % (cn, now, c['pure']))
        t = table.get(dim)
        if t is not None and abs(t - c['pure']) > 0.05:
            res['errors'].append('偏差统计表·%s 纯命中率 %.1f%% 与链实测 %.1f%% 不符'
                                 % (cn, t, c['pure']))
        p = (prev.get('dims') or {}).get(dim, {}).get('pure')
        if p is not None and abs(base - p) > 0.05:
            res['errors'].append(
                '本期变化·%s 基期 %.1f%% 与上一期实测 %.1f%% 不符 —— 疑似基期取错期数'
                '（上一期 = 当前链去掉 `%s`）' % (cn, base, p, '`、`'.join(sorted(ids))))
    if checked:
        res['infos'].append('本期变化·基期对账：已核对 %d 个维度（本期值 + 基期值）' % checked)


def _length_check(text, res):
    """第 7 类检查：篇幅长度约束（《规范_v2》3.8）。

    规则见 layout_spec.LENGTH_RULES。仅对「当日报告」执行（与 DUP_RULES 同口径）。

    为什么要有这一类：3.8 自 2026-09-16 写进规范，但一直没有任何机器检查，
    于是 9/16 报告（核心速览 195/224/108 字、第一块 8,492 字）全部超限却「通过」，
    9/17 首版同样超限 —— 正是 DUP_RULES 当初被补上时的同一个缺口。
    """
    rules = getattr(spec, 'LENGTH_RULES', None)
    if not rules or not _is_today_report(res['path']):
        return
    lines = text.split('\n')

    def _bounds(pat, level=r'^##\s'):
        """定位 pattern 匹配行 → 返回 (start, end)，end 为下一个二级标题之前。"""
        start = None
        for i, l in enumerate(lines):
            if re.match(pat, l):
                start = i
                break
        if start is None:
            return None
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if re.match(level, lines[j]):
                end = j
                break
        return start, end

    for rule in rules.values():
        unit = rule.get('unit')
        over = []                       # [(定位, 实测值)]
        limit = rule.get('max', 0)

        if unit == 'section_lines':
            b = _bounds(rule['section'])
            if not b:
                continue
            for i in range(b[0] + 1, b[1]):
                ln = lines[i]
                if not ln.strip() or ln.startswith('---'):
                    continue
                if _nz(ln) > limit:
                    over.append(('L%d' % (i + 1), _nz(ln)))

        elif unit == 'section_block':
            b = _bounds(rule['section'])
            if not b:
                continue
            n = _nz('\n'.join(lines[b[0]:b[1]]))
            if n > limit:
                over.append(('整块', n))

        elif unit == 'after_heading':
            b = _bounds(rule['heading'])
            if not b:
                continue
            for i in range(b[0] + 1, b[1]):
                if lines[i].strip():
                    if _nz(lines[i]) > limit:
                        over.append(('L%d' % (i + 1), _nz(lines[i])))
                    break

        elif unit == 'table_col':
            for i, ln in enumerate(lines, 1):
                if not re.match(rule['row'], ln):
                    continue
                cells = ln.split('|')
                ci = rule['col']
                if ci < len(cells) and _nz(cells[ci]) > limit:
                    over.append(('L%d' % i, _nz(cells[ci])))

        elif unit == 'heading_count':
            b = _bounds(rule['section'])
            if not b:
                continue
            hits = [j + 1 for j in range(b[0] + 1, b[1])
                    if re.match(rule['heading'], lines[j])]
            if len(hits) > limit:
                over.append(('共 %d 处（行 %s）' % (len(hits), ','.join(map(str, hits))),
                             len(hits)))

        if over:
            detail = '；'.join('%s=%d' % (w, v) for w, v in over[:6])
            res['warns'].append('篇幅超限·%s（上限 %d）：%s。%s'
                                % (rule['label'], limit, detail, rule.get('hint', '')))


def check(path):
    tier = detect_tier(os.path.basename(path))
    res = {'path': path, 'tier': tier, 'errors': [], 'warns': [], 'infos': []}
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
    #    仅「当日报告」判 WARN：历史报告是当时快照，链每天 +1，它必然"过时"——
    #    原先对历史报告也报 WARN，导致每次扫描都把退出码拉到 2，
    #    连 3 份零问题报告也一起背锅，「0 WARN」这道闸门实际永久失效（2026-09-17 修正）。
    if 'bias' in pos:
        m = re.search(r'[（(](\d+)\s*期', text)
        report_n = int(m.group(1)) if m else None
        chain_n = _verified_count()
        if report_n is not None and chain_n is not None and report_n != chain_n:
            msg = ('偏差期数：报告标 %d 期，链当前 %d 期' % (report_n, chain_n))
            if _is_today_report(res['path']) and not _superseded_same_date(res['path']):
                res['warns'].append(msg + '（当日报告需与链一致）')
            else:
                res['infos'].append(msg + '（快照：写于链前进之前，属正常）')

    # 5) 块内部子内容校验（防止「块标题在、内部核心子内容缺失」）
    _sub_required_check(text, pos, res)

    # 6) 排版重复检查（信息原子唯一落地，2026-09-16 维护新增）
    _dup_check(text, res)

    # 7) 篇幅长度约束（规范_v2 3.8，2026-09-17 维护新增）
    _length_check(text, res)

    # 8) 本期变化·基期对账（手写数字 vs 链实测，2026-09-18 审计 P0-1 新增）
    _period_change_check(text, res)

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
    # INFO 只提供上下文，不影响退出码（历史报告快照类差异都归这里）
    for i in res.get('infos', []):
        L.append('  [INFO ] %s' % i)
    return '\n'.join(L)


def _latest_reports():
    """默认扫描：每个档位取最新一份。

    2026-09-17 修正：原列表为 ['晨报','午间','盘中','复盘'] —— **漏了「收盘」**，
    于是收盘档报告在不传参数时根本不进闸门（收盘一旦出错，默认检查看不见）。
    现按 TIER_ALIAS 的档位全量取，并按 tier 去重（避免「收盘复盘」这类命名同时命中两词）。
    """
    out = os.path.join(ROOT, 'outputs')
    files, seen = [], set()
    for kw in spec.TIER_ALIAS:
        g = glob.glob(os.path.join(out, '作战报告_%s_*.md' % kw))
        if not g:
            continue
        f = sorted(g)[-1]
        t = detect_tier(os.path.basename(f))
        if t in seen:
            continue
        seen.add(t)
        files.append(f)
    return files


def main():
    files = sys.argv[1:]
    if not files:
        files = _latest_reports()
    n_err = n_warn = n_info = 0
    for f in files:
        if not os.path.exists(f):
            print('跳过（不存在）：%s' % f)
            continue
        res = check(f)
        print(render(res))
        print()
        n_err += len(res['errors'])
        n_warn += len(res['warns'])
        n_info += len(res.get('infos', []))
    print('汇总：%d 份，ERROR %d，WARN %d，INFO %d' % (len(files), n_err, n_warn, n_info))
    sys.exit(1 if n_err else (2 if n_warn else 0))


if __name__ == '__main__':
    main()
