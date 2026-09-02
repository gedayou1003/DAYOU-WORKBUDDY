# -*- coding: utf-8 -*-
"""知识星球双通道抓取统一入口（薄封装，实际逻辑在 fetch_zsxq.main()）。
用法：python fetch_all.py [--window noon]
说明：--window / ZSXQ_WIN_START/END 窗口参数在 import fetch_zsxq 时通过 sys.argv 透传解析。
"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_zsxq as f

if __name__ == '__main__':
    f.main()
