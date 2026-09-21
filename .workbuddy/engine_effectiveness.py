# -*- coding: utf-8 -*-
"""复盘：两套缠论引擎的有效性（定量 + 定性支撑）。

指标1（引擎B·买卖点）: 提取 evidence.engineB 里所有 "N买/N卖@价格" 点位，
   判断是否落在当日 [low, high] 内（触及），以及距实际极值（高点/低点）的偏差（精准度）。
指标2（引擎A·多维融合）: 提取日线/60F 缠论结构(down/sideways/up)，对比实际方向命中。

2026-09-21 全链路冒烟修的两处（此前一直没暴露，因为都是手敲时恰好站在 .workbuddy 里）：
  1) 链接路径原为裸相对名 'forecast_chain.json' → 只有 cd .workbuddy 才跑得动，
     从仓库根调用直接 FileNotFoundError。改为按 __file__ 锚定。
  2) `review.actual` 在链里存在**三种形态**（dict / 人工散文 str / None），
     原实现只当 dict 用 → `a.get('high')` 在散文那两条上 AttributeError。
     现兼容三种形态，并把**无法纳入统计**的记录逐条打印（不静默跳过）。
"""
import json, os, re

# 路径按**脚本自身位置**解析，不依赖 cwd。
# 2026-09-21 全链路冒烟发现：这里原来写的是裸相对路径 'forecast_chain.json'，
# 只有 `cd .workbuddy` 之后才跑得动；而定时任务/冒烟都是从仓库根调的，
# 直接 FileNotFoundError（rc=1）。这类「cwd 隐式依赖」换机器、换调度器必炸，
# 且因为脚本平时是手敲的、恰好站在 .workbuddy 里，所以一直没暴露。
HERE = os.path.dirname(os.path.abspath(__file__))
recs = json.load(open(os.path.join(HERE, 'forecast_chain.json'), encoding='utf-8'))
verified = [r for r in recs if r.get('status') == 'verified']

def _parse_actual_prose(s):
    """从人工写的复盘散文里抽 OHLC。

    链里有两条记录的 `review.actual` 是**人写的整句话**而不是 dict：
      `9/11 全天：O=3910.92 H=3912.32 L=3852.03 C=3888.11（-1.18%），gap=-0.60% 低开…`
    数字都在里面，只是被包在自然语言里。直接当 dict 用会 AttributeError
    （2026-09-21 全链路冒烟就崩在这），所以这里解析出来，拿不到就返回 None。
    """
    out = {}
    for key, tag in (('open', 'O'), ('high', 'H'), ('low', 'L'), ('close', 'C')):
        m = re.search(r'\b%s\s*[=:：]\s*(-?[\d.]+)' % tag, s)
        if m:
            out[key] = float(m.group(1))
    m = re.search(r'[（(]\s*(-?[\d.]+)\s*%', s)
    if m:
        out['pct_chg'] = float(m.group(1))
    return out if (out.get('high') and out.get('low')) else None


# 无法纳入统计的记录：(id, 原因)。**必须如实打印**，不许静默跳过 ——
# 「统计样本悄悄少了几条」和「这几天本来就没数据」在结果上无法区分。
UNRESOLVED = []


def get_actual(r):
    """取当日实际行情。链里实际存在**三种形态**，都要兼容：

      1) dict —— 标准形态（49 条）
      2) str  —— 人工写的复盘散文（9/11、9/14 两条），数字在自然语言里
      3) None —— 尚未补录（9/18 close 一条：status 已 verified 但 actual 为空）
    """
    a = (r.get('review') or {}).get('actual')
    if isinstance(a, dict):
        return a
    if isinstance(a, str):
        return _parse_actual_prose(a) or {}
    return {}

def review_verdict(r, dim):
    rev = r.get('review') or {}
    return rev.get(dim + '_verdict') or rev.get(dim) or ''

# ---------- 指标1: 引擎B 买卖点触及/精准度 ----------
print('=' * 70)
print('【指标1】引擎B 买卖点作为支撑/压力的有效性')
print('=' * 70)
B_pts = []  # (id, 点位名, 价格, 是否触及, 距极值偏差%)
for r in verified:
    ev = r.get('evidence') or {}
    txt = ev.get('engineB') or ''
    a = get_actual(r)
    if not txt:
        UNRESOLVED.append((r['id'], 'evidence.engineB 为空，无买卖点可核'))
        continue
    if not a.get('high'):
        UNRESOLVED.append((r['id'], 'review.actual 缺失或不可解析（形态异常），无当日 H/L 可比对'))
        continue
    hi, lo = float(a['high']), float(a['low'])
    # 提取 "N买@价格" / "N卖@价格"
    for m in re.finditer(r'(一买|二买|三买|一卖|二卖|三卖)@([\d.]+)', txt):
        name, price = m.group(1), float(m.group(2))
        touched = lo - 0.5 <= price <= hi + 0.5
        # 距极值偏差：卖点对应 high，买点对应 low
        if '卖' in name:
            dev = (price - hi) / hi * 100
        else:
            dev = (price - lo) / lo * 100
        B_pts.append((r['id'], name, price, touched, dev))

print(f'总买卖点样本: {len(B_pts)}')
if B_pts:
    touched = sum(1 for p in B_pts if p[3])
    print(f'触及率（点位落在当日[low,high]内）: {touched}/{len(B_pts)} = {touched/len(B_pts)*100:.1f}%')
    # 精准度：距极值 |dev| <= 0.5% 视为"精准"
    precise = sum(1 for p in B_pts if abs(p[4]) <= 0.5)
    print(f'精准度（距实际极值±0.5%内）: {precise}/{len(B_pts)} = {precise/len(B_pts)*100:.1f}%')
    print()
    print('明细（按偏差排序）:')
    for p in sorted(B_pts, key=lambda x: abs(x[4])):
        print(f"  {p[0]}  {p[1]:4s}@{p[2]:8.2f}  触及={p[3]}  距极值{p[4]:+6.2f}%")

# ---------- 指标2: 引擎A 方向命中 ----------
print()
print('=' * 70)
print('【指标2】引擎A 缠论结构 vs 实际方向（日线级别）')
print('=' * 70)
def parseA_dir(text, lvl):
    if not text:
        return None
    idx = text.find(lvl)
    if idx == -1:
        return None
    seg = text[idx: idx + 45]
    m = re.search(r'(down|sideways|up)', seg)
    return m.group(1) if m else None

hit = miss = side = 0
detail = []
for r in verified:
    ev = r.get('evidence') or {}
    d = parseA_dir(ev.get('engineA'), '日线')
    a = get_actual(r)
    pct = a.get('pct_chg')
    if d is None:
        continue
    if pct is None:
        UNRESOLVED.append((r['id'], 'review.actual 无 pct_chg，方向命中无法判定'))
        continue
    up = pct > 0.15
    dn = pct < -0.15
    if d == 'down':
        if dn: hit += 1; detail.append((r['id'], 'down', pct, 'HIT'))
        elif up: miss += 1; detail.append((r['id'], 'down', pct, 'MISS'))
        else: side += 1; detail.append((r['id'], 'down', pct, 'FLAT'))
    elif d == 'up':
        if up: hit += 1; detail.append((r['id'], 'up', pct, 'HIT'))
        elif dn: miss += 1; detail.append((r['id'], 'up', pct, 'MISS'))
        else: side += 1; detail.append((r['id'], 'up', pct, 'FLAT'))
    else:
        side += 1; detail.append((r['id'], 'sideways', pct, 'SIDE'))

n = hit + miss
print(f'日线明确方向(down/up)样本: 命中 {hit}, 反向 {miss}, 震荡/平 {side}')
print(f'方向命中率（排除震荡）: {hit}/{n} = {hit/n*100:.1f}%' if n else '无样本')
print('明细:')
for d in detail:
    print(f"  {d[0]}  {d[1]:8s}  实际{d[2]:+6.2f}%  {d[3]}")

# 引擎A"观望"占比统计
print()
obs = sum(1 for r in verified if parseA_dir((r.get('evidence') or {}).get('engineA'), '日线') is None)
print(f'engineA 无法提取日线方向的记录: {obs}（多为"观望"表述或无 engineA 字段）')

# ---------- 未纳入统计的记录（不许静默跳过）----------
print()
print('=' * 70)
print('【未纳入统计的记录】')
print('=' * 70)
if not UNRESOLVED:
    print('  无 —— 所有 verified 记录都参与了统计')
else:
    print(f'  共 {len(UNRESOLVED)} 处：')
    for rid, why in UNRESOLVED:
        print(f'  - {rid}：{why}')
    print()
    print('  ⚠️ 这几条会让「命中率」的分母变小。样本数少时，分母少 2 条足以让'
          '百分比差出好几个点，')
    print('     所以必须显式列出来，不能让它悄悄从统计里消失。')
