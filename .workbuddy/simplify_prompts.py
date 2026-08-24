#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精简三档 automation 的第四块 prompt，改为引用 预判规则_v5.md。

用途：automation 配置存本机 SQLite，不走 git。换设备（家里/公司）时，
git pull 拿到本脚本 + 预判规则_v5.md 后，跑一次本脚本即可完成 prompt 精简。

幂等：已精简（含兜底句）的档会跳过，可重复执行。
"""
import sqlite3, os, re, sys

DB = os.path.expanduser("~/.workbuddy/workbuddy.db")
V5 = ".workbuddy/预判规则_v5.md"

# 三档任务 id -> 名称
IDS = {
    "automation-1786669064976": "晨报(9:00)",
    "automation-1786674776188": "午间(12:30)",
    "automation-1786694342329": "收盘(16:00)",
}


def simplify(prompt: str) -> str:
    """对单档 prompt 做 v5 精简，返回新 prompt。"""
    # 1. 加兜底句（幂等：已加则跳过）
    if "执行本块前先读" not in prompt:
        prompt = re.sub(
            r"(## 第四块：预判[^\n]*)\n",
            rf'\1\n> 执行本块前先读 `{V5}`（v5 规则 + 偏差归因统计的唯一权威文件）。\n',
            prompt, count=1)

    # 2. 第3步「形成本期预判」：删「综合 X+Y+Z」表述，改为引用 v5 第二节
    prompt = re.sub(
        r'(形成本期预判[^：]*：)\s*综合 [^，。]+，给出',
        rf'\1按 `{V5}` 第二节 v5 规则，给出',
        prompt)

    # 3. 第5步：删「（所有时段通用）」佐证
    prompt = prompt.replace("5. **预判输出规范**（所有时段通用）：", "5. **预判输出规范**：")

    # 4. 第6步「偏差归因与统计」：整段删掉，改为引用 v5 第六节
    start_marker = "6. **偏差归因与统计**"
    end_marker = "写进该记录 review 字段"
    s = prompt.find(start_marker)
    e = prompt.find(end_marker)
    if s != -1 and e != -1:
        e += len(end_marker)
        prompt = prompt[:s] + f"6. **偏差归因与统计**：按 `{V5}` 第六节执行。" + prompt[e:]

    return prompt


def main():
    if not os.path.exists(DB):
        print(f"未找到 db：{DB}")
        sys.exit(1)

    con = sqlite3.connect(DB, timeout=15)
    cur = con.cursor()
    changed = 0
    for aid, name in IDS.items():
        row = cur.execute("SELECT prompt FROM automations WHERE id=?", (aid,)).fetchone()
        if not row:
            print(f"[跳过] {name}：任务不存在")
            continue
        p = row[0]
        new_p = simplify(p)
        if new_p == p:
            print(f"[跳过] {name}：已精简（含兜底句）")
        else:
            cur.execute("UPDATE automations SET prompt=? WHERE id=?", (new_p, aid))
            print(f"[精简] {name}：{len(p)} -> {len(new_p)} 字符（减 {len(p) - len(new_p)}）")
            changed += 1
    con.commit()
    con.close()
    print(f"\n完成：精简 {changed} 档，跳过 {len(IDS) - changed} 档。")


if __name__ == "__main__":
    main()
