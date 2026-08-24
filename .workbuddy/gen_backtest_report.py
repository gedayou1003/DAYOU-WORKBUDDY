#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成回测 HTML 报告"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
BT = os.path.join(HERE, 'backtest_data')
res = json.load(open(os.path.join(BT, 'backtest_result.json'), encoding='utf-8'))
st = res['stats']
rows = res['rows']

# 逐日明细表
tr = ''
for r in rows:
    p = r['pred']; a = r['actual']; v = r['verdict']
    sup = f"{p['support']:.1f}" if p['support'] else '—'
    resv = f"{p['resistance']:.1f}" if p['resistance'] else '—'
    tj = r['tj_dir'] or '—'
    # 方向颜色
    d = p['direction']
    dc = '#E24B4A' if '多' in d else ('#1D9E75' if '空' in d else '#888')
    pct = a['pct'] if a['pct'] is not None else 0
    pc = '#E24B4A' if pct > 0 else ('#1D9E75' if pct < 0 else '#888')
    dv = v['direction']
    dvc = '#E24B4A' if '✅' in dv else ('#1D9E75' if '❌' in dv else '#888')
    tr += f'<tr><td>{r["T"][5:]}</td><td>{r["next"][5:]}</td><td style="color:{dc}">{d}</td><td>{sup}~{resv}</td><td>{tj}</td><td style="color:{pc}">{pct:+.2f}%</td><td>{a["low"]:.1f}/{a["high"]:.1f}</td><td style="color:{dvc}">{dv}</td><td>{v["range"]}</td><td>{v["support"]}</td><td>{v["resistance"]}</td></tr>'

def card(k, v, color=''):
    c = f' style="color:{color}"' if color else ''
    return f'<div class="card"><div class="k">{k}</div><div class="v"{c}>{v}</div></div>'

html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>000001 预判回测报告</title>
<style>
:root{{--bg:#141518;--card:#1f2126;--text:#e8e8ea;--muted:#9a9ba3;--border:#2c2e33;--red:#E24B4A;--green:#1D9E75;--blue:#5a8dee;--amber:#EF9F27}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;padding:24px;line-height:1.65}}
h1{{font-size:20px;font-weight:600}}
.sub{{font-size:12px;color:var(--muted);margin:6px 0 20px}}
h2{{font-size:15px;font-weight:600;margin:28px 0 12px;padding-left:10px;border-left:3px solid var(--blue)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-bottom:20px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 16px}}
.card .k{{font-size:12px;color:var(--muted)}}
.card .v{{font-size:22px;font-weight:600;margin-top:4px}}
.good{{color:var(--red)}}.bad{{color:var(--green)}}.warn{{color:var(--amber)}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th,td{{padding:6px 8px;text-align:center;border-bottom:1px solid var(--border)}}
th{{color:var(--muted);font-weight:500;position:sticky;top:0;background:var(--bg)}}
.findings{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px 20px}}
.findings li{{margin:8px 0;font-size:13px}}
.tag{{display:inline-block;padding:2px 8px;border-radius:6px;font-size:12px;margin:2px}}
.tag.red{{background:rgba(226,75,74,.15);color:#F09595}}
.tag.green{{background:rgba(29,158,117,.15);color:#7FD8B5}}
.tag.amber{{background:rgba(239,159,39,.15);color:#FAC775}}
.note{{margin-top:16px;font-size:12px;color:var(--muted)}}
</style></head><body>
<h1>上证综指 000001 · 预判回测报告</h1>
<div class="sub">回测区间 2026-07-28 ~ 2026-08-24（{st['n']} 个交易日）· 模型：chan-signal 缠论买卖点（日/周/60F/15F 四周期）· 星球参考：TRUTH AND JUSTICE 技术分析 · 无未来函数（只用截止 T 收盘数据）· 涨红跌绿</div>

<h2>一、核心指标</h2>
<div class="cards">
{card('方向准确率', f'{st["dir_accuracy"]}%', 'bad')}
{card('方向相反率', f'{st["dir_opposite"]}%', 'bad')}
{card('T&J 方向准确率', f'{st["tj_accuracy"]}%', 'good')}
{card('区间覆盖率', f'{st["range_accuracy"]}%', 'bad')}
{card('支撑平均误差', f'{st["sup_mean_err"]} 点', 'bad')}
{card('压力平均误差', f'{st["res_mean_err"]} 点', 'bad')}
{card('支撑守住率', f'{st["sup_hold_rate"]}%', 'bad')}
{card('压力守住率', f'{st["res_hold_rate"]}%', 'bad')}
</div>

<h2>二、关键发现</h2>
<div class="findings">
<ol>
<li><b>方向判断：引擎严重失效，星球观点明显更准</b>。纯缠论引擎方向准确率仅 <b>{st["dir_accuracy"]}%</b>（相反 {st["dir_opposite"]}%，比抛硬币还差）；而 T&J 技术分析方向准确率 <b>{st["tj_accuracy"]}%</b>（相反 {st["tj_opposite"]}%），高出约 16 个百分点。核心原因是买卖点信号<b>滞后</b>：7 月底暴跌中引擎还残留买点偏多、8 月初反弹中又残留卖点偏空，信号成了"反向指标"。</li>
<li><b>区间系统性偏窄</b>。支撑~压力区间覆盖实际走势仅 <b>{st["range_accuracy"]}%</b>；支撑位平均被跌破 <b>{st["sup_mean_err"]} 点</b>、压力位平均被突破 <b>{st["res_mean_err"]} 点</b>，说明模型给的区间比真实波动窄约 ±0.8%。</li>
<li><b>关键拐点 T&J 更有价值</b>：8-18（-2.40%）、8-21（-0.97%）两次下跌，T&J 均提前偏空命中，而引擎在 8-21→8-24 仍给"震荡偏多"看错。</li>
</ol>
</div>

<h2>三、偏差标签统计（观察，不修改策略）</h2>
<div>
<span class="tag red">方向错误 {st["dir_opposite"]}%</span>
<span class="tag green">压力位被突破 {st["res_break_rate"]}%</span>
<span class="tag green">支撑位被跌破 {st["sup_break_rate"]}%</span>
<span class="tag amber">区间越界（窄）</span>
<span class="tag red">信号滞后（趋势反转期反向）</span>
</div>

<h2>四、改进可能（待样本累积后评估）</h2>
<div class="findings">
<ol>
<li><b>方向校准引入星球观点</b>：T&J 方向 47.4% 明显优于引擎 31.6%，且关键拐点更准——建议在方向判断中提高 T&J/大鹏鸟等技术观点权重，或在引擎"方向不明"时以星球观点为准。</li>
<li><b>区间放宽</b>：当前支撑~压力区间系统性偏窄 ±30 点（约 ±0.8%），可考虑区间上/下沿各外扩 0.5~1 个档位，或用 BOLL 上下轨替代单一买卖点作为区间边界。</li>
<li><b>支撑/压力取宽带</b>：买卖点价位作为支撑/压力被穿透是常态（支撑跌破 36.8%、压力突破 57.9%），可结合 BOLL 中轨/上下轨取"支撑带/压力带"而非单点。</li>
<li><b>买卖点滞后问题</b>：趋势反转初期信号反向，是缠论结构类信号固有局限，需用"变盘信号"（15F 带宽收口、日线零轴金叉/死叉）前置预警。</li>
</ol>
</div>

<h2>五、逐日明细（{st['n']} 个预判）</h2>
<table>
<thead><tr><th>预判日</th><th>验证日</th><th>预判方向</th><th>支撑~压力</th><th>T&J</th><th>实际涨跌</th><th>实际低/高</th><th>方向</th><th>区间</th><th>支撑</th><th>压力</th></tr></thead>
<tbody>{tr}</tbody>
</table>

<div class="note">说明：① 本回测为"预判 vs 实际走势"的偏差统计，非收益回测；② 预判方向由四周期买卖点信号加权得出，支撑/压力取近期买卖点价位；③ 方向命中阈值 ±0.15%（震荡 ±0.3%）；④ 以上为历史回测，仅供研究参考，不构成投资建议。</div>
</body></html>'''

out = os.path.join(HERE, '..', 'outputs', '000001_预判回测报告_2026-07-28_08-24.html')
out = os.path.normpath(out)
with open(out, 'w', encoding='utf-8') as f:
    f.write(html)
print('HTML 报告已保存:', out)

# 同时生成 Markdown 摘要
md = f'''# 上证综指 000001 预判回测报告（2026-07-28 ~ 08-24，{st["n"]} 个交易日）

## 核心指标
| 指标 | 数值 |
|---|---|
| 引擎方向准确率 | {st["dir_accuracy"]}%（相反 {st["dir_opposite"]}%） |
| T&J 方向准确率 | {st["tj_accuracy"]}%（相反 {st["tj_opposite"]}%） |
| 区间覆盖率 | {st["range_accuracy"]}% |
| 支撑平均误差 | {st["sup_mean_err"]} 点 |
| 压力平均误差 | {st["res_mean_err"]} 点 |
| 支撑守住率 | {st["sup_hold_rate"]}%（跌破 {st["sup_break_rate"]}%） |
| 压力守住率 | {st["res_hold_rate"]}%（突破 {st["res_break_rate"]}%） |

## 关键结论
1. 方向：引擎 {st["dir_accuracy"]}% 严重失效（信号滞后），T&J {st["tj_accuracy"]}% 明显更准
2. 区间系统性偏窄（覆盖仅 {st["range_accuracy"]}%）
3. 关键拐点（8-18/8-21 下跌）T&J 提前命中，引擎看错

## 改进可能
1. 方向校准引入星球观点（T&J 47.4% > 引擎 31.6%）
2. 区间放宽 ±0.8%
3. 支撑/压力取"带"而非单点
'''
mdout = os.path.join(HERE, '..', 'outputs', '000001_预判回测报告_2026-07-28_08-24.md')
mdout = os.path.normpath(mdout)
with open(mdout, 'w', encoding='utf-8') as f:
    f.write(md)
print('MD 摘要已保存:', mdout)
