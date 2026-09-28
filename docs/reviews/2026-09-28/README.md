# 2026-09-28 审查记录：交互、性能、规则（简单易用）

基线：`main` @ `c14701f`，工作区干净，代码版本 0.2.8。本轮只写评审文档和复现脚本，没有改动产品代码。

基线检查：`mise exec -- uv run pytest -q` 为 **682 passed、1 skipped**（115 秒），与 2026-09-27 结果一致。

## 结论

前几轮已经解决了布局溢出、摘要不一致和批量决定等问题。这次的问题集中在三处：

1. **主流程有误导，还会误触发分析。**
   - 合并设置窗口的主按钮写着“继续选择转换方向”，点下去却直接开始分析；方向选择藏在第二个标签页。
   - 在“筛选文件”框按 Enter 会直接开始分析（真实 Qt 已复现）。
   - 应用前必须决定每一项，但“接受其余项”藏在“更多…”里的 7 个相似入口中。
   - “更多…”里的“接受全部文件”一次点击就会覆盖用户手动跳过的项。
2. **规则有几处会让普通书籍分析失败，或者写出错误结果。**
   - 自带的“整理空格”正则模板，用在 60 章、每章 10 处双空格的普通书上，会让整次分析中止。原因是命中计数把重叠候选也算了进去，而且按整本书累计。
   - 在默认规则集里新加的规则，方向默认是“任意方向”。s2t 时加的“里→裡”，以后做 t2s 也会生效，写出“公裡”。
   - 两个规则集之间的冲突，在规则窗口和导入预览里都看不到，等到分析时才整体失败。
   - 从 TSV 导入的更正规则永远不会生效，因为隐藏的语义版本 V1/V2 排在范围之前比较，导入预览却显示“冲突 0”。
3. **性能：大书和大量规则时有平方级或线性放大。**
   - 打开预览前，主线程上的 `_diagnostic_records` 随单个文件的规模平方增长。10 个文件、每个 480 段时需要 13.7 秒。
   - 2,000 条字面规则时，`plan()` 需要 15.2 秒，无规则时 3.3 秒。原因是每个文本片段都要扫描全部规则，而构建好的前缀索引从未被使用。
   - 在“只看待决定”的筛选下，每点一次接受要 141 ms。
   - 5.5 MiB 的书，计划要占用 240 MiB 内存。

**最不合理的五个地方：**
- “继续选择转换方向”按钮会直接开始分析。
- “本次启用此规则集”其实是写进文件、对所有方案永久生效的开关。
- 只是切换到另一个规则集看一眼再保存，它就被加入了本次转换。
- 自带模板在普通书上会失败，而沙箱里测试总是通过，因为沙箱每次都用新的预算。
- 同一个“未决定”状态，在预览窗口里有“待决定/待定/未决/未处理”四种叫法。

## 文档

| 文件 | 内容 |
| --- | --- |
| [01-interaction.md](01-interaction.md) | 交互与易用性：UXS-01 至 UXS-11 |
| [02-performance.md](02-performance.md) | 性能：PERF-01 至 PERF-07 |
| [03-rules.md](03-rules.md) | 规则语义、正确性与易用性：RULE-01 至 RULE-15 |
| `scripts/ux/` | 真实 Qt 探针：控件计数、Enter 行为、规则窗口可视区 |
| `scripts/perf/` | 合成大书基准。必须整个目录一起使用，因为各脚本共用 `synthetic_book.py` |
| `scripts/rules/` | 规则复现脚本，每个脚本对应一条 RULE |
| `evidence/` | 基线输出：`rules/*.out`、`perf/*.json`、`ux/ux_probe.json` 及截图 |

## 合并与去重

三份子评审中有重叠。以下编号只在一个地方描述，另一处只留引用：

| 保留条目 | 合并进来的 | 原因 |
| --- | --- | --- |
| RULE-01（03） | PERF-04 | 同一个 `RegexBudget`：命中计数方式和整书时间预算一起重新定义 |
| PERF-01（02） | RULE-16 | 同一个字面规则前缀索引 |
| RULE-11（03） | UXS-05、RULE-12 的“本次引用”部分 | 规则集的“本次使用”和“全局启用”是同一个问题 |

## 执行顺序（给执行模型）

每个批次单独提交，提交主题用括号里的写法。每批做完都要运行下文“每批通用验证”，全部通过后再进入下一批。上一批没过，不要开始下一批。

| 批次 | 条目 | 依赖 | 建议提交主题 |
| --- | --- | --- | --- |
| 1 | RULE-10 | 无 | `fix: default new rules to the current direction` |
| 2 | RULE-01（含 PERF-04） | 无 | `fix: count only applied regex hits and scale run budget` |
| 3 | UXS-02 → UXS-01 | 无 | `fix: keep filter Enter from starting analysis`；`fix: show direction and honest analyze label` |
| 4 | RULE-13 | 无 | `fix: inspect the visible selected rule` |
| 5 | RULE-05 → RULE-02 | RULE-02 会让跨版本的同源异目标变成阻断冲突，必须先由 RULE-05 让冲突在规则窗口里可见 | `feat: show conflicts across run rulesets`；`fix: rank scope before semantic version` |
| 6 | PERF-02 | 无 | `perf: index diagnostic spans per file` |
| 7 | PERF-01 | 批次 2（同一个 `matching.py`；等价测试必须在新预算语义上跑） | `perf: prefilter literal rules by prefix index` |
| 8 | UXS-03 | 无 | `feat: resolve remaining preview items from one entry` |
| 9 | RULE-06 → RULE-07 → RULE-08 → RULE-09 | 依次修改 `importers.py` | 每条一个提交 |
| 10 | RULE-11 → RULE-12 → UXS-06 → RULE-14 | UXS-06 的“规则集设置”对话框要放 RULE-11 移出来的全局开关 | 每条一个提交 |
| 11 | RULE-03 → RULE-15 → RULE-04 | RULE-04 的沙箱 trace 要反映 RULE-03 的新行为 | 每条一个提交 |
| 12 | PERF-05 → PERF-03 → PERF-06 → PERF-07 | PERF-03 改动 models，做完必须跑全量 `make check` | 每条一个提交 |
| 13 | UXS-07 → UXS-08 → UXS-09 → UXS-10 → UXS-11 | UXS-10 第 1 步依赖批次 3 的合并窗口布局 | 每条一个提交 |
| 14 | UXS-04（统一术语） | 放在最后，一次性统一前面各批新增的文案 | `fix: use one term per concept in catalogs` |

P1 条目：RULE-10、RULE-01、UXS-02、UXS-01、RULE-05、RULE-02、PERF-02、PERF-01、UXS-03、RULE-06、RULE-11。其余为 P2/P3。

## 我已替你做的产品决定（如不同意，先改这里再交给执行模型）

| 编号 | 决定 | 涉及条目 |
| --- | --- | --- |
| D1 | 正则命中只计**已采用**的匹配，上限为：单规则单文本片段 512，整次分析 100,000。候选数只作内存保护，上限为单规则单文本片段 20,000，不设整书上限。整次运行时间预算改为 `3 s + 2 s × 每百万个已扫描字符`，同一段文本在同一阶段只计一次，不按规则数重复计。单次搜索 50 ms 超时和候选输出字符上限 2,000,000 保持不变 | RULE-01 |
| D2 | 同一起点的候选排序中删除语义版本维度：候选全是 V1 时用 V1 范围表，否则统一用 V2 范围表。跨版本的同源异目标变为阻断冲突 | RULE-02 |
| D3 | 运行时遇到零长度正则匹配时跳过并给出诊断，不再中止整次分析。保存时的校验不放宽 | RULE-15 |
| D4 | 文件范围去掉“单个文件”模式，只剩 3 个选项。只在 UI 中去掉，core 里的 `Scope.SINGLE` 保留 | UXS-07 |
| D5 | “更多…”菜单删除 6 个“本文件/筛选/全部”的一键批量入口，统一走批量对话框 | UXS-03 |
| D6 | 历史 index 改为紧凑 JSON，不再缩进，因此不便人工阅读 | PERF-07 |
| D7 | 新规则默认使用当前方向；“任意方向”只能逐条显式选择，并显示反向警告 | RULE-10 |

## 全局约束（每一条都适用）

1. 不可妥协项见 [INVARIANTS](../../OpenCCForSigil_Spec_v1.4/INVARIANTS.md)，架构见 [architecture](../../architecture.md)，隐私见 [privacy](../../privacy.md)。
2. 转换结果、保护区间、源偏移、原子组都不能变，除非条目明确要求。
3. Apply 仍要求没有待决定项；不增加任何自动接受。
4. 新增或修改的文案必须同时改 `plugin/OpenCCForSigil/resources/i18n/{en,zh-Hans,zh-Hant}.json` 三份文件。新文案按下面的术语表写，不要等到 UXS-04 再统一：

   | 概念 | zh-Hans | zh-Hant | en |
   | --- | --- | --- | --- |
   | 未决定的变更 | 待决定 | 待決定 | Undecided |
   | Profile | 方案 | 設定檔 | Profile |
   | 内置署名规则 | 内置署名保护 | 內建署名保護 | Author-credit protection |
   | 规则沙箱 | 规则测试 | 規則測試 | Rule test |
   | Checkpoint | 检查点（首次出现写“Checkpoint（检查点）”） | 檢查點 | Checkpoint |

5. 日志、历史、偏好中不能写入正文、搜索词或规则测试输入。
6. 不修改版本号，不打标签，不发布。只在当前会话的用户要求时提交和推送。
7. 不要改签入的旧证据（`docs/reviews/2026-09-2*/evidence/`）。前几轮探针脚本因为入口变化需要调整时，只能更新入口，不能降低断言。
8. 没有真实 Sigil 环境时，宿主相关验收写 `Not verified`，不要写成通过。

## 每批通用验证

```sh
make check
QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python \
  docs/reviews/2026-09-27/ui-workflow/scripts/check_ui_acceptance.py --verify \
  --width 960 --height 640 --output /tmp/opencc-ui-acceptance
```

两条命令都必须退出 0，第二条的 `acceptance.json` 里不能有 FAIL。

每条完成后，把结果追加到本目录的 `04-implementation-results.md`，包括：提交 SHA、测试结果、条目中的验收勾选情况、基准前后数字、未完成项，以及宿主状态（`Not verified` 或实测结果）。

## 复现脚本用法

所有命令都在仓库根目录执行。

```sh
# 规则（纯 Python，大多数几秒内完成）
mise exec -- uv run python docs/reviews/2026-09-28/scripts/rules/rule01_regex_hit_budget.py

# 性能（合成书，只读，不写 Sigil、用户目录或历史）
mise exec -- uv run python docs/reviews/2026-09-28/scripts/perf/benchmark_book_pipeline.py --output /tmp/opencc-pipeline.json

# 交互（真实 Qt）
QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python \
  docs/reviews/2026-09-28/scripts/ux/probe_ux_simplicity.py --output /tmp/opencc-ux
```

注意：
- 退出码 0 只表示脚本跑完了，不表示问题已修复。每条的“验收标准”写明了应当看到的输出。
- 修复前的输出保存在 `evidence/` 中，不要覆盖。
- `scripts/perf/benchmark_rules_book.py` 的 `indexed` 模式、以及部分 probe 里的原型模式，是对 `c14701f` 源码的 monkeypatch。修复落地后只能使用 `--modes current` 或默认模式，并对照文中记录的 digest。

## 已检查、没有问题的部分（不必重复）

- **启动：** 第一次构造 OpenCCBackend 0.10 s；模块导入 85 ms；Jieba 探测是异步的。
- **分析线程：** worker 分析期间，主线程进度回调间隔最大 85 ms，界面不冻结。
- **不重复转换：** 不重复 tokenize；每个 target 只调用一次 OpenCC；Apply 和 verify 不再调用 OpenCC。
- **预览交互：** 无筛选时接受当前项 5.7 ms；全部接受 30 ms；首次 show 0.04 s。
- **按键：** 预览表格上按 Enter 不会接受或应用；Esc 的草稿保护正常；A/S/N 只在表格内生效。
- **Checkpoint：** 应用前的 Checkpoint 确认是规格要求，不属于确认过多。
- **规则边界：** CJK Ext-B、emoji、`source == target`、同阶段不级联、BOM/CRLF、V1 TSV 往返、属性转义、字面规则不跨行内标签——均正常。
- **i18n 键：** 三份 i18n 的键集合一致，各 689 个。
