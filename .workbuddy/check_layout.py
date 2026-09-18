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
  9. 表格长文本单元格（WARN）：长文本列被挤成竖条 —— 见 layout_spec.TABLE_CELL_RULES
  10. 术语与口径一致性（WARN）：55 线写法混用 / MA20 与 BOLL 中轨并存未注明等价 /
      关键位表出现无属性的行 —— 见 layout_spec.TERM_RULES
  11. 附录 A/B 星球覆盖口径（WARN）：附录 B 列了、附录 A 既不出现也不说「未覆盖」
      —— 见 layout_spec.APPENDIX_COVERAGE

9~11 是 2026-09-18 全链路审计「排版读感」章节（5.1/5.3/5.4）的落地。
它们与本文件既有的检查同属一类：**规则写在文档里、产出与规范之间没有机器拦网** ——
审计报告点出的三处长文本列、55 线两种写法、附录 A 少 3 个星球，全都能机器查，却没人查。

「仅当日报告」的口径：第 4/6/7/8 项对历史报告是快照差异（链每天前进、规范逐步收紧），
判定它们"不达标"没有意义，只会让「0 WARN」这道闸门永久失效。历史报告一律降为 INFO。
第 9~11 项另加**规则生效起点**（`since`）：规则在 t 时刻确立，只约束 t 之后生成的报告，
早于起点的报告**明示**豁免（打印 INFO），不是静默跳过。

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
    skipped_since = []      # 因「生效起点未到」而跳过的短语（末尾聚合成一条 INFO，避免刷屏）

    # --- 价格关键位 / 结论短语 / 事件说明：全篇计数
    for key in ('price', 'phrase', 'event'):
        rule = rules.get(key)
        if not rule:
            continue
        max_n = rule.get('max', 8)
        limits = rule.get('limits') or {}        # 短语专属上限（2026-09-18 审计 5.2 扩容）
        since_map = rule.get('since_map') or {}  # 新增短语的生效起点
        hits = {}
        if 'pattern' in rule:
            rx = re.compile(rule['pattern'])
            for i, ln in enumerate(lines, 1):
                for m in rx.findall(ln):
                    hits.setdefault(m, []).append(i)
        else:
            for ph in rule.get('phrases', []):
                # 新增短语带生效起点：早于起点的报告不参与（打 INFO 明示，不静默跳过）
                since = since_map.get(ph)
                if since and not _rule_exists_yet(since, res['path']):
                    skipped_since.append(ph)
                    continue
                ls = [i for i, ln in enumerate(lines, 1) if ph in ln]
                if ls:
                    hits[ph] = ls
        over = {}
        for k, v in hits.items():
            lim = limits.get(k, max_n)
            if len(v) > lim:
                over[k] = (v, lim)
        if over:
            top = sorted(over.items(), key=lambda x: -len(x[1][0]))[:4]
            detail = '；'.join('%s×%d（上限 %d，行 %s）' % (
                k, len(v), lim, ','.join(str(x) for x in v[:10]) + ('…' if len(v) > 10 else ''))
                for k, (v, lim) in top)
            res['warns'].append(
                '排版重复·%s 超限：%s。%s' % (rule['label'], detail, rule.get('hint', '')))

    # --- 结构性双写：字段表 ↔ 关键位表
    st = rules.get('structural')
    if st:
        has_field = bool(re.search(st['field_row'], text))
        has_level = bool(re.search(st['level_section'], text))
        if has_field and has_level:
            res['warns'].append('排版重复·%s：%s' % (st['label'], st.get('hint', '')))

    if skipped_since:
        res['infos'].append('排版重复：新增结论短语 %s 的阈值自 2026-09-19 起生效，'
                            '本报告早于规则确立，不参与' % '、'.join(skipped_since))


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


# ---------------------------------------------------------------- 第 9~11 类：排版读感（审计 5.1/5.3/5.4）


def _rule_exists_yet(since, path):
    """规则是否已对该报告生效（纯判定，不打 INFO）—— 供需要自己聚合说明的调用方用。"""
    if not since:
        return True
    d = _report_date(path)
    return not (d and d < since)


def _rule_active(since, path, res, label):
    """新增规则的生效起点。

    规则在 t 时刻确立，就只约束 t 之后**生成**的报告。早于起点的报告**明示**豁免：
    打印一条 INFO 说明原因，而不是静默跳过 —— 静默跳过等于把闸门调松了却不说。
    （本项目已有教训：拿新尺子量旧快照，会让「0 WARN」这道闸门当天就永久失效。）

    注意：这里只把豁免**登记**到 res['_exempt']，不在每处直接 append ——
    因为同一份报告会被 5 条新规则各判一次，逐条打印会让每份历史报告刷 5 行 INFO
    （5 份报告 25 行），由 check() 末尾聚合成 1 条「逐一点名」的 INFO。
    """
    if not since:
        return True
    d = _report_date(path)
    if d and d < since:
        res.setdefault('_exempt', []).append((label, since, d))
        return False
    return True


def _parse_tables(text):
    """解析 markdown 表格 → [(表头行号, [表头列], [(数据行行号, [单元格])])]。

    表头 = 以 `|` 开头、且**下一行**是分隔线（`|---|---|`）的那一行。
    数据行 = 紧随其后、仍以 `|` 开头的行。
    """
    lines = text.split('\n')
    out = []
    i = 1
    while i <= len(lines):
        s = lines[i - 1].strip()
        if (s.startswith('|') and i < len(lines)
                and re.match(r'^\|[\s:|\-]+\|?\s*$', lines[i].strip())):
            header = [c.strip() for c in s.strip('|').split('|')]
            rows = []
            j = i + 2
            while j <= len(lines) and lines[j - 1].strip().startswith('|'):
                rows.append((j, [c.strip() for c in lines[j - 1].strip().strip('|').split('|')]))
                j += 1
            out.append((i, header, rows))
            i = j
        else:
            i += 1
    return out


def _cell_text(c):
    """单元格的「读者可见宽度」口径：去掉空白与 markdown 标记（** ` * 等）。"""
    return _nz(re.sub(r'[*`~]', '', c))


def _width_check(text, res):
    """第 9 类检查：表格长文本单元格上限（审计 5.1）。

    实测 9/18 晨报：第二块「上期共识复盘」的「说明」列最长 **202 字/格**，
    第五块「做多/规避榜」的「依据」列 125 字/格 —— 880px 宽的 HTML 里就是一列竖条。

    阈值按列数分层（列越多每列越窄）：≤3 列 120 字 / 4 列 90 字 / ≥5 列 80 字。
    """
    rules = getattr(spec, 'TABLE_CELL_RULES', None)
    if not rules or not _rule_active(rules.get('since'), res['path'], res, rules['label']):
        return
    tiers = rules['by_cols']
    over = []
    for _hline, header, rows in _parse_tables(text):
        ncols = len(header)
        limit = next(l for maxc, l in tiers if ncols <= maxc)
        for rline, cells in rows:
            for ci, c in enumerate(cells, 1):
                n = _cell_text(c)
                if n > limit:
                    # 元组顺序必须与下面的格式串一致：(行号, 列号, 字数, 该表列数, 上限)
                    over.append((rline, ci, n, ncols, limit))
    if over:
        over.sort(key=lambda x: -x[2])
        detail = '；'.join('L%d 第%d列 %d字（该表 %d 列，上限 %d）' % o for o in over[:6])
        if len(over) > 6:
            detail += '；…共 %d 处' % len(over)
        res['warns'].append('表格宽度·%s：%s。%s' % (rules['label'], detail, rules['hint']))


def _term_check(text, res):
    """第 10 类检查：术语与口径一致性（审计 5.3）。三条独立判据，见 layout_spec.TERM_RULES。"""
    rules = getattr(spec, 'TERM_RULES', None)
    if not rules:
        return

    # ① 55 线写法混用：同一级别同时出现 `30F55` 与 `30F MA55`
    r = rules.get('ma55_style')
    if r and _rule_active(r.get('since'), res['path'], res, r['label']):
        compact = set(re.findall(r['compact'], text))
        full = set(re.findall(r['full'], text))
        both = sorted(compact & full)
        if both:
            res['warns'].append('术语·%s：级别 %s 同时出现 xF55 与 xF MA55 两种写法。%s'
                                % (r['label'], '、'.join(both), r['hint']))

    # ② MA20 与 BOLL 中轨并存且未注明等价
    r = rules.get('ma20_boll')
    if r and _rule_active(r.get('since'), res['path'], res, r['label']):
        if re.search(r['a'], text) and re.search(r['b'], text) and not re.search(r['equiv'], text):
            res['warns'].append('术语·%s：%s' % (r['label'], r['hint']))

    # ③ 关键位表的「属性」列出现 —/空（那是「现价」行，不是关键位）
    r = rules.get('level_table_dash')
    if r and _rule_active(r.get('since'), res['path'], res, r['label']):
        dash = set(v.lower() for v in r['dash_values'])
        bad = []
        for _hline, header, rows in _parse_tables(text):
            joined = ''.join(header)
            if not all(k in joined for k in r['header_must_contain']):
                continue
            idx = next((i for i, h in enumerate(header) if '属性' in h), None)
            if idx is None:
                continue
            for rline, cells in rows:
                if idx >= len(cells):
                    continue
                if cells[idx].replace('*', '').strip().lower() in dash:
                    bad.append('L%d（第%d列「%s」值为「%s」）'
                               % (rline, idx + 1, header[idx], cells[idx] or '空'))
        if bad:
            res['warns'].append('术语·%s：%s。%s' % (r['label'], '；'.join(bad[:5]), r['hint']))


def _appendix_coverage_check(text, res):
    """第 11 类检查：附录 A/B 星球覆盖口径（审计 5.4）。

    实测 9/18 晨报：附录 B 列 10 个星球、附录 A 只列 7 —— 信息平权 / 投行圈子 / 口罩哥
    **完全没出现**，也没有一句「本期未覆盖」。读者会以为漏抓（实际是通道未返回/未配置）。

    判据：附录 B 的每个星球名，要么在附录 A 段落里出现，要么该段落含「未覆盖」类说明。
    """
    rules = getattr(spec, 'APPENDIX_COVERAGE', None)
    if not rules or not _rule_active(rules.get('since'), res['path'], res, rules['label']):
        return
    lines = text.split('\n')

    def seg(pat):
        """取 `## 附录 X …` 到下一个 H2 之间的正文。"""
        start = None
        for i, l in enumerate(lines):
            if re.match(r'^##\s', l) and re.search(pat, l):
                start = i
                break
        if start is None:
            return None
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if re.match(r'^##\s', lines[j]):
                end = j
                break
        return '\n'.join(lines[start:end])

    a_seg = seg(r'附录\s*A')
    b_seg = seg(r'附录\s*B')
    if not a_seg or not b_seg:
        res['infos'].append('%s：未同时找到附录 A 与附录 B，跳过覆盖核对' % rules['label'])
        return

    names = []
    for _hline, header, rows in _parse_tables(b_seg):
        joined = ''.join(header)
        if rules['b_header_key'] not in joined or '代号' not in joined:
            continue
        idx = next((i for i, h in enumerate(header) if rules['b_header_key'] in h), None)
        for _rline, cells in rows:
            if idx is not None and idx < len(cells):
                v = re.sub(r'[*`]', '', cells[idx]).strip()
                if v and v not in names:
                    names.append(v)
    if not names:
        res['infos'].append('%s：附录 B 未解析出星球列表，跳过覆盖核对' % rules['label'])
        return

    blob_a = re.sub(r'\s', '', a_seg)
    missing = [n for n in names if re.sub(r'\s', '', n) not in blob_a]
    if missing and not re.search(rules['absence_marker'], a_seg):
        res['warns'].append('附录口径·%s：附录 B 列了 %d 个星球，但 %s 在附录 A 里既不出现、'
                            '也没有「未覆盖」说明 —— 读者会以为漏抓。%s'
                            % (rules['label'], len(names), '、'.join(missing), rules['hint']))
    elif missing:
        res['infos'].append('附录口径：%d 个星球已在附录 A 以「未覆盖」显式说明：%s'
                            % (len(missing), '、'.join(missing)))


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

    # 9) 表格长文本单元格宽度（2026-09-18 审计 5.1 新增）
    _width_check(text, res)

    # 10) 术语与口径一致性（2026-09-18 审计 5.3 新增）
    _term_check(text, res)

    # 11) 附录 A/B 星球覆盖口径（2026-09-18 审计 5.4 新增）
    _appendix_coverage_check(text, res)

    # 聚合同一份报告被多条第 9~11 类规则登记的豁免，压成 1 条「逐一点名」的 INFO。
    # 不聚合的话，每份早于生效起点的历史报告会刷 5 行（5 份报告 25 行），
    # 就又复现「告警太多 → 闸门被无视」那类噪声。
    exempt = res.pop('_exempt', None)
    if exempt:
        by_since = {}
        for label, since, d in exempt:
            by_since.setdefault((since, d), []).append(label)
        for (since, d), labels in by_since.items():
            res['infos'].append(
                '新增规则 %s（共 %d 条）自 %s 起生效，本报告（%s）早于规则确立，不参与'
                % ('、'.join(labels), len(labels), since, d))

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
