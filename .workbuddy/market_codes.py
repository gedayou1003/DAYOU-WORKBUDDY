# -*- coding: utf-8 -*-
"""
指数/标的代码注册表（统一数据源解析）
======================================
用途：把"用户说的代码"（如 000300 / 沪深300 / sh000300）统一解析为腾讯行情接口代码，
      供 get_daily_ohlc.py、chan-signal 引擎、预判链等多处复用。

数据源支持情况（2026-08-21 实测）：
- 腾讯 fqkline/mkline：宽基指数全部可用（sh000300/sh000905/sh000852/sh000016/sz399006...）
- 申万行业指数（801xxx）：腾讯/新浪/东财公开接口均不可用；数据源=akshare（index_hist_sw，日线/周线 OHLC）

用法：
    from market_codes import resolve, get_name
    code = resolve('000300')        # -> 'sh000300'
    code = resolve('沪深300')        # -> 'sh000300'
    code = resolve('sh000300')      # -> 'sh000300'
    code = resolve('801080')        # -> 申万电子（data_source=akshare）
"""

# 主注册表：标准代码 -> {腾讯代码, 名称, 类型}
# 宽基指数（腾讯已验证可用）
INDEXES = {
    '000001': {'tencent': 'sh000001', 'name': '上证综指', 'type': '宽基指数'},
    '000016': {'tencent': 'sh000016', 'name': '上证50', 'type': '宽基指数'},
    '000300': {'tencent': 'sh000300', 'name': '沪深300', 'type': '宽基指数'},
    '000905': {'tencent': 'sh000905', 'name': '中证500', 'type': '宽基指数'},
    '000852': {'tencent': 'sh000852', 'name': '中证1000', 'type': '宽基指数'},
    '399006': {'tencent': 'sz399006', 'name': '创业板指', 'type': '宽基指数'},
    '399303': {'tencent': 'sz399303', 'name': '国证2000', 'type': '宽基指数'},
    # '932000' 中证2000 腾讯接口无数据（实测空），暂不收录
}

# 申万一级行业指数（2021版，31个）——数据源：akshare（index_hist_sw）
# 实测（2026-08-21）：akshare 提供完整 OHLC 日线 + 周线，31 个行业全部可用；无分钟线
SW_INDEXES = {
    '801010': {'tencent': None, 'name': '申万农林牧渔', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801030': {'tencent': None, 'name': '申万基础化工', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801040': {'tencent': None, 'name': '申万钢铁', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801050': {'tencent': None, 'name': '申万有色金属', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801080': {'tencent': None, 'name': '申万电子', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801110': {'tencent': None, 'name': '申万家用电器', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801120': {'tencent': None, 'name': '申万食品饮料', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801130': {'tencent': None, 'name': '申万纺织服饰', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801140': {'tencent': None, 'name': '申万轻工制造', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801150': {'tencent': None, 'name': '申万医药生物', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801160': {'tencent': None, 'name': '申万公用事业', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801170': {'tencent': None, 'name': '申万交通运输', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801180': {'tencent': None, 'name': '申万房地产', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801200': {'tencent': None, 'name': '申万商贸零售', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801210': {'tencent': None, 'name': '申万社会服务', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801230': {'tencent': None, 'name': '申万综合', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801710': {'tencent': None, 'name': '申万建筑材料', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801720': {'tencent': None, 'name': '申万建筑装饰', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801730': {'tencent': None, 'name': '申万电力设备', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801740': {'tencent': None, 'name': '申万国防军工', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801750': {'tencent': None, 'name': '申万计算机', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801760': {'tencent': None, 'name': '申万传媒', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801770': {'tencent': None, 'name': '申万通信', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801780': {'tencent': None, 'name': '申万银行', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801790': {'tencent': None, 'name': '申万非银金融', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801880': {'tencent': None, 'name': '申万汽车', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801890': {'tencent': None, 'name': '申万机械设备', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801950': {'tencent': None, 'name': '申万煤炭', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801960': {'tencent': None, 'name': '申万石油石化', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801970': {'tencent': None, 'name': '申万环保', 'type': '申万一级行业', 'data_source': 'akshare'},
    '801980': {'tencent': None, 'name': '申万美容护理', 'type': '申万一级行业', 'data_source': 'akshare'},
}

# 全部合并（方便统一查询）
ALL = {}
ALL.update(INDEXES)
ALL.update(SW_INDEXES)

# 名称 -> 标准代码 的倒查索引
NAME_TO_CODE = {v['name']: k for k, v in ALL.items()}


def resolve(user_input):
    """
    把用户输入解析为标准代码（6位数字）和腾讯代码。
    支持：'000300' / '沪深300' / 'sh000300' / '300'（唯一前缀）等。
    返回 dict: {code, tencent, name, type, data_source}
    无法解析时返回 None。
    """
    s = str(user_input).strip().lower().replace(' ', '')

    # 1. 直接匹配标准代码
    if s in ALL:
        info = ALL[s]
        return {'code': s, 'tencent': info['tencent'], 'name': info['name'],
                'type': info.get('type', ''), 'data_source': info.get('data_source', 'tencent')}

    # 2. 匹配名称（如 沪深300、上证综指）
    if s in NAME_TO_CODE:
        c = NAME_TO_CODE[s]
        info = ALL[c]
        return {'code': c, 'tencent': info['tencent'], 'name': info['name'],
                'type': info.get('type', ''), 'data_source': info.get('data_source', 'tencent')}

    # 3. 匹配带市场前缀（sh000300 / sz399006）
    for c, info in ALL.items():
        if info['tencent'] and s == info['tencent'].lower():
            return {'code': c, 'tencent': info['tencent'], 'name': info['name'],
                    'type': info.get('type', ''), 'data_source': info.get('data_source', 'tencent')}

    # 4. 纯数字前缀唯一匹配（如 '300' -> 000300）
    if s.isdigit() and len(s) < 6:
        matches = [c for c in ALL if c.endswith(s)]
        if len(matches) == 1:
            c = matches[0]
            info = ALL[c]
            return {'code': c, 'tencent': info['tencent'], 'name': info['name'],
                    'type': info.get('type', ''), 'data_source': info.get('data_source', 'tencent')}

    return None


def get_name(code):
    """按标准代码取名称，未知返回原码"""
    info = ALL.get(code)
    return info['name'] if info else code


def is_supported_tencent(code):
    """该标准代码是否可用腾讯接口拉取"""
    info = ALL.get(code)
    return bool(info and info.get('tencent'))


if __name__ == '__main__':
    for t in ['000001', '000300', '沪深300', 'sh000905', '1000', '801080', '申万电子', 'xxxx']:
        r = resolve(t)
        print(f'{t!r:12} -> {r}')
