# 2026-09-29 复核：2026-09-28 方案的落实情况、剩余工作、可删除的复杂边界

基线：`main` @ `6d74b25`，版本 0.2.10，工作区干净。本轮只写了评审文档、复现脚本和证据，没有改动产品代码。

基线检查：`make check` 全部通过。
- Ruff 通过；pytest **775 passed、1 skipped**（120 s）。
- vendor manifest 通过；OpenCC 差分 28 例、Jieba 差分 10 例全部一致；插件元数据校验通过（0.2.10）。
- 真实 Qt 验收 `check_ui_acceptance.py --verify --width 960 --height 640`：13/13 PASS。

本机：macOS 26.5.2，Apple M4 Pro。Sigil 宿主上的验收：**Not verified**。

**决定状态：** 2026-09-29，所有待拍板的项目都已按本文的推荐定下来，见下文“已拍板的决定”。执行模型不需要再等待任何决定。

## 结论

2026-09-28 方案共 32 条（UXS 10 条、PERF 7 条、RULE 15 条），另有“其他观察”一节。执行记录（`../2026-09-28/04-implementation-results.md`）写的是“全部完成”，这个结论不准确。

- **主体都落地了。**
  - 13 条完全达到验收标准。
  - 11 条基本完成，只剩文案、测试强度或验证工具的小尾巴。
  - 2 条（UXS-08、PERF-05）有验收项没达标。
  - 6 条（RULE-05、06、07、10、11、12）的新代码带进了缺陷。
  - 所有“不要做”条目中，只有 RULE-11 的“未经确认不写入已保存的方案”被违反一次（见 FIX-05）。
- **新代码带进来 3 个 P1 缺陷，其中 1 个会丢数据。现有测试都没覆盖到：**
  1. 本次引用的规则集之间有冲突时，点“分析并预览”**完全没有反应**。异常逃出 Qt 槽函数，没有任何提示（FIX-01）。
  2. 删除规则集 X 后，在保存前又新建或改名出一个 X，保存时 **X.json 会被删掉，里面的规则全部丢失**（FIX-02）。
  3. 重命名一个本次使用的规则集后，它在窗口里显示为“不用于本次转换”，跨规则集冲突随之消失，“保存”重新可用；真正分析时才整体失败（FIX-03）。
- **另有 2 处相对 0.2.8 的回归：**
  1. TSV 导入改用 `str.splitlines()` 后，在 U+2028、U+2029、NEL 和 `\x0c` 处也会断行。规则被截断后仍会静默导入（FIX-08）。
  2. 3 列、方向栏为空的 TSV 行，以前使用对话框里选的方向，现在报错（FIX-07）。
- **执行记录有 3 处与实测不符，需要更正（FIX-12）：**
  1. 完整的 `benchmark_book_pipeline.py` 能跑完：本机 162 s。
  2. PERF-06 的“macOS 27.0 对 26.5.2”解释不成立：本机就是 26.5.2。实际情况是比例达标，但绝对阈值只在低负载时达标。
  3. 2026-09-28 的两个验证探针（`probe_ux_simplicity.py`、`probe_rules_viewport.py`）在 HEAD 上会崩溃，UXS-02 的验证命令因此跑不起来。另外 `rule05`、`rule11` 两个复现脚本的入口已经过期：`rule05` 跑出来的结果是错的，`rule11` 的第二段变成了永远不会失败的桩。
- **复杂度没有降下来。**
  - 决定一条规则是否生效的开关仍是 7 个。
  - 同一起点的隐含排序仍有 5 层。
  - `ui/preview_window.py` 有 4,533 行，约 45% 与预览无关。
  - 已确认可以直接删掉的死代码约 1,250 行，见 [03](03-simplification.md) 的 A 组。

## 文档

| 文件 | 内容 |
| --- | --- |
| [01-acceptance-audit.md](01-acceptance-audit.md) | 2026-09-28 方案 32 条逐条验收：每个勾选项的状态和证据，以及对执行记录的更正 |
| [02-remaining-fixes.md](02-remaining-fixes.md) | 剩余工作 FIX-01 至 FIX-18：未完成的验收项、新引入的缺陷、坏掉的验证工具，每条都可以直接执行 |
| [03-simplification.md](03-simplification.md) | 可删除的复杂边界 SIMP-01 至 SIMP-32。本轮执行 29 项：A 组（01–10）、B 组中除 SIMP-17 外的 11 项、C 组的 SIMP-23 至 SIMP-30；不做的是 SIMP-17、SIMP-31、SIMP-32 |
| `scripts/rules/`、`scripts/perf/`、`scripts/ux/` | 复现脚本。每个脚本对应一个 FIX 或决定，文件名带编号 |
| `evidence/` | 在 `6d74b25` 上跑这些脚本得到的输出，也就是修复前的状态。不要覆盖 |

## 32 条落实总表

状态说明：
- **完成**：全部验收项达标。
- **基本完成**：验收项达标，但有小尾巴，例如测试偏弱、文案、验证工具。
- **部分完成**：有验收项没达标。
- **有缺陷**：新代码引入了 bug。

| 条目 | 状态 | 剩余问题 | 去向 |
| --- | --- | --- | --- |
| UXS-01 方向前置、按钮如实 | 完成 | — | — |
| UXS-02 筛选框 Enter 不再开始分析 | 基本完成 | 行为已修；计划指定的验证探针崩溃 | FIX-12 |
| UXS-03 “处理剩余 N 项” | 基本完成 | 批量处理后提示“涉及 0 个组”；无可处理项时按钮显示“处理 0 项修改” | FIX-11 |
| UXS-04 一个概念一种叫法 | 基本完成 | 遗留“沙箱输出”；zh-Hant“已寫入/未寫回”混用；V2 标签三种语言不一致 | FIX-13 |
| UXS-06 规则窗口首屏 | 完成 | 探针 `probe_rules_viewport.py` 崩溃 | FIX-12 |
| UXS-07 范围只剩 3 项 | 基本完成 | 缺计划要求的“不改动直接接受 → SELECTED”断言 | FIX-17 |
| UXS-08 结果框只显示非 0 行 | **部分完成** | 取消已改为一行；成功结果仍有“已写回：0 个文件”“已跳过 0 项”“没有建议变更：0 个” | FIX-11 |
| UXS-09 NAV 开关不再灰显 | 完成 | — | — |
| UXS-10 语言选择挪走、Jieba 按需显示 | 完成 | — | — |
| UXS-11 表格列宽、来源名称 | 完成 | — | — |
| PERF-01 字面规则前缀索引 | 基本完成 | 随机等价测试里的随机规则永远不命中；多加了 3 条测不出收益的快路径 | FIX-17、SIMP-07 |
| PERF-02 诊断索引 | 基本完成 | 计划外把诊断页改为打开时才构建，打开前标签不显示数量 | FIX-18 |
| PERF-03 计划内存 | 基本完成 | slots 测试没有断言 `replace()` | FIX-17 |
| PERF-04 正则整书预算（并入 RULE-01） | 完成 | — | — |
| PERF-05 状态筛选下的决定 | **部分完成** | 单项和“本文件”达标；**有分组的项**在状态筛选下每次单击仍重建 O(N) 行映射（39.6 万行时 54–61 ms，目标 25 ms） | FIX-10 |
| PERF-06 汉字计数、比较去重 | 基本完成 | 比较次数和 digest 达标，同机提速约 9%；绝对阈值只在低负载下满足；执行记录的解释有误 | FIX-12 |
| PERF-07 紧凑历史 index | 完成 | 高负载时单次超标，低负载下达标 | — |
| RULE-01 正则命中只计已采用的 | 完成 | D1 的两个边界：大量短片段 × 多条正则；10 万段的长篇触到整次 10 万命中上限 | SIMP-23（D8：删除整次限额） |
| RULE-02 去掉隐藏版本维度 | 完成 | V1/V2 两张范围表会互相翻转；V2 的范围顺序与 spec §11.2 相反，也没有记入 deviations；`precedence_key` 未删 | SIMP-24（D9：只用 §11.2 的顺序）、SIMP-04 |
| RULE-03 更短的覆盖规则不被连带淘汰 | 完成 | — | — |
| RULE-04 最左优先的说明与 trace | 完成 | — | — |
| RULE-05 跨规则集冲突可见 | **有缺陷** | 分析时的冲突被静默吞掉（P1）；切到无关规则集后“保存”又可用；复现脚本入口过期 | FIX-01、FIX-04、FIX-12 |
| RULE-06 两列表格与批量添加 | **有缺陷** | 首字段是表头词的数据行被静默丢弃；3 列空方向行回归；批量添加会生成 `*` 规则；指南没写文件导入的 2/3 列格式 | FIX-06、FIX-07 |
| RULE-07 TSV 不再按 CSV 解析引号 | **有缺陷** | `splitlines()` 回归 | FIX-08 |
| RULE-08 物理行号 | 完成 | — | — |
| RULE-09 JSON 导入不改写归属 | 基本完成 | TSV/CSV/TXT 导入仍然同时写入方案归属和书籍归属 | FIX-15 |
| RULE-10 新规则默认当前方向 | **有缺陷** | 在 s2t 会话里保存 default 集后，它的 `default_direction` 被固化为 s2t，下次 t2s 会话仍预选 s2t；删除一条 `*` 规则后，下一条会继承 `*` | FIX-06 |
| RULE-11 “本次使用”与“全局启用”分开 | **有缺陷** | 重命名后本次引用脱节（P1）；确认“加入方案”时，把用户没被问过的移除也写进了方案（违反“不要做”）；`rule11` 脚本第二段变成了桩 | FIX-03、FIX-05、FIX-12 |
| RULE-12 删除规则集 | **有缺陷** | 删除后在保存前复用同一个 ID，会丢数据（P1）；“默认规则集不能删除”的说明在菜单里看不到；偏好中留下悬空引用 | FIX-02、FIX-14 |
| RULE-13 词典检查取可见行 | 完成 | — | — |
| RULE-14 其他书/方案的归属 | 基本完成 | 顶部提示点开后会带出无关规则；窗口内改绑没有清掉另一个归属字段 | FIX-15、SIMP-22（删除该提示，FIX-16 不做） |
| RULE-15 零宽匹配只跳过这一次 | 基本完成 | 诊断按文本片段发，不是按规则汇总；预览中显示为“其他诊断：REGEX_ZERO_WIDTH_SKIPPED：1 处” | FIX-09 |
| 其他观察（3 项） | 未做 | 实体说明、`precedence_key`、TSV 导出顺序 | FIX-18、SIMP-04 |

## 执行顺序（给执行模型）

- 每个批次单独提交，提交主题用括号里的写法。
- 每批做完都要运行下文的“每批通用验证”，全部通过后再进入下一批。上一批没过，不要开始下一批。
- 标为“不做”的条目（FIX-16、SIMP-17、SIMP-31、SIMP-32）一律跳过。

| 批次 | 条目 | 依赖 | 建议提交主题 |
| --- | --- | --- | --- |
| 1 | FIX-02 → FIX-03 → FIX-01 | 无。FIX-02 丢数据，最先做；FIX-03 与 FIX-02 改同一段 `edit_rules` | `fix: never delete a rule set that is saved in the same result`；`fix: keep run membership across rule set renames`；`fix: report rule conflicts before analysis` |
| 2 | FIX-04 → FIX-05 → FIX-06 | 批次 1 | 每条一个提交 |
| 3 | FIX-07 → FIX-08 → FIX-15 | 无。三条都改 `rules/importers.py`，按顺序做 | 每条一个提交 |
| 4 | FIX-09 → FIX-10 | 无 | 每条一个提交 |
| 5 | FIX-11 → FIX-13 → FIX-14 | FIX-13 放在 FIX-11 之后，统一检查新文案。FIX-16 不做，由 SIMP-22 取代 | 每条一个提交 |
| 6 | FIX-12 → FIX-17 → FIX-18 | 批次 1–5。FIX-12 要在修复落地后重跑探针和基准 | 每条一个提交 |
| 7 | 03 的 A 组：SIMP-01 至 SIMP-10 | 批次 1–6。SIMP-02 会删掉 FIX-10 不再涉及的“本文件”路径 | 每条一个提交 |
| 8 | 03 的 B 组：SIMP-11 → 12 → 13 → 14 → 15 → 16 → 18 → 19 → 20 → 21 → 22（不做 SIMP-17） | 批次 7。SIMP-12 依赖 SIMP-01；SIMP-18 第 2 项要在 FIX-06 之后 | 每条一个提交 |
| 9 | 03 的 C 组：SIMP-23 → 24 → 30 → 25 → 26 → 27 → 28 → 29（不做 SIMP-31、SIMP-32） | 批次 8。SIMP-25 依赖 SIMP-18 第 2 项；SIMP-26 依赖 SIMP-01；SIMP-28 依赖 SIMP-13 | 每条一个提交 |

P1 条目：FIX-01、FIX-02、FIX-03。其余为 P2/P3。

## 已拍板的决定（2026-09-29，全部按推荐）

| 编号 | 问题 | 结论 | 执行条目 |
| --- | --- | --- | --- |
| D8 | 正则的 3 个整次分析限额（总时间 3 s + 2 s/百万字符、总命中 100,000、已采用输出 2,000,000）会让合法的大书失败，而沙箱永远触发不到它们 | **删除这 3 个整次限额**。保留单次搜索 50 ms、每条规则每片段 512 次命中、每片段 20,000 个候选；候选输出上限改为按片段计 | SIMP-23 |
| D9 | V1/V2 两张范围表：V1 是书 > 全局 > 方案（与 spec §11.2 一致），V2 是书 > 方案 > 全局（与 §11.2 相反）；混用时胜负会非局部翻转 | **只保留 §11.2 的顺序（书 > 全局 > 方案）**，删除 V2 表；V2 放宽的 source 校验保留，并记入 deviations | SIMP-24 |
| D10 | 规则窗口保存时是否继续问“把规则集 X 加入方案 Y？” | **保留这个问题**，但回答“是”只写入新增的规则集，不写入移除 | FIX-05 |
| D11 | 03 的 B 组 12 项（用户能看到的功能或兼容行为） | **做 11 项，SIMP-17（中转链改固定链）不做**，因为还不确定是否有人依赖 t2s 的其他 4 条链 | SIMP-11 至 SIMP-22，除 SIMP-17 |
| D12 | 用真 PySide6 offscreen 替换 fake_qt（新增 342 MB 开发依赖，CI 要加 Qt 运行库） | **本轮不做** | SIMP-31 不做 |
| D13 | C 组其余条目：SIMP-25 至 SIMP-30 | **按 03 的建议执行**。SIMP-26 撤销 2026-09-28 的 D4“core 保留 `Scope.SINGLE`”；SIMP-25 保留 `RuleSet.enabled` 字段，只改界面；SIMP-30 删除旧版带引号 TSV 的警告 | SIMP-25 至 SIMP-30 |
| D14 | SIMP-32 拆分 `ui/preview_window.py` | **本轮不做**，A、B、C 三组完成后单独评估 | SIMP-32 不做 |
| D15 | 有些已批准的删除会让旧验收探针里“该功能存在”的检查失败，已知的是 SIMP-18 第 5 项、SIMP-20、SIMP-28 | **允许把这些检查改为“该功能不存在”或改查新位置**，规则见全局约束 13。其他已批准条目遇到同样情况也照此办理 | SIMP-18、SIMP-20、SIMP-28 等 |

## 全局约束（每一条都适用）

沿用 [2026-09-28 README](../2026-09-28/README.md#全局约束每一条都适用) 的 8 条全局约束，包括术语表、隐私、不改版本号、宿主写 `Not verified`。另外补充 6 条：

9. **不要改签入的旧证据**（`docs/reviews/2026-09-2*/evidence/`，包括本目录的 `evidence/`）。
   - 修复后重跑复现脚本，输出写到 `/tmp/`，然后与 `evidence/` 对照。
   - 前几轮的探针因入口变化需要调整时，只能改入口，不能降低断言。
10. **旧记录只追加，不改写。** `../2026-09-28/04-implementation-results.md` 里需要更正的地方，在文件末尾追加一节“2026-09-29 更正”，不要改原来的行。
11. **每条修复都必须带一个会失败的测试。**
    - 先写测试，在修复前的代码上确认它失败，再改代码。
    - 提交说明里写上“修复前失败的测试：<测试名>”。
12. **只做已批准的条目。** 标为“不做”的条目（FIX-16、SIMP-17、SIMP-31、SIMP-32）一律跳过，并在 `04-implementation-results.md` 中写“按 2026-09-29 决定不做”。
13. **被批准删除的功能，允许改写旧探针里对应的检查，但只限下列两种改法：**
    - 把“X 存在或可见”改为“X 不存在”；
    - 功能挪了位置时，把检查改到新位置，检查的内容不变。

    不能删掉检查，也不能放宽与该功能无关的断言。每处改写都要在提交说明里写明“按 D15 改写：<文件:行> 原断言 → 新断言”。
14. **偏离 spec 的删除要记入 `docs/deviations.md`。** 在“Deliberate implementation choices”一节追加一条英文说明，写明 spec 章节号。涉及的条目：SIMP-21（§86）、SIMP-24（§11.8.3）、SIMP-27（§8 数据模型）、SIMP-28（§6.1、§6.2）、SIMP-29（§15）。不要修改 `docs/OpenCCForSigil_Spec_v1.4/` 下的文件，也不要修改 INVARIANTS。

新增或修改的文案必须同时改 `plugin/OpenCCForSigil/resources/i18n/{en,zh-Hans,zh-Hant}.json` 三份，并遵守 2026-09-28 的术语表。补充两个词：

| 概念 | zh-Hans | zh-Hant | en |
| --- | --- | --- | --- |
| 写入书籍 | 写回 | 寫回 | written |
| 规则测试的输出 | 测试输出 | 測試輸出 | Test output |

## 每批通用验证

```sh
make check
QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python \
  docs/reviews/2026-09-27/ui-workflow/scripts/check_ui_acceptance.py --verify \
  --width 960 --height 640 --output /tmp/opencc-ui-acceptance
```

- 两条命令都必须退出 0，第二条的 `acceptance.json` 里不能有 FAIL。
- 每条完成后，把结果追加到本目录的 `04-implementation-results.md`（新建），内容包括：
  - 提交 SHA；
  - 修复前失败的测试名；
  - 测试结果；
  - 该条“验收标准”的勾选情况；
  - 复现脚本修复后的输出，与 `evidence/` 对照；
  - 宿主状态（`Not verified` 或实测结果）。

## 复现脚本用法

所有命令都在仓库根目录执行。脚本只使用临时目录，不写 Sigil、用户目录或历史。

```sh
# 纯 Python / fake Qt
mise exec -- uv run python docs/reviews/2026-09-29/scripts/rules/fix02_fix03_ruleset_rename_delete.py

# 文件名以 _qt 结尾的脚本需要真实 Qt
QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python \
  docs/reviews/2026-09-29/scripts/rules/fix01_analyze_conflict_qt.py

# 修复后逐个重跑，与 evidence/ 对照
for f in docs/reviews/2026-09-29/scripts/*/*.py; do
  echo "== $f"
  case "$f" in
    *_qt.py) QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python "$f" ;;
    *) QT_QPA_PLATFORM=offscreen mise exec -- uv run python "$f" ;;
  esac
done
```

注意：
- 退出码 0 只表示脚本跑完了，不表示问题已修复。每条 FIX 的“验收标准”写明了应当看到的输出。
- `scripts/perf/fuzz_prefix_index.py` 约需 140 s，`scripts/rules/d8_regex_tiny_fragments.py` 约需 25 s，其余都在几秒以内。
- 修复前的输出保存在 `evidence/` 中，不要覆盖。

## 已复查、没有问题的部分（不必重复）

- **模糊测试：**
  - PERF-01 前缀索引与全量扫描做了 13,440 段文本（source/pre/post），0 处不一致（`evidence/perf/fuzz_prefix_index.out`）。
  - PERF-05 增量计数做了 400 个种子 × 40 步随机操作，结果与完整重算一致（`evidence/perf/fuzz_incremental_counts.out`）。
- **PERF-01 的缓存：** `unlocked` 按对象身份缓存，LRU 按 overlay 身份加文本缓存，都不会读到过期数据；每个 converter 只服务一次 plan。
- **真实 Qt 场景：** 在筛选框按 Return 或 Enter，以及选了 0/1/2 个文件时，窗口都不关闭；焦点在列表或按钮上时，Enter 仍会开始分析。
- **正则保护：** 单次搜索 50 ms 超时在 HEAD 上仍然生效（`evidence/rules/fix17_regex_timeout.out`：0.066 s 报错）。
- **各条“不要做”：** 除 FIX-05 那一处外都没有违反。其中包括：没有自动接受；没有 Aho–Corasick；没有 QSortFilterProxyModel；没有改 `book_fingerprint()`；没有放宽保存时的正则校验；没有改 schema。
