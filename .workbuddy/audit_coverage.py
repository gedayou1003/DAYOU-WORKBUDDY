# -*- coding: utf-8 -*-
"""行业覆盖审计 —— 防「当期不热但政策有变」的板块被系统性漏掉。

背景（2026-09-21 真实漏读事故）
--------------------------------
9/21 晨报漏掉一条板块级政策快讯：「消息人士称，美国考虑允许大多数与中国的制药许可交易」
（基业长青+，2026-09-18 22:35，`text` 只有一句、无附件、无展开）。
根因之一是**扫描方式为主题驱动**（涨价/算力/宏观）——主题驱动天然偏向当期最热的题材，
会系统性漏掉「当期不热但政策有变」的行业。本工具把扫描改为**行业清单驱动**：

    申万一级 31 个行业 × 逐行业命中统计 → 零命中的行业即「盲区」，必须人工过一眼。

用法
----
    $PY .workbuddy/audit_coverage.py                    # 审计默认 raw 文件
    $PY .workbuddy/audit_coverage.py --raw <path>
    $PY .workbuddy/audit_coverage.py --md <out.md>       # 同时输出 markdown 表

退出码
------
    0 = 无盲区；1 = 存在零命中行业（需人工确认是否为真盲区）
"""
import argparse
import json
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RAW = os.path.join(HERE, 'zsxq_fetch_raw.json')

# ---------------------------------------------------------------------------
# 申万一级 31 个行业 → 关键词表
# 关键词宁宽勿窄：本工具的目的是「不漏」，不是「精准」；命中后再人工判定相关性。
# ---------------------------------------------------------------------------
SW_L1 = [
    ('农林牧渔', ['农林牧渔', '生猪', '养殖', '种业', '种植', '饲料', '水产', '白羽鸡', '猪价', '母猪']),
    ('基础化工', ['基础化工', '化工', '化肥', '农药', '磷', '氟', '纯碱', '钛白粉', '维生素']),
    ('钢铁',     ['钢铁', '钢价', '螺纹', '铁矿', '板材', '钢厂']),
    ('有色金属', ['有色金属', '有色', '铜', '铝', '黄金', '稀土', '锂矿', '锡', '镍', '小金属']),
    ('电子',     ['电子', '半导体', '芯片', 'PCB', 'MLCC', '存储', '面板', '消费电子', '元件', '光学', 'SOX']),
    ('汽车',     ['汽车', '整车', '乘用车', '新能源车', '智能驾驶', '零部件', '车企']),
    ('家用电器', ['家电', '白电', '空调', '冰箱', '洗衣机', '小家电']),
    ('食品饮料', ['食品饮料', '白酒', '啤酒', '乳业', '调味品', '餐饮', '食饮']),
    ('纺织服饰', ['纺织', '服饰', '服装', '鞋', '家纺']),
    ('轻工制造', ['轻工', '造纸', '包装', '家居', '文娱用品']),
    ('医药生物', ['医药', '制药', '创新药', '生物医药', '生物制品', '化学制药', '中药', '医疗器械',
                 '医疗服务', '医药商业', '医美', 'CXO', 'CRO', 'CDMO', '疫苗', '临床', '药审',
                 'NMPA', 'FDA', 'license', 'license-out', 'BD 交易', '授权引进', '集采', '医保',
                 '国谈', '商保', '药企', '药明', '恒瑞', '百济', '信达', '康龙', '金斯瑞', '羚锐', '亚虹']),
    ('公用事业', ['公用事业', '电力', '燃气', '水务', '火电', '水电', '核电', '绿电']),
    ('交通运输', ['交通运输', '航运', '集运', '航空', '机场', '港口', '快递', '物流', '铁路', '运价']),
    ('房地产',   ['房地产', '地产', '楼市', '房企', '商品房', '拿地', '二手房', '公积金']),
    ('商贸零售', ['商贸零售', '零售', '商超', '电商', '免税', '百货']),
    ('社会服务', ['社会服务', '旅游', '酒店', '餐饮', '教育', '人力资源', '景区']),
    ('综合',     ['综合']),
    ('建筑材料', ['建筑材料', '建材', '水泥', '玻璃', '玻纤', '防水']),
    ('建筑装饰', ['建筑装饰', '基建', '建筑', '工程', '装修']),
    ('电力设备', ['电力设备', '光伏', '风电', '储能', '锂电', '电池', '逆变器', '电网', '特高压', '宁德']),
    ('国防军工', ['军工', '国防', '航空发动机', '导弹', '卫星', '军贸']),
    ('计算机',   ['计算机', '软件', 'IT服务', '信创', '云计算', 'SaaS', '操作系统', '网络安全', 'AI 应用']),
    ('传媒',     ['传媒', '游戏', '影视', '广告', '出版', 'IP', '院线']),
    ('通信',     ['通信', '光模块', '光通信', '运营商', '5G', '6G', 'CPO', '交换机', '数据中心', 'IDC']),
    ('银行',     ['银行', '信贷', '存款', '息差', '不良率']),
    ('非银金融', ['非银', '券商', '保险', '信托', '资管', 'IPO', '投行']),
    ('煤炭',     ['煤炭', '动力煤', '焦煤', '煤价', '焦炭']),
    ('石油石化', ['石油石化', '石油', '原油', '油价', '炼化', 'PTA', '天然气', '油服']),
    ('环保',     ['环保', '污水', '固废', '垃圾', '碳中和', '碳交易']),
    ('美容护理', ['美容护理', '化妆品', '医美', '个护', '护肤']),
    ('机械设备', ['机械设备', '工程机械', '机床', '工业母机', '机器人', '人形机器人', '叉车', '注塑机']),
]

# 宏观/跨行业词：不计入行业命中，仅作参考
MACRO = ['美联储', '加息', '美债', '收益率', '央行', '通胀', 'CPI', 'PPI', 'PMI', '人民币', '汇率',
         '关税', '峰会', '地缘', '原油', '黄金', 'GDP', '财政']


def clean(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s or '')).strip()


def main():
    ap = argparse.ArgumentParser(description='行业覆盖审计（行业清单驱动扫描）')
    ap.add_argument('--raw', default=DEFAULT_RAW, help='zsxq_fetch_raw.json 路径')
    ap.add_argument('--md', default=None, help='同时写出 markdown 表到该路径')
    args = ap.parse_args()

    if not os.path.exists(args.raw):
        print('[FAIL] 找不到原始数据：%s' % args.raw)
        return 2
    data = json.load(open(args.raw, encoding='utf-8'))

    rows = []
    for name, kws in SW_L1:
        body_hits, file_hits, samples = 0, 0, []
        for it in data:
            body = clean(it.get('text'))
            names = ' | '.join(f.get('name', '') for f in (it.get('files') or []))
            hit_b = any(k in body for k in kws)
            hit_f = any(k in names for k in kws)
            if hit_b:
                body_hits += 1
                if len(samples) < 2:
                    samples.append('%s %s' % (it.get('group', '')[:6], it.get('create_time', '')[5:16]))
            if hit_f:
                file_hits += 1
        rows.append((name, body_hits, file_hits, samples))

    total = len(data)
    print('=' * 78)
    print('行业覆盖审计（行业清单驱动）  数据源：%s' % os.path.basename(args.raw))
    print('窗口内条数：%d ｜ 行业数：%d' % (total, len(SW_L1)))
    print('=' * 78)
    print('%-10s %8s %8s   %s' % ('申万一级', '正文命中', '附件命中', '样例'))
    print('-' * 78)

    blind, thin = [], []
    for name, b, f, s in rows:
        flag = ''
        if b == 0 and f == 0:
            flag = ' ⚠️ 盲区'
            blind.append(name)
        elif b == 0:
            flag = ' △ 仅附件'
            thin.append(name)
        print('%-10s %8d %8d   %s%s' % (name, b, f, '；'.join(s) if s else '—', flag))

    print('-' * 78)
    print('零命中（真盲区）：%d 个 —— %s' % (len(blind), '、'.join(blind) if blind else '无'))
    print('仅附件命中（正文未提及）：%d 个 —— %s' % (len(thin), '、'.join(thin) if thin else '无'))
    print()
    print('> 判读口径：')
    print('>  「盲区」= 该行业在本窗口既无正文、也无附件提及 → 必须人工确认是「确实没有信息」')
    print('>            还是「有信息但我没抓到/没读」（对照 2026-09-21 医药漏读事故）。')
    print('>  「仅附件命中」= 正文零提及但挂了该行业研报附件 → 附件正文必须读，否则该行业必漏。')

    if args.md:
        with open(args.md, 'w', encoding='utf-8') as fp:
            fp.write('| 申万一级 | 正文命中 | 附件命中 | 样例 |\n|---|---|---|---|\n')
            for name, b, f, s in rows:
                mark = ' ⚠️ 盲区' if (b == 0 and f == 0) else (' △ 仅附件' if b == 0 else '')
                fp.write('| %s | %d | %d | %s |\n' % (name, b, f, '；'.join(s) if s else '—'))
        print('\n已写出 markdown：%s' % args.md)

    return 1 if blind else 0


if __name__ == '__main__':
    sys.exit(main())
