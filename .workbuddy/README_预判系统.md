# 技术预判系统代码说明

> 上证综指（默认）及任意宽基指数的缠论预判 + 预判链复盘。支持沪深300/中证500/中证1000/上证50/创业板指等。
> 所有脚本用 venv python 运行：`C:\Users\gedayou\.workbuddy\binaries\python\envs\default\Scripts\python.exe`

## 一、文件清单

| 文件 | 作用 | 支持多指数 |
|------|------|-----------|
| `.workbuddy/market_codes.py` | **指数代码注册表**（标准码↔腾讯码↔名称），统一解析入口 | ✅ 核心 |
| `.workbuddy/get_daily_ohlc.py` | 取当日/最近 N 日 OHLC（复盘用实际走势） | ✅ `python get_daily_ohlc.py 000300` |
| `.workbuddy/forecast_analyze.py` | **一键预判入口**：行情+引擎+复盘数据包 | ✅ `python forecast_analyze.py 000300` |
| `.workbuddy/forecast_chain.json` | 预判链存储（每条带 code，多标的隔离） | ✅ |
| `skills/chan-signal__skillhub/run_000001_chansignal.py` | chan-signal 买卖点引擎（五周期） | ✅ `--code 000300` |
| `skills/chan-signal__skillhub/run_000001_boll_chan.py` | BOLL×缠论交叉验证+变盘概率 | ✅ `--code 000300` |
| `skills/chanlun-multidimensional-tech-analysis__skillhub/run_000001_multi.py` | 多维融合引擎（四级别） | ✅ `--code 000300` |
| `.workbuddy/analyze_000001_multi.py` | 四周期联动+区间套（收盘后档用） | ⚠️ 待改造 |
| `skills/_backup_20260821/` | 改造前引擎脚本备份 | — |

## 二、数据源支持情况（2026-08-21 实测）

| 类型 | 腾讯 fqkline/mkline | 备注 |
|------|--------------------|------|
| 宽基指数（沪深300/500/1000/上证50/创业板/国证2000）| ✅ 全部可用 | 主数据源 |
| 中证2000（932000）| ❌ 空数据 | 未收录 |
| 申万一级行业（801xxx，31个）| ❌ 不支持 | 已预留注册表，待接入 iFinD/Wind |

## 三、典型用法

```bash
# 1. 快速取行情（任意指数，支持名称）
python get_daily_ohlc.py 000300 2          # 沪深300 最近2日
python get_daily_ohlc.py 中证1000           # 中证1000

# 2. chan-signal 买卖点（任意指数）
cd skills/chan-signal__skillhub
python run_000001_chansignal.py --code 000300

# 3. BOLL×缠论 变盘概率
python run_000001_boll_chan.py --code 000300

# 4. 多维融合引擎
cd ../chanlun-multidimensional-tech-analysis__skillhub
python run_000001_multi.py --code 000300

# 5. 一键预判数据包（行情+引擎+上期复盘）
cd ../../.workbuddy
python forecast_analyze.py 000300
```

## 四、改造说明（2026-08-21）

1. 三个引擎脚本加了 `--code` 参数，**默认 000001 向后兼容**，原自动化不受影响。
2. 代码解析统一走 `market_codes.resolve()`，支持 `000300` / `沪深300` / `sh000300` / `中证1000` 等多种输入。
3. 输出文件名按标准代码隔离（如 `000300_20260821_chansignal.json`），不会覆盖 000001 的结果。
4. 改造前脚本备份在 `skills/_backup_20260821/`。

## 五、待办 / 已知限制

- [ ] `analyze_000001_multi.py`（四周期联动）尚未参数化，收盘后档如需多指数需改造。
- [ ] 机械复盘（`forecast_analyze.py` 的 `mechanical_review`）方向判定较粗（按涨跌幅符号近似），仅作辅助，最终以 AI 综合判断为准。
- [ ] 分钟级数据量：各引擎拉 400 根，深市指数（sz 前缀）已实测可用。
- [ ] **引擎脚本硬编码 workspace 路径**导入 `market_codes`（三个引擎脚本里 `sys.path.insert(0, .../WorkBuddy/2026-08-14-09-01-12/.workbuddy)`）。当前可用（中文名已实测），有 try/except 兜底 fallback 到 sh/sz 前缀规则；若 workspace 目录名变化，需同步更新三个脚本的导入路径（否则仅中文名/申万代码解析失效，宽基数字代码不受影响）。

## 六、申万行业接入（2026-08-21）

- `market_codes.py` 的 SW_INDEXES（31 个申万一级行业）data_source 已设为 `akshare`
- `run_sw_chansignal.py`：申万日线+周线缠论（复用 chan_signal 引擎 + akshare 数据源）
- 限制：申万行业无分钟线（免费源限制），仅日线/周线级别
- 用法：`python run_sw_chansignal.py --code 801080`（或 `--code 申万电子`）

## 七、代码自查记录（2026-08-21）

修复的逻辑问题：
1. **get_daily_ohlc.py**：`prev_close`/`pct_chg` 原先从切片后 `rows` 取倒数第二根，`days=1` 时缺失；已改为从完整 `kline` 取，`days=1` 也能正确计算涨跌幅
2. **market_codes.py**：删除 801020 后 801010/801030 挤同一行（格式），已拆开；docstring 过时（还写"待接入 iFinD/Wind"）已更新为 akshare
3. **forecast_analyze.py**：`mechanical_review` 方向判定原先只认中文（偏多/偏空/震荡），术语英文化后会失效；已加 `_normalize_direction` 统一映射（兼容中英文）；删除未用变量 `rng`；`fetch_ohlc` 的 days 硬编码 2 改回 1

## 八、定时任务全脚本自查（2026-08-21 第二轮，重点）

本轮覆盖所有定时任务（晨报/午间/晚间/收盘后）调用的脚本，发现并修复 4 个问题：

1. **【严重】`run_000001_multi.py` 日线/周线硬编码日期 `'2026-08-14'`**：多维引擎（引擎A）日线/周线取数 end 日期写死为 workspace 创建日，导致日线/周线级别用**过期数据**（比当天少 N 个交易日）。已改为 `datetime.now().strftime('%Y-%m-%d')`。影响：此前晨报/晚间快报里引擎A的日线/周线信号是过期的。修复后日线数据 400→401 根，最新到当天，日线趋势与引擎B一致。
2. **【严重】`fetch_zsxq.py` 的 `norm_topic` 图片/附件提取 bug**：Skill 通道（zsxq-cli `topics_brief`）结构里 `images`/`files` 在**顶层**（`talk` 字段为 None），但代码只从 `body=t['talk']` 里取，导致 **Skill 通道星球（基业长青+、卫斯李、Truth and Justice）的图片正文全部丢失**。已加顶层兜底：`body` 取不到时从顶层 `t` 取。验证：Skill 通道 7 张图可正确提取。Cookie 通道（嵌套 talk）不受影响（body 已取到则不触发兜底）。
3. **【中等】`run_000001_chansignal.py` HTML 面板日期硬编码 `'2026-08-14'`**：信号面板副标题写死日期，已改为动态 `{TODAY}`。
4. **【中等】`anonymize_report.py` 硬编码 8/19 路径**：无法复用，已参数化（`python anonymize_report.py [YYYY-MM-DD]`，默认今天）。

已废弃脚本（不再被定时任务调用，硬编码日期不影响运行）：`backtest_*.py`、`gen_evening_report.py`、旧 `run_000001.py`（单级别版）。

## 九、fetch_zsxq.py 分页 bug（2026-08-21 重跑暴露，已修复）

重跑抓取验证图片提取修复时，又暴露第 5 个 bug：**无分页 + limit 上限 30**。

- **现象**：13:55 重跑 morning 窗口时，基业长青+ 从早上 28 条 → 0 条。原因是重度发帖星球在 9:00 后发了 30+ 条新帖，`limit=30` 只取最新 30 条，把昨晚窗口内容挤出。
- **根因**：`zsxq-cli` 的 `--limit` 上限是 30（1-30，超了报"无效的count"）；Cookie 官方 API `count` 上限约 20。之前无分页，单页取不完重度星球的窗口内容。
- **修复**：`fetch_skill`/`fetch_cookie` 加分页循环（`--end-time` / `&end_time=` 翻页），直到最后一条早于窗口开始时间；按 `topic_id` 去重防边界重复。
- **修复后数据对比**（morning 窗口）：

| 指标 | 修复前（无分页）| 修复后（分页）|
|------|---------------|--------------|
| 总窗口内 | 48 条 | **60 条** |
| 基业长青+ | 28 条 | **40 条** |
| 图片 | 24 张 | **52 张** |
| 附件 | 4 个 | **100 个** |

- **结论**：早上的晨报其实漏了 12 条帖子、28 张图（卫斯李 22 张全漏）、96 个文件附件（基业长青+ 的 PDF 分享全漏）。修复后数据才完整。
