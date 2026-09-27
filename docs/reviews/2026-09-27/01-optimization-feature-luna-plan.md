# OpenCCForSigil 下一轮优化与功能计划（Luna 执行版）

日期：2026-09-27。审查基线：`main`，`13a0d796106e2c922e8ddb37f93d27b91d200e36`，项目版本 `0.2.6`。

这轮最值得做的是：先修正预览分组语义和 MathML 保护范围，再优化多组批量操作，随后增加预览检索、撤销决定和诊断定位。SVG、方案迁移、审校批注可以做，但放在独立的后续阶段。

**本文是执行规格，不是实现完成报告。** 本次只新增计划、合成复现脚本和基线证据，没有修改插件行为，也没有重新验证远端 Release 或真实 Sigil。

## 1. 可以直接交给 Luna 的执行指令

> 读取本文件和第 2 节约束，以实际检出代码为准，按第 4 节顺序完成核心条目。先运行附带探针，针对 R-01、R-02 写出会失败的正式回归，再修复。新增功能按本文冻结的交互语义实现，不自行增加默认开启的转换能力。每个条目形成独立可审查的变更，运行列出的定向检查；最后执行总验收。将结果写到本目录 `02-implementation-results.md`，每项列出实现、测试、证据和剩余限制。第 9 节候选功能默认不实现。真实宿主条件不足时继续完成可以自动验证的工作，并将宿主项标成 `Not verified`。不要把代码完成、自动测试通过和真实 Sigil 验收混为一个状态。用户已要求在 `main` 上分步骤提交并推送，所有核心批次与验收证据完成后，最后发布准备提交必须作为 `v0.2.8` 的目标节点；E-01 和资产验证通过后再打标签，标签后的 main/tag 不得追加提交。

工作方式：

1. 先核对 `git status --short --branch` 和 `git rev-parse HEAD`，保护现有改动；基线变化时先复查相关实现，不机械照抄旧结论。
2. 每次只做一个条目。旧缺陷遵守“失败测试 → 修改 → 通过”；体验功能先写交互状态表，再加能验证用户结果的测试。
3. 新测试放进正式 `tests/unit/` 或 `tests/integration/`。审查脚本作为复现证据保留，不能代替正式回归。
4. 本轮不引入新生产依赖、不更新原生 payload、不改 CI 平台矩阵。只有实际失败证明相关时才调整检查脚本。
5. 不要求另起代理或并行代理。一个 Luna 按批次执行即可；每批本地验证后单独提交并推送，记录 SHA。自动 CI 不必为每个中间批次等待完整原生矩阵，最终 release candidate 必须通过完整 E-01。

## 2. 必须阅读与保持的边界

先读：

- `docs/OpenCCForSigil_Spec_v1.4/INVARIANTS.md`。
- 同目录 `OpenCCForSigil_Engineering_Spec.md`：§7 文档保护、§18 审校批注、§27 校验、§58 功能分期；以及 `REVISION_NOTES.md`。
- `docs/architecture.md`、`docs/deviations.md`、`docs/privacy.md`、`docs/rules-and-profiles.md`。
- `docs/reviews/2026-09-26/02-implementation-results.md`，避免重做已完成事项。

执行时保持：

- 官方 vendored OpenCC 仍是最终转换结果来源；保留上下文，不能拆碎输入来制造性能提升。
- 不重写整个 XHTML/NCX/OPF；只能修改已计划的源区间，其他内容保持原样。
- 预览、筛选、撤销、诊断查看均不能写 BookContainer，也不能重新调用 OpenCC。
- 规则一次出现的替换组不可拆开；跨资源语言标签组也不可拆开；不同出现不能因为规则 ID 相同被合并。
- 来源、规则、Profile、后端信息仍冻结；返回设置或源数据漂移必须废弃旧计划，不能复用旧决定。
- 正文和检索词仅用于本次内存交互。日志、历史、默认导出不能新增正文；完整 diff 仍需用户明确勾选。
- 所有新增用户文案有英文、简体中文、繁体中文版本。fake Qt、真实 offscreen Qt、真实 Sigil 分别记录。

规范与当前代码已有差异，例如单独的 Linux cp312 包、已实现的 regex/pre/post。O-02 负责澄清文档；不要为了迎合旧章节而删掉已实现能力，也不要照抄旧阶段清单认定它们不存在。

## 3. 本次实查基线

### 3.1 已完成的能力，不再作为新功能排期

| 能力 | 当前证据 |
| --- | --- |
| 规则普通文字搜索、按本次生效筛选、稳定 ID 编辑、草稿保护 | `ui/rules_window.py`，上轮 R-08/U-01 与正式测试 |
| JSON 逐条导入诊断、有损导出提示、空目标删除语义 | `rules/importers.py`、`rules/exporters.py`、上轮 R-03/R-04/R-09/R-12 |
| 正则规则、pre/post 替换、输出预算、单次出现决策组 | `rules/matching.py`、`core/converter.py`、`core/planner.py` |
| 后台分析、合作式取消、返回设置重分析 | `core/workflow.py`、`app/controller.py` |
| 预览虚拟表格、懒格式化、下一项待处理、按文件/类别/风险筛选 | `ui/preview_window.py`，`test_preview_model.py` 有 300,000 行测试 |
| NCX、元数据白名单、中文语言标签、历史及 Markdown/JSON 报告 | 对应服务及集成测试已存在 |
| ruby 注音、code/pre、数字中文字符引用的可选处理 | `app/settings.py:tokenizer_policy()`、`ui/run_options.py` 和 tokenizer；不能因 `ruby.py` 是占位文件就判定整项未实现 |

### 3.2 本轮实际运行结果

| 项目 | 结果及边界 |
| --- | --- |
| `make check` | **611 passed, 1 skipped，42.76s**；Ruff、vendor、28 条 OpenCC 差分、10 条 Jieba 差分、插件元数据检查通过。见 [日志](evidence/baseline-check.log) |
| 分组语义与复杂度探针 | 两项分组行为异常，扫描次数呈二次增长；见 [baseline.json](evidence/baseline.json) |
| MathML 探针 | `mathml=False` 无目标；经 `Profile.from_dict()` 加载 `mathml=True` 后，`mi`、`mtext`、`annotation` 均进入可转换目标 |
| 真实 Qt 三语言预览尺寸 | PySide6 6.11.2，macOS arm64，offscreen：初始均 900×620；最小宽 618–689、高 420–434，表格高 276–290。基础尺寸检查通过，不列为布局缺陷 |
| 真实 Sigil | 本轮未执行安装、转换、保存、重开：**Not verified** |

唯一 pytest skip 是已有的假 Qt 规则窗口尺寸检查，不表示宿主验收通过。真实 Qt 截图：[英文](evidence/preview-before/preview-en.png)、[简中](evidence/preview-before/preview-zh-Hans.png)、[繁中](evidence/preview-before/preview-zh-Hant.png)；数据见 [layout.json](evidence/preview-before/layout.json)。英文截图同时显示普通规则组被误标为语言标签组。

复现命令（从仓库根目录运行；输出写到 `/tmp`，不覆盖基线）：

```sh
mise exec -- uv run python docs/reviews/2026-09-27/scripts/probe_followup.py \
  --output /tmp/opencc-followup-probe.json

QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python \
  docs/reviews/2026-09-27/scripts/check_preview_layout.py \
  --output /tmp/opencc-followup-preview --verify
```

探针只使用合成数据和 fake Qt，不打开真实 EPUB 或用户配置；它打印观察结果，**退出码 0 不代表缺陷已修复**。尺寸脚本的 `--verify` 只检查基础几何，不判断分组语义。两个脚本都不能作为真实 Sigil 证明。

## 4. 核心执行顺序

P1 表示会影响用户决定或文档保护的已复现问题；P2 表示有证据的效率或体验改进。工作量 S/M/L 表示相对复杂度，不是耗时承诺。

| 顺序 | ID | 优先级 / 工作量 | 交付 | 依赖 |
| --- | --- | --- | --- | --- |
| 1 | R-01 | P1 / M | 分清规则替换组和语言标签组，修正文件/分组按钮作用范围 | 无 |
| 2 | R-02 | P1 / M | MathML 开启时仍保护数学标识符 | 无 |
| 3 | O-01 | P2 / M | 消除按组批量操作的重复全表扫描 | R-01 |
| 4 | F-01 | P2 / M | 预览状态筛选、文字搜索、来源筛选 | R-01、O-01 |
| 5 | F-02 | P2 / L | 撤销/重做预览决定，恢复未处理状态 | F-01 |
| 6 | F-03 | P2 / M | 可定位的诊断列表，包括没有修改的文件 | F-01 |
| 7 | O-02 | P2 / S | 维护文档状态及运行时矩阵与代码一致 | 上述实现结果 |
| 8 | V-01 | 验收 / M | 自动检查、真实 Qt 与真实 Sigil 证据分层交付 | 上述全部 |

推荐拆成三批：R-01/R-02/O-01；F-01/F-02/F-03；O-02/V-01。若分多次会话，每批先完成验收再继续。

## 5. 缺陷修正与性能优化

### R-01：规则组被当成语言标签组处理

**已复现，不只是文案建议。**

位置：`ui/preview_window.py` 中 `_group_stats`、`_PreviewTableData`、`_groups_for_file()`、`_update_group_controls()`、`_decide_current_file_groups()`、`_accept_file()`、`_reject_file()`、`_decide_filtered()`；分组生成在 `core/planner.py:_absolute_change()`。

基线行为：

- 只有 `rules:…` 组也显示 “Accept language tag group”；列表、详情和反馈也称为语言标签修改。
- “接受本文件”跳过所有有 `group_id` 的项，普通规则替换组因此仍未决定。
- 混合语言组与规则组时，点“接受语言标签组”会同时接受规则组。

**冻结后的按钮语义：**

| 操作 | 普通变更 | 本文件规则替换组 | 跨文件语言标签组 |
| --- | --- | --- | --- |
| 接受/跳过当前项 | 当前项 | 当前这一次出现的完整组 | 整个语言组，明确提示涉及文件数 |
| 接受/跳过本文件 | 本文件全部 | 本文件全部规则组 | 仍留给专门语言组操作，不受此按钮影响 |
| 接受/跳过语言标签组 | 不影响 | 不影响 | 当前文件关联的完整语言组 |
| 接受/跳过筛选结果 | 当前匹配项 | 匹配项所属完整组 | 匹配项所属完整组，包含隐藏成员 |
| 接受/跳过全部 | 全部 | 全部 | 全部 |

实现步骤：

1. 统一分组类型判定。现有 `language_metadata` 与 `rules:` 来源明确，可先集中成纯辅助函数；不要在多个按钮里散写判断。未知非空组按原子组处理，不伪称语言组。
2. 语言组按钮只在当前文件存在语言组时出现；规则组使用“同次规则替换”文案，并显示修改数。跨文件扩展仍显示涉及文件数。
3. “接受本文件”包含文件内完整规则组。若未来出现跨文件的非语言组，不拆组、不静默决定其他文件；保留待处理并显示原因。
4. 筛选动作执行前计算完整影响集合；若包含隐藏成员，显示匹配数、额外联动数和文件数，在该次批量操作中确认后执行。取消不改变任何决定。
5. 核心 `finalize()` 对不完整组的拒绝仍保留，不能只靠 UI 自律。

正式测试与验收：

- 在 `test_preview_window.py` 覆盖规则组、语言组、两者混合；语言按钮不能决定规则项。
- 在 `test_rules_transform_workflow.py` 使用两个文件、同规则各出现两次；每次替换至少产生两个关联 change。接受当前项只处理一次出现；接受文件处理该文件全部规则组，其他文件不变。
- 筛选隐藏一个组成员，确认时整组同步，取消时整个决定映射不变；全接受/全跳过仍可覆盖先前单项决定。
- 三语言列表、详情、按钮、反馈均不把规则组称为语言组。
- 复跑探针：`rule_only_after_accept_file` 应为接受状态；混合场景语言按钮执行后 `change-1` 仍未决定。探针中规则组专用语言按钮隐藏后，程序化 `.click()` 也不能改变它。

### R-02：MathML 开关不能开放数学标识符

位置：`app/profiles.py:Profile.from_dict()`、`app/settings.py:tokenizer_policy()`、`document/tokenizer.py:_is_protected()` / `_element_is_writable()`。

**已复现的范围：** 默认关闭路径安全；从保存的 Profile 加载 `mathml=True`，`<mi>变量</mi>` 被标记 `convert=True`。本轮证明的是受保护内容进入目标提取路径，没有宣称真实 EPUB 已发生损坏。`test_profiles_m3.py` 已覆盖开启后转换 `mtext`，不能把 MathML 写成“完全未实现”。

目标行为与步骤：

1. 保留默认关闭及已测试的 `mtext` 自然语言支持；`mathml=True` 只允许 MathML `mtext` 的直接文字目标，作为本轮明确的保守范围。
2. `mi`、`mo`、`mn`、`ms`、`annotation-xml` 及其他未列入允许范围的 MathML 内容、所有 MathML 属性保持原样。暂不开放 `annotation`，它需要独立的编码白名单和产品开关，见第 9 节。
3. 允许范围不能绕过外语、script/style、CDATA 和实体保护。`mtext` 下嵌套的数学标识符仍受保护。
4. 按命名空间和继承作用域确认 MathML；覆盖默认命名空间、前缀、前缀重绑定。无法确认时保守跳过，不按任意标签的局部名开放内容。
5. 用户已有 Profile 文件不自动改写。加载后保持 `mathml=True` 取值，但实际含义收紧为上述允许范围；文档说明这是保护范围修正。Profile 摘要说明范围，主设置本轮不新增开关。

验收：

- 正式测试包含 `mtext`、`mi`、`mo`、`mn`、`ms`、`annotation`、`annotation-xml`、属性、前缀和嵌套场景；对真实 namespace 和无 namespace 的历史 `<math><mtext>` 夹具分别定义兼容策略。历史无 namespace 夹具可保留 mtext 行为，但不得放开其他节点。
- 使用 `Profile.to_dict() → from_dict()` 的实际配置加载入口，而非只构造 dataclass。
- 集成测试从 plan → preview → stage → verify，接受全部后仅 mtext 允许区间变化；标识符、属性和其余原始切片逐字节一致。
- 复跑探针，开启时只有 `mtext` 出现在可转换目标中；默认关闭仍为空。整个预览前及查看诊断时写入数为 0。

### O-01：按组批量决定避免 O(组数 × 全部变更数)

位置：`ui/preview_window.py:_decide_group()`、`_decide_filtered()`、`_decide_current_file_groups()`、`_decide_entry()`。

当前 `_decide_group()` 每次遍历 `_entries`；批量操作对每组再次调用。基线探针只计决定阶段，排除了重绘/重算：

| 组数 | 变更数（每组 2 项） | 访问 entry 次数 | 本机耗时（参考） |
| --- | --- | --- | --- |
| 100 | 200 | 20,400 | 0.00085s |
| 200 | 400 | 80,800 | 0.00324s |
| 400 | 800 | 321,600 | 0.01265s |

这是复杂度证据，不能把微秒结果外推为整书加速倍数。现有 300,000 行测试没有覆盖这种“很多个小组”的批量路径。

实现步骤：

1. 初始化预览时一次构建 `group_id → entries`、`file_id → groups` 和稳定行身份索引，保留 group kind。索引只引用冻结 change，不复制正文。
2. 单组决定只访问该组成员；批量操作先收集 group ID 并去重，再一次决定所有成员。R-01 的跨文件保护和操作影响范围不变。
3. 单组只增量更新实际改变的状态和计数；全局批量可进行一次线性重算，不允许每组全表重算。
4. 保留现有懒格式化和虚拟表格。不要重建所有单元格，亦不要把 OpenCC 移入预览。

验收：

- 新建 `tests/unit/test_preview_group_scaling.py`；用操作计数证明初始建索引 O(N)、单组访问 O(组大小)、全组批量 O(N + G)。2,000 个双成员组的批量决定访问上限可定为 `10 × N`，不依赖机器速度。
- 测试单组只改对应成员、计数与全量重算一致；普通项、规则组、跨文件语言组混合后仍正确。
- 基准扩至 1,000/2,000/4,000 个双成员组，每档至少三次取中位数。计时记录环境，但不新增类似 `<0.05s` 的 CI 断言。
- 原有 300,000 行构建/过滤/全接受测试继续通过；不借此条目做无关性能重构。
- 若调整内部 API，使探针计数包装不再适用，同步维护探针并保留基线，不能删除失败场景或把扫描隐藏到未计数的等价全表循环。

## 6. 本轮新增功能

### F-01：预览只看待处理、按文字和来源找修改

现状：预览 UI 只有文件、类别、风险；核心 `PreviewFilter` 已有 `rule_source`，但 UI 没接。规则管理器中的搜索是另一个窗口，不等于本功能已实现。

位置：`core/preview.py`、`ui/preview_window.py:_current_filter()` / `_visible_entries()` / `_refresh()`、相关 i18n JSON。

冻结的最小范围：

1. 状态筛选：全部（默认）/ 未处理 / 已接受 / 已跳过；来源筛选：全部及本次出现的具体 `rule_source`，标签本地化、数据使用原 ID。
2. 一个普通文字搜索框，搜索完整 source、target、规则来源和文件 href；对 source/target 使用与预览显示一致的实体解码，只影响显示匹配，不改源偏移。英文不区分大小写，不执行正则，不搜索整本正文上下文。
3. 文件、类别、风险、状态、来源、文字查询采用 AND；提供“一键清除筛选”。空查询匹配全部。
4. 显示“可见 N / 总计 M”，保留全局剩余未决定数；明确区分“没有变更”和“没有符合筛选条件的项”。
5. 只看未处理时，接受后该行消失，焦点落到当前位置之后的下一条可见记录；到末尾从头继续；没有记录则清空详情并禁用当前项操作。
6. “接受筛选结果”冻结点击瞬间的匹配集合，一次处理；不能在边改状态边筛选的循环中漏项或多处理项。R-01 的完整组扩展与确认继续生效。
7. 全局仍有未处理项时，隐藏它们不能让 Apply 提前可用。筛选只改变视图。

实现注意：

- 当前 `_refresh(refresh_statuses=True)` 假设决定不影响可见集合。新增状态筛选后必须重审该缓存，不能只刷新状态列。
- 用 `(file_id, change_id)` 保持选择和索引；不要拿可见行号作为业务身份。
- 文字输入可做短延迟合并刷新，测试使用信号/事件驱动而非硬睡眠。检索串只存在内存，不保存到偏好或日志。
- 筛选结果列表可以线性扫描，显示文本仍按需生成；不得为每个查询反复实例化规则引擎或调用 OpenCC。

验收：

- 新建 `test_preview_filters.py`，覆盖中文、英文大小写、空/纯空白查询、带实体的 source、完整长目标、组合筛选、无结果和清除筛选。
- 处理后即刻隐藏、撤销后重新出现（F-02 联动）；选择保持同一 ID，不能误改筛选后占据旧行号的另一项。
- “只看未处理 + 接受筛选结果”对点击时全部匹配项恰好生效一次；隐藏组成员完整同步，其他独立出现不变。
- 在 10,000/300,000 行合成数据中检查无全量格式化，无 OpenCC/regex 调用；记录本机搜索耗时，避免硬毫秒阈值。
- 真实 Qt 三语言检查新增控件、Tab 顺序、输入焦点及无结果状态，保持表格主要空间；多出的筛选控件可以分行或折叠，不能把最小宽度撑大到屏幕外。

### F-02：撤销/重做“预览决定”，允许恢复未处理

现状：`PreviewSession` 只有接受/跳过；已接受与已跳过可以互相覆盖，但不能回到未处理，也没有操作撤销。用户批量误点后只能重新逐项选择或重新分析。

**本功能仅影响尚未写入的预览决定。** 用户文案用“撤销预览操作”，不能承诺撤销 Sigil 已提交的 EPUB。

位置：`core/preview.py`、`ui/preview_window.py`。可新增 `core/preview_commands.py`，但不引入通用事务框架或持久化日志。

实现步骤：

1. 为决定状态提供经校验的读取/恢复接口；可恢复 `None`，拒绝未知 change ID 和非法决定。不让 UI 任意写 `_decisions`。
2. 一次用户点击对应一个操作，记录所有实际受影响 ID 的 before/after 状态。组、文件、筛选、全接受都作为完整的一次操作；不记录没有任何状态差异的操作。
3. Undo 恢复整次 before，Redo 恢复整次 after；撤销后产生新操作清空 redo。跨文件语言组也必须整体恢复。
4. 新增“恢复当前项为未处理”，组内项恢复整个组，并作为可撤销的一次操作；本轮不增加复杂的分支历史或持久化恢复。
5. 增加 Undo/Redo 按钮和平台标准快捷键，详情/搜索框持有焦点时保留文字复制、选择和输入控件自身的撤销语义。不能抢走文本编辑快捷键。
6. 更新总计数、每文件计数、状态筛选可见性、当前选择和 Apply 状态。返回设置、退出、重新分析、成功 Apply 时清空操作历史；旧计划 ID 不能用于新计划。
7. 历史只存 ID 和决定，不复制原文/目标。最多保留 100 个操作、累计 2,000,000 个变更记录；从最旧的完整操作开始淘汰。单次操作若超过预算，至少完整保留最新一次并清掉更旧历史，提供简短提示；不能只保存半个组或只撤销一部分。

验收：

- 新建 `test_preview_decision_history.py`；单项、组、文件、筛选、全部分别做两次 undo/redo，对照完整决定映射和计数。
- 从未处理 → 接受 → 跳过 → undo → undo，应回到未处理；恢复未处理后 Apply 重新禁用。
- 跨文件语言组和每次出现规则组完整恢复；过滤后不可见的成员也恢复。
- 随机操作序列用简单参考状态机对照；每步校验 accepted/rejected/undecided、剩余项、最终 accepted plan。
- 300,000 行全接受的 undo/redo 保持一个完整操作，无正文复制；测试历史淘汰、无效操作、清空 redo 和重分析失效。
- controller/adapter spy 确认这些操作写入数为 0、后端调用数为 0。真实 Qt 验证搜索框输入时快捷键不误触全局撤销。

### F-03：诊断有列表、有位置，零修改也能看

现状：已有 `INLINE_BOUNDARY` 等诊断和摘要/详情展示；本条是把它们变成可检索、可定位的审查入口，不能重复实现诊断算法，也不能声称实现跨行内标签整词转换。

位置：`core/models.py:Diagnostic`、`document/diagnostics.py`、`core/planner.py`、`ui/preview_window.py:_diagnostics_for_file()` / `_show_current()` / `show_result()`、`app/controller.py` 的零变更分支。

目标行为与步骤：

1. 增加可折叠的只读诊断列表：文件、诊断代码的本地化名称、原始行/列、简短说明。数据来自已经冻结的计划，不重新分析，不额外读书。
2. 以文件和诊断代码过滤；至少覆盖跨行内标签边界、引号未配对、混合简繁及当前已有源文件跳过诊断。以实际代码中的诊断为准，不伪造缺失结果。
3. 有源 span 时按冻结源建立每文件行起点索引，显示从 1 开始的原始行/列；CRLF 作为一个换行。位置不可用时写“位置不可用”，不能猜一个行号。
4. 选中诊断，展示其附近纯文本或源码上下文，仅在内存中；若有相关变更可定位到预览项，无对应 change 时仍能查看诊断，不能生成虚假可接受项。
5. 多个 change 对应同一个诊断时按文件/代码/span 去重。没有变更的选中文件仍出现在诊断文件列表。
6. controller 的“零变更”结果窗口提供查看本次诊断入口。诊断可见性不改变退出码、跳过坏文件的既有策略、写入数量或历史完成语义。

验收：

- 两文件夹具：一个产生变更，另一个只产生 `INLINE_BOUNDARY`；列表必须同时有正确文件/位置，点击后不改变任何决定。
- 引号未配对、混合诊断、无 span、同诊断多个关联 change；CRLF、非 BMP 字符、组合字符前后的行列映射均测试。
- 零变更但存在诊断时用户仍可打开列表，关闭后无写入、无额外 OpenCC 调用。
- 默认日志和报告不含新上下文文本；以特征字符串断言。详情用纯文本控件，不能解释书中的 HTML。
- 真实 Qt 验证折叠区、键盘定位、关闭行为；尺寸脚本继续通过。

### O-02：文档中的“尚未完成”及包矩阵更新到同一基线

已核对到的差异：

- `docs/README.md` 仍写五个平台包、六个包、七份资产；当前代码矩阵是一个 Fat + 六个平台 ZIP + 校验清单，共八份资产。
- `docs/performance-interaction-followup.md` 的旧“后续专项”仍列后台分析、返回设置、大列表模型等；实际已经实现，末尾仅补了 worker 说明。
- 稳定规范 INVARIANTS 的 Python 运行时文字没有说明现有独立 Linux x86_64/cp312 例外。
- 阶段清单把 regex 和数字中文字符引用仍列为后续功能；`docs/deviations.md` 的 MathML 总括也没有区分已存在的底层选项与未提供的完整 UI。

实现步骤：

1. 以 `tools/runtime_matrix.py`、`tools/release_assets.py`、`.github/workflows/ci.yml` 为包矩阵来源，修正维护入口，并链接具体 Release 文档；本轮不改变矩阵。
2. 历史测量、旧审查和旧版本 release notes 不改写成新结论。在旧“待做”表旁增加状态日期和实现指向，保留原始测量。
3. 稳定规范的补充在 `REVISION_NOTES.md` 留记录，并同步 Engineering Spec、INVARIANTS 与 `docs/deviations.md` 的相关表述；明确 cp312 是单独的平台包，不能把任意 Python 版本都写成支持。
4. 写一张当前能力表，使用“已实现 / 本轮新增 / 部分底层支持 / 未开放 / 宿主未验收”等准确状态。
5. F-01/F-02/F-03 完成后更新用户操作说明；撤销文案明确只作用于预览决定。

验收：人工对照矩阵、代码和测试，检查 Markdown 链接可达。此类文字同步无需增加镜像实现的测试；不能把“文档写支持”当作兼容性验收。

## 7. V-01：检查命令与真实宿主验收

### 7.1 定向检查

下面前一组测试文件已存在；新测试文件在对应功能实现时创建，不提前建立空测试占位。

```sh
# R-01 / O-01
mise exec -- uv run pytest tests/unit/test_preview_window.py \
  tests/unit/test_preview_model.py \
  tests/integration/test_rules_transform_workflow.py \
  tests/integration/test_extended_documents.py -q

# R-02
mise exec -- uv run pytest tests/unit/test_profiles_m3.py \
  tests/unit/test_xml_targets.py tests/unit/test_source_preserving_pipeline.py -q

# 新增正式回归，实现后必须存在且实际执行
mise exec -- uv run pytest tests/unit/test_preview_group_scaling.py \
  tests/unit/test_preview_filters.py tests/unit/test_preview_decision_history.py -q

# 新文案及控制器零修改/报告路径
mise exec -- uv run pytest tests/unit/test_i18n.py \
  tests/unit/test_history_report_self_test.py \
  tests/integration/test_plugin_conversion.py -q
```

F-03 新增的诊断列表与位置映射测试放进相关正式测试文件，结果表记录实际文件/测试名，不可只运行旧测试后标完成功能。

### 7.2 最终自动验收

```sh
make check

mise exec -- uv run python docs/reviews/2026-09-27/scripts/probe_followup.py \
  --output /tmp/opencc-followup-after.json

QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python \
  docs/reviews/2026-09-27/scripts/check_preview_layout.py \
  --output /tmp/opencc-followup-preview-after --verify

# 保留上轮规则窗口回归，防止通用 Qt/i18n 改动影响它
QT_QPA_PLATFORM=offscreen PYTHONPATH=plugin/OpenCCForSigil mise exec -- \
  uv run --with PySide6==6.11.2 python \
  docs/reviews/2026-09-26/scripts/check_rules_layout.py \
  --output /tmp/opencc-followup-rules-after --verify

make package
make artifact-check
git diff --check
```

尺寸脚本需要随新增控件补充真实 Qt 交互检查：分组按钮作用域、状态筛选后行消失、撤销重现、搜索输入快捷键、诊断跳转。不要把 fake Qt 调用 `_accept_this()` 当成真实点击/快捷键验证。固定相同合成夹具记录三语言截图和检查结果。

本机 `make package` 只含本地可用 payload。没有执行完整原生 CI 时，跨平台自动验收也应写 `Not verified`；不强求在本机伪造 Fat Plugin。

### 7.3 真实 Sigil 操作表

使用可复现的合成 EPUB 副本，先创建 Sigil Checkpoint。Luna 可准备夹具和预期文件，但不得把夹具生成当成宿主通过。

| 场景 | 操作与期望 |
| --- | --- |
| 混合分组 | 两章含同规则多次替换并有语言提案；语言组按钮只改语言，接受当前项只改一次规则出现 |
| 文件批量 | 接受第一章后其规则组全部决定；第二章规则组不变，语言组仍等待专门决定 |
| 筛选 | 未处理 + 指定来源 + 关键词；批量接受与提示数量一致，隐藏成员完整联动 |
| 撤销/重做 | 连续撤销单项、筛选、文件操作，计数和可见行恢复；重做后输出与原决定一致 |
| MathML | 使用 `mathml=True` 的合成 Profile：mtext 改变，mi 等标识符与属性保存重开后原样 |
| 诊断 | 无修改但有诊断的文件仍可查看原始位置，查看不会写入 |
| 写回 | 只写接受的修改；完成后保存 EPUB、关闭并重开；未选资源的 SHA-256 不变 |
| 取消/设置 | 取消预览零写入；返回设置重分析后旧撤销栈和筛选决定不污染新计划 |
| 可操作性 | 1280×800、三语言、系统缩放和键盘焦点；Apply/取消可达，正文可以完整查看和复制 |

每份宿主记录包括：源提交、插件版本、安装 ZIP SHA-256、夹具 EPUB SHA-256、OS/架构、Sigil 版本、插件 Python/Qt 版本、操作、期望、实际结果、输出 EPUB SHA-256。macOS arm64 上通过只代表这一宿主；其他平台没有实测就分别写 `Not verified`。

## 8. Luna 的结果交付格式

新建 `02-implementation-results.md`，不要提前把本计划勾成完成：

```markdown
# 2026-09-27 后续优化实现结果

- 实际起始提交：
- 最终实现提交或未提交 diff：
- 环境：OS / Python / Qt / Sigil

| ID | 基线证据 | 修改入口 | 正式测试与结果 | 真实 Qt | Sigil | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| R-01 | baseline.json + 截图 | 待填 | 待填 | 待填 | Not verified | 待执行 |

## 自动验证

填写实际命令、通过/失败/跳过数量、probe 前后数据、性能规模/访问次数、
真实 Qt 截图和交互数据路径、package/validator 结果。

## 仍未完成或未验证

分开写实现缺口、自动验证缺口、宿主缺口；说明原因和下一步。
```

所有核心条目必须各有一行。完成条件是功能语义和列出的边界都覆盖，不能仅以 `make check` 为绿来勾选新功能。本轮需要交付 v0.2.8 发布；按第 10 节在最终 release prep commit 中统一改版本和发布记录。

## 10. 用户指定的提交、推送和 v0.2.8 发布节点

用户已明确要求“分步骤提交 push，最终打最后 commit 的节点的 tag 0.2.8”。按以下顺序操作，不在 tag 后再加 release note 或修复提交：

1. 当前审查计划、基线探针、截图与 full check 日志先作为一个独立 `docs:` commit 推到 `main`。
2. R-01、R-02、O-01 各自按可审查范围完成、验证、commit、push；随后 F-01、F-02、F-03 各自完成并推送。每个 commit 的结果表列出 SHA 和定向测试。
3. O-02 与 `02-implementation-results.md` 完成后单独提交并推送。核对远端 main 与本地 release candidate 一致、工作区干净。
4. 更新 `PLUGIN_VERSION`、`pyproject.toml` 与 `uv.lock` 的项目版本、`plugin.xml`、`README.md` 当前 Release 链接、`CHANGELOG.md`、`docs/releases/v0.2.8.md` 及结果报告。核对仓库其他生成版本来源，不能留 0.2.6 作为当前值。release prep commit 作为最后一个 main commit，英文提交信息说明 v0.2.8。
5. 在 release prep commit 上运行 `make check`、`make package`、`make artifact-check`、`git diff --check`；本地 ZIP 只能报告为 macOS arm64 单平台包。
6. 将 release prep commit 推到 `origin/main`。运行 `gh workflow run ci.yml --ref main`；等待完整六 payload、差分、包组装、六个 package smoke 全绿。下载与该 commit SHA 一致的 Actions artifact，运行 `tools/release_assets.py --asset-dir … --version 0.2.8` 并独立校验所有 ZIP 与 checksum。**若 E-01、资产或校验未过，不打 tag。**
7. 确认 `main`、release prep SHA、成功 workflow `headSha` 和下载的 artifact commit 完全一致；本地不存在旧 `v0.2.8` tag，也不存在 GitHub 上已占用的 tag/release。基于成功验证的同一 SHA 创建 annotated tag `v0.2.8` 并推送 tag。不要创建指向其他 commit 的移动或替换 tag。
8. 等待 tag workflow 的六个 smoke、`attest-release-assets`、`publish-release` 全绿。下载 GitHub Release 上的所有文件，验证七个 ZIP、`SHA256SUMS.txt`、版本号、校验值，并对八个资产逐一运行 `gh attestation verify`。只有到这里才报告发布完成。
9. 真实 Sigil 安装、转换、保存、关闭并重开另列宿主表；没有具体宿主测试就写 `Not verified`。完整 release workflow 或包 smoke 不能代替宿主验收。

提交和发布门禁格式：

```text
<step commit SHA> <remote main SHA> <targeted checks>
<final candidate SHA> <E-01 URL> <asset checksums>
v0.2.8 -> <final candidate SHA>
<tag workflow URL> <release URL> <attestation results>
```

## 9. 确实还可以做的功能：独立候选，不纳入默认核心批次

以下是项目代码/规范中可确认的未开放能力。它们对转换范围或持久化有更大影响，应单独选题；不是把一个开关接上 UI 就能完成。

### C-01：SVG 可见文字（优先于竖排标点）

价值：转换图表、插图中的中文标签。当前 `TokenizerOptions.svg_text` 有低层开关和测试，但 Profile 开启被拒绝、`tokenizer_policy()` 未接通它；没有完整产品入口。

最小可执行范围：仅已选择 XHTML 中的内嵌 SVG `text` / `tspan` 直接文字；默认关闭；不增加独立 `.svg` 文件选择，不处理 `foreignObject`、script/style、path、属性、id/href。需要命名空间感知的允许列表，不能直接取消整个 SVG 的保护。

步骤：先扩充 tokenizer 的目标策略与结构夹具，再接 Profile 验证/保存、设置 UI、快照、预览独立分类和计数。未知 SVG 元素/namespace 保守跳过；独立资源以后另排期。

验收：前缀、嵌套 tspan、实体、外语、未知命名空间、script/style/path/foreignObject、默认关闭；只有 text/tspan 允许区间变化。保存 Profile 重载后选项保持；只接受一个 SVG 文字项时，其余文本、path data、属性与未选文件逐字节不变。完成真实 Sigil 保存/重开和至少一个实际阅读器渲染核对后，再声称视觉验收完成。

### C-02：方案与关联规则的一起导出/导入

价值：换电脑、分享一套转换规则，避免只复制 Profile 后丢失 `ruleset_ids` 指向的规则。现在有规则导入导出和 Profile 本地存储，没有在 Profile 管理器中找到这种完整迁移入口。

最小版本先做“导出迁移包 + 导入为副本”，不做覆盖合并、云同步或备份整个用户目录：

1. 使用单一 UTF-8 JSON，独立 schema version，包含一个选定 Profile 和全部引用 ruleset；缺引用即终止导出并说明。
2. 默认明确提示包内含用户规则正文；不含 EPUB、正文历史、日志、路径、后端二进制。它是用户主动导出的规则文件，不混入默认日志。
3. 导入先验证整包、未来 schema、规则语义及冲突；显示摘要，用户确认前零磁盘修改。先限制为 10 MiB、10,000 条规则，超限明确报错。
4. 导入总是生成新 Profile/ruleset/rule ID，重写关联；profile owner 映射到新 Profile，global owner 保持规则语义；book owner 不能套用当前书，发现 book-scoped 规则则本版拒绝并指导单独管理。
5. 多文件落盘使用临时暂存与恢复记录，Profile 最后发布；注入写失败和进程中断后不能留下可使用的半套引用，也不能覆盖旧数据。沿用现有存储校验，不发明不经验证的直接 JSON 复制。

验收：导出 → 在空用户目录导入 → 重新加载 → 同一合成输入输出相同；规则共享引用、ID 碰撞、重名、新 ID owner 重映射、取消、损坏文件、未来 schema、写失败恢复均验证。该功能工作量 L，应独立执行，不能塞进 O-02 的文档整理。

### C-03：MathML 自然语言 annotation

R-02 先保护标识符。后续增加默认关闭的“转换 MathML 文本注释”，只允许 `annotation encoding="text/plain"` 的文字；其他 encoding、`annotation-xml`、TeX/程序内容、mi/mo/mn 不转换。单独计数并标为需复核，Profile 和语言策略要完整接通。

验收：默认关闭、encoding 大小写/缺失/未知、前缀作用域、混合内容、全部接受后非允许区间不变。没有明确编码的注释不得推测为自然语言。

### C-04：原文对照审校输出

当前已有显式完整 diff 的 Markdown/JSON 报告；`transforms/annotations.py` 只是边界占位，尚未提供规范 §18 的 EPUB 批注插入/清理。

优先选择较小的独立双栏 HTML 审校报告：复用冻结预览结果、用户明确包含原文、HTML 转义、离线无脚本、标明接受/跳过/未处理、按文件定位；不改 EPUB。验收恶意 HTML 文本只按文字显示、实体/换行/删除替换正确、默认报告仍无正文。

若要把批注写入 EPUB，必须另立执行规格：定义允许的结构变化、marker CSS、命名冲突、幂等插入/移除、移除是否能恢复源格式、额外资源写入与失败处理，再扩展 verifier。不能用这个计划直接跳过“未计划结构不得修改”的约束。

### C-05：竖排标点、跨行内标签整词、custom config

这些仍是后续研究项，不适合作为本轮 Luna 的顺手功能：

- 竖排标点需要文档/CSS 写作方向语境，当前 `punctuation.py` 明确拒绝 vertical；不能靠全局字符替换开放。
- 跨行内标签整词需要可靠的 segment/offset 投影；已有 `INLINE_BOUNDARY` 诊断不等于安全映射已经实现。
- custom config 需要本地文件允许范围、数据来源/许可、hash 冻结、配置链验证与独立打包约定；不能绕过官方 payload 边界。

每个研究项先交付“可行性证据 + 数据模型 + 最小合成夹具 + 不支持范围 + 验收规则”，再形成独立实现计划。不要先开放 UI，之后才补保护和验收。
