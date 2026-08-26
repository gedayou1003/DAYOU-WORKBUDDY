# -*- coding: utf-8 -*-
"""把晨报 automation 的 prompt 同步到标准版（家里维护的唯一权威模板）。

用法：公司电脑 git pull 后跑一次即可对齐晨报 prompt。
    python .workbuddy/sync_morning_prompt.py
幂等：已是最新版则跳过。按 automation name（含"晨报"或"Dawn"）定位，不硬编码 id。
"""
import sqlite3, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "morning_prompt_std.txt")


def main():
    if not os.path.exists(TEMPLATE):
        print(f"[sync] ❌ 模板不存在: {TEMPLATE}")
        sys.exit(1)
    std = open(TEMPLATE, encoding="utf-8").read().strip()
    if not std:
        print("[sync] ❌ 模板为空")
        sys.exit(1)

    db = os.path.expanduser("~/.workbuddy/workbuddy.db")
    if not os.path.exists(db):
        print(f"[sync] ❌ workbuddy.db 不存在: {db}")
        sys.exit(1)

    con = sqlite3.connect(db, timeout=15)
    cur = con.cursor()
    rows = cur.execute("SELECT id, name, prompt FROM automations WHERE deleted_at IS NULL").fetchall()

    target = None
    for aid, name, _ in rows:
        if "晨报" in name or "Dawn" in name:
            target = (aid, name)
            break
    if not target:
        print("[sync] ❌ 未找到晨报 automation（按 name 含「晨报」或「Dawn」定位）")
        con.close()
        sys.exit(1)

    aid, name = target
    cur_prompt = cur.execute("SELECT prompt FROM automations WHERE id=?", (aid,)).fetchone()[0]
    if (cur_prompt or "").strip() == std:
        print(f"[sync] ✅ 晨报 prompt 已是最新标准版，无需更新（{name}）")
    else:
        cur.execute("UPDATE automations SET prompt=? WHERE id=?", (std, aid))
        con.commit()
        print(f"[sync] ✅ 晨报 prompt 已更新到标准版（{name}，长度 {len(cur_prompt or '')} → {len(std)}）")
    con.close()


if __name__ == "__main__":
    main()
