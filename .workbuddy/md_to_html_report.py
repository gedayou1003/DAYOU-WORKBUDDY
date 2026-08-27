# -*- coding: utf-8 -*-
"""把作战报告 md 渲染成 Editorial 风 HTML（内嵌预判走势图 SVG，解决 md 预览图不显示 + 排版拥挤）。
用法：$PY .workbuddy/md_to_html_report.py <md路径>
不传参数时默认 2026-08-27 演示版。"""
import io, re, os, sys, markdown

MD = sys.argv[1] if len(sys.argv) > 1 else 'outputs/作战报告_晨报_2026-08-27_行业强弱榜演示版.md'
OUT = MD[:-3] + '.html' if MD.endswith('.md') else MD + '.html'

md = io.open(MD, encoding='utf-8').read()

title = '作战报告'
m = re.search(r'^#\s+(.+)$', md, re.M)
if m:
    title = m.group(1).strip()

# 从 md 内图片引用解析 SVG，并内嵌
svg_inline = ''
m = re.search(r'!\[[^\]]*\]\(([^)]*\.svg)\)', md)
if m:
    svg_path = os.path.normpath(os.path.join(os.path.dirname(MD), m.group(1)))
    if os.path.exists(svg_path):
        svg_raw = io.open(svg_path, encoding='utf-8').read()
        # viewBox 由 gen_forecast_svg.py 统一维护（900 宽，右侧标注不裁剪），此处不再硬改
        svg_raw = re.sub(r'<\?xml[^>]*\?>', '', svg_raw)
        svg_inline = svg_raw.replace(
            '<svg ', '<svg style="width:100%;height:auto;max-width:880px;display:block;margin:20px auto;" '
        )

# 图片引用 → 占位符（转 HTML 后注入 inline svg）
md = re.sub(r'!\[[^\]]*\]\([^)]*\.svg\)', '{{FORECAST_SVG}}', md)

body = markdown.markdown(md, extensions=['tables'])
body = body.replace('<p>{{FORECAST_SVG}}</p>', svg_inline).replace('{{FORECAST_SVG}}', svg_inline)

CSS = """
* { box-sizing: border-box; }
body { background: #f6f2e9; color: #2b2b2b;
  font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', 'Segoe UI', sans-serif;
  font-size: 15px; line-height: 1.85; max-width: 880px; margin: 0 auto; padding: 44px 36px 96px; }
h1 { font-size: 26px; color: #1f3a3a; font-weight: 700; line-height: 1.35;
  border-bottom: 3px solid #1f3a3a; padding-bottom: 14px; margin: 0 0 10px; }
h2 { font-size: 20px; color: #1f3a3a; font-weight: 700; margin: 52px 0 18px;
  padding-top: 18px; border-top: 1px solid #e0d8c8; }
h3 { font-size: 16px; color: #b33a1f; font-weight: 600; margin: 30px 0 12px; }
h4 { font-size: 15px; color: #1f3a3a; font-weight: 600; margin: 24px 0 8px; }
p { margin: 12px 0; }
blockquote { margin: 16px 0; padding: 12px 18px; background: #fffdf6;
  border-left: 3px solid #b33a1f; color: #5a5a4f; font-size: 14px; line-height: 1.75;
  border-radius: 0 6px 6px 0; }
blockquote p { margin: 6px 0; }
table { border-collapse: collapse; width: 100%; margin: 18px 0;
  font-size: 13.5px; line-height: 1.65; background: #fffdf6; }
th, td { border: 1px solid #e0d8c8; padding: 9px 13px; text-align: left; vertical-align: top; }
th { background: #ece4d0; color: #1f3a3a; font-weight: 600; white-space: nowrap; }
tr:nth-child(even) td { background: #fbf7ec; }
ul, ol { margin: 10px 0; padding-left: 26px; }
li { margin: 7px 0; }
hr { border: none; border-top: 2px solid #e0d8c8; margin: 42px 0; }
strong { color: #1f3a3a; font-weight: 600; }
code { background: #ece4d0; padding: 1px 6px; border-radius: 4px;
  font-family: 'SF Mono', Consolas, monospace; font-size: 12.5px; color: #b33a1f; }
"""

html = u"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s</title>
<style>%s</style>
</head>
<body>
%s
</body>
</html>
""" % (title, CSS, body)

io.open(OUT, 'w', encoding='utf-8').write(html)
print('written:', OUT, 'len:', len(html))
