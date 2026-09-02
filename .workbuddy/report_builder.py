# -*- coding: utf-8 -*-
"""统一报告生成入口（参数化日期，替代 refine_report.py + update_block5.py）。

流程：读原始晨报 → 标题/头部替换 → 第一块格式转换 → 第四块偏差统计（程序化重算）
     → 第五块行业强弱榜（industry_rank 三要素自动推导）→ 写 md。

用法：
    python report_builder.py [YYYY-MM-DD]
不传日期默认今天。原始晨报须已存在：outputs/知识星球晨报_YYYY-MM-DD_改进版.md
"""
import io, os, re, sys, json, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import industry_rank     # 复用 derive / render（有 __main__ 保护，import 无副作用）

DATE = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime('%Y-%m-%d')

SRC_MD = os.path.join(ROOT, 'outputs', f'知识星球晨报_{DATE}_改进版.md')
DST_MD = os.path.join(ROOT, 'outputs', f'作战报告_晨报_{DATE}.md')
FORECAST = os.path.join(HERE, 'forecast_chain.json')


# ---------- 第一块格式转换（内联自 refine_report，去元数据 + 合并星球） ----------
def clean_point(p):
    c = p
    c = re.sub(r'（附件[^（）]*）', '', c)
    c = re.sub(r'附件：[^；；]*?(?:\.html|PDF|docx|MP3|xlsx)[^；；]*[；；]?', '', c)
    c = re.sub(r'中英 PDF \+ 英 PDF\s*', '', c)
    c = c.replace('**', '').replace('*', '')
    c = re.sub(r'\s{2,}', ' ', c)
    return c.strip()


def format_post(time, title, points):
    r = [f'- **[{time}] {title}**']
    for p in points:
        c = clean_point(p)
        if not c:
            continue
        if re.match(r'^\d+\.', c):
            r.append(f'        {c}')     # 8 空格（嵌套数字列表）
        else:
            r.append(f'    - {c}')       # 4 空格（嵌套子列表）
    return '\n'.join(r)


def convert_block1(text):
    lines = text.split('\n')
    out = []
    current_group = None
    posts = []
    cur = None
    title_re = re.compile(r'^\*\*(.+?)\s+\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\]\s*·\s*(.+?)\*\*')

    def flush_post():
        nonlocal cur
        if cur is not None:
            posts.append(cur); cur = None

    def flush_group():
        nonlocal current_group, posts
        if current_group is not None:
            out.append(f'**{current_group}**：')
            out.append('')          # 空行：让 markdown 识别下方为列表
            for t, ti, pts in posts:
                out.append(format_post(t, ti, pts))
            out.append('')
            current_group = None; posts = []

    for line in lines:
        s = line.strip()
        if s.startswith('### ') or s.startswith('## ') or s.startswith('> '):
            flush_post(); flush_group()
            if s.startswith('> '):
                s = s.replace('分板块逐条列出（标题+时间+核心要点，含图片正文）',
                              '分板块按星球归组（时间倒序罗列，含图片正文）')
            out.append(s); out.append(''); continue
        m = title_re.match(s)
        if m:
            flush_post()
            g = m.group(1); t = m.group(3); ti = m.group(4)
            if g != current_group:
                flush_group(); current_group = g
            cur = [t, ti, []]; continue
        if cur is not None:
            if s == '':
                continue
            pt = re.sub(r'^-\s+', '', s)
            cur[2].append(pt); continue
        flush_post(); flush_group()
        if s:
            s = re.sub(r'\s*PDF\s+[\d.]+\s*(?:KB|MB)', '', s)
            s = re.sub(r'（[^（）]*(?:imgs|附件|已读)[^（）]*）', '', s)
            out.append(s)
    flush_post(); flush_group()
    return '\n'.join(out)


# ---------- 第四块偏差统计（程序化重算，禁手写数字） ----------
def compute_bias_stats(forecast_path):
    chain = json.load(open(forecast_path, encoding='utf-8'))
    verified = [r for r in chain if r.get('status') == 'verified']
    dims = ['direction', 'range', 'support', 'resistance']
    stat = {k: {'ok': [], 'part': [], 'fail': []} for k in dims}

    for r in verified:
        rv = r.get('review')
        if not isinstance(rv, dict):
            continue
        for k in dims:
            v = rv.get(k + '_verdict') or rv.get(k) or ''
            if not isinstance(v, str) or not v:
                continue
            if v.startswith('✅'):
                stat[k]['ok'].append(r['id'])
            elif v.startswith('⚠'):
                stat[k]['part'].append(r['id'])
            elif v.startswith('❌'):
                stat[k]['fail'].append(r['id'])

    from collections import Counter
    bc = Counter()
    for r in verified:
        rv = r.get('review')
        if not isinstance(rv, dict):
            continue
        bt = rv.get('bias_type') or rv.get('bias') or []
        if isinstance(bt, str):
            bt = [bt]
        for t in bt:
            bc[t] += 1
    return {'n': len(verified), 'stat': stat, 'bias': bc}


def render_bias_stats(st):
    n = st['n']; stat = st['stat']; bc = st['bias']
    L = ['### 三、偏差观察统计表（v5 第六节：四维配对计数 + bias_type 三分类）', '']
    L.append('> 累计 ≥3 类「规律已现」标签 = 仅观察不修改任何策略/逻辑/参数（绝不修改）')
    L.append(f'> 截至 {DATE}，已复盘 **{n} 期**预判；四维配对计数从 `forecast_chain.json` 逐条 review 程序化重算')
    L.append('')
    L.append('#### 四维配对计数（每维 ✅命中 / ⚠️部分 / ❌失效 分别计数，绝不抵消）')
    L.append('')
    L.append('| 维度 | ✅ 命中 | ⚠️ 部分 | ❌ 失效 | 纯命中率 |')
    L.append('|------|--------|--------|--------|---------|')
    for k, zh in [('direction', '方向'), ('range', '区间'), ('support', '支撑'), ('resistance', '压力')]:
        s = stat[k]; ok, part, fail = len(s['ok']), len(s['part']), len(s['fail'])
        tot = ok + part + fail
        rate = f'{ok/tot*100:.1f}%' if tot else '-'
        L.append(f"| **{zh}** | {ok} | {part} | {fail} | {rate} |")

    def cnt_like(prefix):
        return sum(v for k, v in bc.items() if k.startswith(prefix))
    sup_break = cnt_like('支撑跌破')
    press_break = cnt_like('压力位短暂突破')
    range_break = cnt_like('区间下沿破位')
    dir_err = cnt_like('方向错误') + cnt_like('方向相反')

    L.append('')
    L.append('#### bias_type 三分类统计')
    L.append('')
    L.append('| 真偏差类（计入 ≥3 阈值） | 累计 | 规律化 |')
    L.append('|----------------------|------|--------|')
    for name, cnt in [('支撑跌破', sup_break), ('压力位短暂突破', press_break),
                      ('区间下沿破位', range_break), ('方向错误/相反', dir_err)]:
        flag = '✅ 规律已现（≥3）' if cnt >= 3 else '观察'
        L.append(f'| **{name}** | **{cnt}** | {flag} |')
    L.append('')
    L.append('> 关键观察（仅观察，不修改任何策略/逻辑/参数）：命中「规律已现」的维度仅标注不优化。')
    return '\n'.join(L)


# ---------- 第五块（industry_rank 自动推导） ----------
def build_block5():
    rt, realtime, sw_agg = industry_rank.load_data()
    rank = industry_rank.derive(realtime, sw_agg)
    body = industry_rank.render(rank, rt.get('ts', ''), realtime, sw_agg)
    return ('## 第五块 · 行业强弱榜\n\n'
            '> 数据源：akshare 实时（`scan_sw_realtime.py`，ts=' + rt.get('ts', '') + '）+ 同花顺缠论方向分（`scan_ths.py`，T+1）\n'
            '> 推导逻辑：与 v5 预判模型一致的三要素——①星球观点 ②缠论信号 ③复盘经验，**不只看涨跌幅**。\n\n'
            + body + '\n\n---\n\n')


# ---------- 主流程 ----------
def main():
    if not os.path.exists(SRC_MD):
        print(f'❌ 原始晨报不存在：{SRC_MD}')
        print('   请先跑晨报 prompt 生成原始报告，再运行本脚本后处理。')
        return

    md = io.open(SRC_MD, encoding='utf-8').read()

    # 1) 标题
    md = re.sub(r'^#\s+知识星球晨报[^\n]*', f'# 作战报告 · 晨报 · {DATE}', md, count=1)

    # 2) 第一块格式转换
    b1_start = md.index('## 第一块'); b1_end = md.index('## 第二块')
    new_b1 = convert_block1(md[b1_start:b1_end])

    # 3) 第四块偏差统计（程序化）
    st = compute_bias_stats(FORECAST)
    stat_md = render_bias_stats(st)
    stat_start = md.index('### 三、偏差观察统计表'); stat_end = md.index('### 四、走势图')
    md = md[:stat_start] + stat_md + '\n\n' + md[stat_end:]

    # 4) 第五块（industry_rank 自动）
    b5_start = md.index('## 第五块'); b5_end = md.index('## 附录 A')
    md = md[:b5_start] + build_block5() + md[b5_end:]

    # 5) 拼接第一块
    md = md[:b1_start] + new_b1 + '\n' + md[b1_end:]

    # 产物清单：主报告名替换
    md = re.sub(r'`outputs/知识星球晨报_[^`]*`\s*\|\s*主报告', f'`outputs/作战报告_晨报_{DATE}.md` | 主报告', md)

    io.open(DST_MD, 'w', encoding='utf-8').write(md)
    print(f'✅ 已生成 {DST_MD}（{len(md)} 字）')
    print(f'   HTML 请用：$PY .workbuddy/md_to_html_report.py {DST_MD}')


if __name__ == '__main__':
    main()
