# -*- coding: utf-8 -*-
"""
一键打包 WorkBuddy 的关键数据，方便换电脑无缝迁移。
打包内容（解压到新电脑的 C:\\Users\\<用户名>\\ 即可还原）：
  1. ~/.workbuddy/workbuddy.db    —— 自动化任务配置（最关键）
  2. ~/.workbuddy/skills/          —— 技能（chan-signal / ifind 等）
  3. 工作区（脚本+记忆+Cookie+outputs，排除图片和缓存）
  4. ~/.workbuddy/MEMORY.md        —— 用户级记忆
  5. ~/.workbuddy/mcp.json         —— MCP 连接器配置
  6. ~/.workbuddy/binaries/        —— Python/Node 环境（--with-binaries 才包含，较大）

用法：
    python export_backup.py                        # 默认打包（不含 binaries/图片）
    python export_backup.py --with-binaries        # 含 Python/Node 环境（几 G）
    python export_backup.py --with-images          # 含图片（338M，一般不需要）

输出：桌面 WorkBuddy_backup_YYYY-MM-DD.zip
"""
import os, sys, zipfile, datetime

HOME = os.path.expanduser("~")
DOT = os.path.join(HOME, ".workbuddy")

# 自动探测工作区（WorkBuddy 目录下 .workbuddy 最近活动过的子目录）
def find_workspace():
    env = os.environ.get("WORKBUDDY_WORKSPACE")
    if env and os.path.isdir(env):
        return env
    wb = os.path.join(HOME, "WorkBuddy")
    if os.path.isdir(wb):
        cands = []
        for d in os.listdir(wb):
            p = os.path.join(wb, d)
            dot = os.path.join(p, ".workbuddy")
            if os.path.isdir(dot):
                cands.append((os.path.getmtime(dot), p))
        if cands:
            cands.sort(key=lambda x: x[0], reverse=True)
            return cands[0][1]
    return None

# 优先用脚本自身位置反推工作区（脚本在 .workbuddy/ 下，最准确），兜底探测
WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) or find_workspace()

# 排除规则：相对路径或绝对路径命中即排除
EXCLUDE_SUFFIX = ("_缓存.json", "zsxq_fetch_raw.json", "forecast_chain.md")


def _excluded(abspath):
    p = abspath.replace("\\", "/")
    if "zsxq_images" in p:      # 图片中间产物，正文已进 md
        return True
    if p.endswith(EXCLUDE_SUFFIX):
        return True
    if "__pycache__" in p:
        return True
    return False


def add_tree(zf, src_root, arc_root):
    """把 src_root 目录递归写入 zip，arcname 相对 arc_root，命中排除则跳过"""
    for dirpath, dirnames, filenames in os.walk(src_root):
        # 跳过排除目录
        dirnames[:] = [d for d in dirnames if not _excluded(os.path.join(dirpath, d))]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            if _excluded(full):
                continue
            rel = os.path.relpath(full, src_root)
            arcname = os.path.join(arc_root, rel).replace("\\", "/")
            zf.write(full, arcname)


def add_file(zf, filepath, arcname):
    if os.path.isfile(filepath) and not _excluded(filepath):
        zf.write(filepath, arcname)
        return True
    return False


def main():
    with_binaries = "--with-binaries" in sys.argv
    with_images = "--with-images" in sys.argv
    if with_images:
        # 覆盖默认排除，改回包含图片
        global _excluded
        _orig = _excluded
        def _excluded(p):  # noqa: F811
            if p.replace("\\", "/").endswith(EXCLUDE_SUFFIX) or "__pycache__" in p:
                return True
            return False

    date = datetime.datetime.now().strftime("%Y-%m-%d")
    out = os.path.join(HOME, "Desktop", f"WorkBuddy_backup_{date}.zip")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. 自动化配置数据库
        n += add_file(zf, os.path.join(DOT, "workbuddy.db"), ".workbuddy/workbuddy.db")
        # 2. 技能
        skills = os.path.join(DOT, "skills")
        if os.path.isdir(skills):
            add_tree(zf, skills, ".workbuddy/skills")
            n += 1
        # 3. 工作区
        if WORKSPACE:
            add_tree(zf, WORKSPACE, os.path.basename(WORKSPACE))
            n += 1
        else:
            print("⚠️ 未探测到工作区，请用环境变量 WORKBUDDY_WORKSPACE 指定")
        # 4. 用户级记忆
        n += add_file(zf, os.path.join(DOT, "MEMORY.md"), ".workbuddy/MEMORY.md")
        # 4.5 路径解析模块（跨设备核心，多个脚本 import paths）
        n += add_file(zf, os.path.join(DOT, "paths.py"), ".workbuddy/paths.py")
        # 5. MCP 配置
        n += add_file(zf, os.path.join(DOT, "mcp.json"), ".workbuddy/mcp.json")
        # 6. Python/Node 环境（可选）
        if with_binaries:
            b = os.path.join(DOT, "binaries")
            if os.path.isdir(b):
                add_tree(zf, b, ".workbuddy/binaries")
                n += 1
        # 7. zsxq-cli（知识星球 CLI，fetch_zsxq Skill 通道依赖）+ 登录凭证
        npm_dir = os.path.join(HOME, "AppData", "Roaming", "npm")
        for f in ["zsxq-cli.cmd", "zsxq-cli", "zsxq-cli.ps1"]:
            n += add_file(zf, os.path.join(npm_dir, f), "AppData/Roaming/npm/" + f)
        zsxq_pkg = os.path.join(npm_dir, "node_modules", "zsxq-cli")
        if os.path.isdir(zsxq_pkg):
            add_tree(zf, zsxq_pkg, "AppData/Roaming/npm/node_modules/zsxq-cli")
            n += 1
        n += add_file(zf, os.path.join(HOME, ".config", "zsxq-cli", "config.json"),
                      ".config/zsxq-cli/config.json")

    size = os.path.getsize(out) / 1024 / 1024
    print(f"备份完成：{out}")
    print(f"大小：{size:.1f} MB · 已打包 {n} 类数据")
    print()
    print("还原方法：新电脑装好 WorkBuddy 并登录同一账号后，把 zip 解压到 C:\\Users\\<用户名>\\ 覆盖即可。")
    print("注意：新电脑用户名尽量与原电脑一致（gedayou），路径不一致时脚本会自动探测工作区，无需改代码。")


if __name__ == "__main__":
    main()
