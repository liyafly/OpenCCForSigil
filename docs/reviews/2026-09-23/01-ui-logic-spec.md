# v0.1.0 UI 与逻辑复审：修改规格（供实现模型执行）

日期：2026-09-23。基线：`main` @ `b2f674b`（v0.1.0）。状态：待实施。

本文档是一份可直接交给实现模型执行的修改规格。每个条目给出位置、现状与证据、修改要求、不可破坏的约束和验证方法。
审查范围为 `plugin/OpenCCForSigil/` 下的 UI、controller、core、rules、logging。打包、CI 与 native 构建不在本次范围内。

基线验证：`.venv/bin/python -m pytest -q` 共 209 项通过（41.2 秒，macOS arm64 / CPython 3.14.7）。

---

## 0. 实现者必读

### 0.1 必须同时载入的文件

- `docs/OpenCCForSigil_Spec_v1.4/INVARIANTS.md`：与本文冲突时以 INVARIANTS 为准，冲突条目放弃并在交付说明中记录。
- 本文与以下现有记录：`docs/deviations.md`、`docs/rules-and-profiles.md`、`docs/extended-document-conversion.md`、`docs/privacy.md`。

与本次修改最相关、绝对不能破坏的不变量：

| 编号 | 内容摘要 | 本次最容易踩到的地方 |
| --- | --- | --- |
| 16 | 只有 `allowed_spans` 内可变化，其余字节不变 | L-01 引号状态跨节点、L-02 转义 |
| 18 | PREVIEWING 之前 `writefile` 调用为 0 | U-01 返回范围、U-06 空计划直出结果 |
| 19/21 | staging → verify → 源哈希复查 → 唯一 commit 边界 | L-11 错误对话框、U-10 写回进度 |
| 20 | 任何错误 `run()` 返回非 0，不得部分提交 | L-11、L-12 的"恢复"不能把失败变成成功 |
| 23 | 规则、profile、config、scope、options 改变必须使 Plan 失效 | L-03、L-07 编译规则缓存、U-01 |
| 15 | Jieba 仅在已验证 payload 且探测成功时可用；失败即关闭，不回退 | L-08 后台探测 |
| 25/26 | 地区显式；comparison config 只做分类 | L-09 诊断短路 |
| 27 | 默认日志和历史不保存正文 | L-16 历史书名字段 |

另外：UI、Rules、Preview、Verifier 不得直接 `import opencc`，所有转换经过 `OpenCCBackend`。不得为了提速拆分传给 OpenCC 的原文。

### 0.2 工作方式

1. 每个条目（或本文第 6 节的一个批次）单独提交；先写能复现问题的失败测试，再改代码。
2. 不刷新 golden/差分期望值，不改 `vendor/` 与 `native_build/`，不新增运行时依赖。
3. 所有新增用户可见文字进入 `resources/i18n/{en,zh-Hans,zh-Hant}.json`，三份键和占位符一致；运行时必需键加入 `tools/validate_artifact.py:46` 的 `_I18N_REQUIRED_KEYS`。
4. 每条交付时写明：改了哪些文件、新增了哪些测试、测试命令与结果、哪些手动验收项需要用户在 Sigil 里完成。

### 0.3 测试基础设施（已存在，直接复用）

| 用途 | 做法 | 参考 |
| --- | --- | --- |
| Qt 对话框逻辑单测 | `object.__new__(_PreviewDialog)` 后注入 fake 控件，调用私有方法并断言 | `tests/unit/test_preview_window.py:1-140` |
| 进度对话框单测 | `_FakeQt` / `_FakeProgressDialog` | `tests/unit/test_progress_reporter.py` |
| Controller 全流程 | `monkeypatch.setattr("ui.preview_window.choose_scope", …)` 等替换 UI 函数，用 fake BookContainer 记录读写 | `tests/integration/test_plugin_conversion.py:1-90` |
| 真实 OpenCC 后端 | 仓库自带 macOS arm64 cp314 payload，本机 `OpenCCBackend("s2t")` 可直接构造 | `tests/unit/test_worker_planning.py` |
| 全量检查 | `make check`（Ruff、pytest、vendor 校验、两套差分、构建检查） | `Makefile` |

本机 `.venv` 没有 PySide6，也没有安装 Sigil。凡是只能在真实 Qt 里确认的行为（焦点、Esc、窗口关闭、布局截图），本文都列为"手动验收"，由用户在 Sigil 内完成。fake 测试通过不等于宿主验收。

### 0.4 优先级定义

- **P0**：产生错误的书籍内容，且现有 verify 拦不住。
- **P1**：用户可见的阻断、设置被静默丢弃、明显卡顿，或与规格/文档承诺不符。
- **P2**：体验打磨、一致性、次要性能。
- **P3**：代码结构与可维护性，不改变行为。

证据标记："已复现"表示本次用脚本在真实 payload 上跑出了结果；"代码确认"表示逐行阅读得出，逻辑确定；"需宿主实测"表示依赖真实 Qt/Sigil 行为，实施前后都要实测。

---

## 1. 结论

最需要先修的是 L-01：开启引号转换时，内联标签或用户规则会把配对状态切断，闭引号被写成开引号。verify 无法发现这个错误（已复现）。

其次是三处设置静默丢失或损坏：
- L-03：新建规则集下次启动就不再生效。
- L-04：Jieba 方案在方案编辑器里无法保存。
- L-05：强制中转链加载后被重置。

性能上，规则较多时每个文本节点都在重复校验并全量扫描规则。实测 2000 条规则时约 12 ms/节点，3000 个节点约 36 秒（L-07）。每次启动还固定多花约 2.2 秒探测 Jieba（L-08）。

失败路径没有任何用户界面提示（L-11）。流程上，"返回设置"不能改文件范围（U-01）。Checkpoint 提醒出现在插件运行中、用户已无法操作 Sigil 的时刻（U-02）。

---

## 2. 问题总览

| ID | 优先级 | 类型 | 标题 | 主要文件 |
| --- | --- | --- | --- | --- |
| L-01 | P0 | 正确性 | 引号配对在内联标签与规则切分处重置 | `transforms/quotations.py`、`core/converter.py`、`core/planner.py` |
| L-02 | P1 | 正确性 | 长文本回退块中未变化的 `>` 被转义为 `&gt;` | `core/planner.py:124-162` |
| L-03 | P1 | 设置丢失 | 规则窗口新建的规则集下次启动静默失效 | `app/settings.py`、`ui/run_options.py` |
| L-04 | P1 | 设置损坏 | 方案编辑器无法保存 Jieba 配置的方案 | `ui/profile_window.py` |
| L-05 | P1 | 设置损坏 | 强制中转链加载时被重置、选项互不联动 | `ui/run_options.py` |
| L-06 | P1 | 逻辑 | 规则"添加 / 更新"只会追加，编辑即产生阻断冲突 | `ui/rules_window.py` |
| L-07 | P1 | 性能 | 规则覆盖层每节点重复校验、线性扫描全部规则 | `core/converter.py:88-120`、`rules/engine.py:82-121` |
| L-08 | P1 | 性能 | 每次启动同步探测 Jieba 约 2.2 秒且无反馈 | `app/controller.py:122`、`opencc_backend/backend.py:84-105` |
| L-09 | P2 | 性能 | 混合脚本诊断对无汉字文本也做两次转换 | `core/diagnostics.py:44-46`、`core/converter.py:51-54` |
| L-10 | P2 | 逻辑 | 后台分析进度每 25 ms 只取一条更新，显示滞后 | `core/workflow.py:233-241` |
| L-11 | P1 | 失败处理 | 所有失败路径都没有用户界面提示 | `app/controller.py:372-383`、`plugin.py:38-40` |
| L-12 | P1 | 健壮性 | 偏好、方案、历史文件损坏会让插件无法使用 | `sigil/storage.py:74-81`、`app/settings.py:31-33`、`app/profiles.py:419-427` |
| L-13 | P1 | 逻辑 | 源文件本身不良构时，用户决定完才在 verify 阶段整体失败 | `core/verifier.py:46-50`、`core/workflow.py` |
| L-14 | P2 | 逻辑 | 规则导入不传范围、不显示诊断，与文档承诺不符 | `ui/rules_window.py:513-535` |
| L-15 | P2 | 逻辑 | 词典检查不传 profile/book，也不显示对比配置输出 | `ui/rules_window.py:489-511`、`app/settings.py:90-93` |
| L-16 | P2 | 逻辑 | 保留期清理从未被调用；历史"书名"列恒为空 | `logging_ext/retention.py`、`ui/history_window.py:91` |
| L-17 | P2 | 数据一致性 | `run_options` 把过期字段带进方案，界面不显示当前方案 | `ui/run_options.py:87-94` |
| U-01 | P1 | 流程 | "返回设置"不能修改文件范围 | `app/controller.py:104-262` |
| U-02 | P1 | 流程 | Checkpoint 提醒时机错误（运行中无法操作 Sigil） | `ui/preview_window.py:836-860` |
| U-03 | P1 | 防误操作 | 预览中 Esc/关闭/取消直接丢弃全部决定 | `ui/preview_window.py:585` |
| U-04 | P1 | 可读性 | 预览列表显示 manifest ID、repr 引号和原始 XHTML 上下文 | `ui/preview_window.py:682-742`、`core/planner.py:143-159` |
| U-05 | P1 | 效率 | 决定后不跳到下一项，无快捷键，应用按钮不说明原因 | `ui/preview_window.py` |
| U-06 | P1 | 流程 | 没有任何变化时仍弹出空预览 | `app/controller.py:241-242` |
| U-07 | P1 | 可理解性 | 语言标签组跨文件联动，"接受本文件"会改其他文件 | `ui/preview_window.py:800-818` |
| U-08 | P1 | 布局 | 转换设置对话框 18 个选项平铺、互不联动 | `ui/run_options.py`、`ui/preview_window.py:877-991` |
| U-09 | P2 | 布局 | 范围对话框的单文件/全书模式表达不清 | `ui/preview_window.py:994-1223` |
| U-10 | P2 | 流程 | 不可取消阶段的进度窗可被关闭；写回阶段无进度 | `app/controller.py:276-301`、`ui/preview_window.py:39-143` |
| U-11 | P2 | 文案 | 结果对话框缺少"仍需在 Sigil 中保存"提醒 | `ui/preview_window.py:374-452` |
| U-12 | P2 | 布局 | 方案窗口"保存=选择"、无删除、规则集要手输 | `ui/profile_window.py` |
| U-13 | P2 | 布局 | 规则窗口的规则集选择、范围文案、按钮分组 | `ui/rules_window.py`、`app/settings.py:75-97` |
| U-14 | P2 | 布局 | 历史窗口可编辑、未本地化、含无效复选框 | `ui/history_window.py` |
| U-15 | P2 | i18n | 三套私有翻译表、原始英文异常直接进对话框 | 多个 `ui/*.py` |
| C-01 | P3 | 结构 | Qt 加载与配置常量重复 4 份、模块级全局传参、占位模块 | `ui/*.py`、`app/settings.py` |

---

## 3. 逻辑与正确性

### L-01 引号配对在内联标签与规则切分处重置（P0，已复现）

**位置**

- `transforms/quotations.py:28-56`：`transform_quotations` 每次调用都从 `in_quote = False` 开始。
- `core/converter.py:48`：每个文本 target 单独调用一次。
- `core/converter.py:102-110`：有规则时按锁定区间切段，每段各调用一次 `convert`，因此每段都重新配对。

**复现**（真实 payload，`quotation_mode="corner"`，s2t）：

```text
<p>"他说<em>你好</em>"</p>        →  <p>「他說<em>你好</em>「</p>
<p>"软件"</p> + protect 规则"软件"  →  <p>「软件「</p>
<p>"软件"</p>（无规则）             →  <p>「軟件」</p>
```

闭引号变成开引号。结构校验不会失败，只能靠用户在预览里逐条发现。

**修改要求**

1. 把配对改成有状态的对象，例如 `QuotationPairer(mode)`，提供 `feed(text, mutate=True) -> str`。状态跨调用保留；`mutate=False` 时只推进状态、不改文字。
2. `_convert_rules` 遍历分段时共用同一个 pairer：
   - 未锁定段 `mutate=True`；
   - 锁定区间（exact/protect）调用 `feed(span.source, mutate=False)`，只推进状态。现有文档承诺"规则输出不参与引号变化"，这一点保持不变。
3. `build_conversion_plan` 遍历 `document.targets` 时，在同一块级元素内的连续文本 target 之间传递状态：
   - 用 `document.tags` 判断前后两个 target 之间是否出现块级开/闭标签。块级集合至少包含 `p div li h1-h6 blockquote td th dd dt figcaption section article aside header footer body`。
   - 出现块级边界就重置状态。方法可参考 `document/diagnostics.py:32-74` 的 bisect 写法。
   - 属性 target（alt/title/aria-label）各自使用独立状态，不与正文串联。
   - NCX/metadata 每个 target 独立。
4. 块结束时若仍处于引号内（ASCII `"` 数量为奇数），该块内所有 `category="quotation"` 的变更把 `risk` 提升为 `REVIEW`，并追加诊断 `QUOTE_UNBALANCED`（按 U-15 本地化）。
5. `keep` 模式必须仍然原样返回同一对象，不产生任何变更。

**约束**：不得把多个文本节点拼接后一起送进 OpenCC（会改变分词上下文）。拆分只影响引号状态，OpenCC 输入保持逐节点不变。

**验证（自动化）**：新增 `tests/unit/test_quotation_pairing.py`，用真实 `OpenCCBackend("s2t")` 走 `ConversionWorkflow.plan()`。可参考本次复现脚本的写法：fake Book 只需 `text_iter/readfile/writefile`，`TargetSelection(Scope.SINGLE, ("a",))`。

| 用例 | 输入 | 期望（corner） |
| --- | --- | --- |
| 跨内联 | `<p>"他说<em>你好</em>"</p>` | `<p>「他說<em>你好</em>」</p>` |
| 规则切分 | `<p>"软件"</p>` + protect「软件」 | `<p>「软件」</p>`，且"软件"未被转换 |
| exact 规则 | `<p>"鼠标"</p>` + exact 鼠标→滑鼠 | `<p>「滑鼠」</p>` |
| 块级重置 | `<p>"甲"</p><p>"乙"</p>` | 两段各自一对 |
| 不平衡 | `<p>"甲</p><p>乙"</p>` | 两个引号变更 risk 为 REVIEW，含 `QUOTE_UNBALANCED` |
| 属性独立 | `<img alt='"甲"'/>` + 正文 `"乙` | alt 自成一对，不影响正文 |
| keep 模式 | 以上任一 | 零变更，输出字节不变 |
| 重建 | 全部接受 | `apply_changes` 结果等于期望字符串，且 `verify_staged_file(...).passed` |

同时跑 `tests/unit/test_m4_transforms.py` 与 `tests/integration/test_rules_transform_workflow.py`，确认原有用例全部通过。

**验证（手动）**：在 Sigil 中对含 `<p>"……<span>……</span>……"</p>` 的章节开启"角括号"，预览中闭引号显示为 `"` → `」`。

---

### L-02 长文本回退块中未变化的 `>` 被转义（P1，已复现）

**位置**：`core/planner.py:137-138` 对整段替换目标做 `html.escape(target_text, quote=attribute)`。

**复现**：一个文本节点为 `"汉"*1500 + " a > b " + "汉"*1500`，s2t。`core/diff.py` 找不到唯一锚点，回退为一个整段替换，输出中的 `a > b` 变为 `a &gt; b`，且 verify 通过。

属性值也有同类问题：在 `"` 定界的属性里，未变化的 `'` 会被转成 `&#x27;`。

**为什么仍需要转义**：用户 exact 规则的 target 可以包含 `&`、`<`、引号；文本 target 本身不会含实体（`document/tokenizer.py:414-443` 已按实体切开）。

**修改要求**

1. 文本节点只转义 `&` 与 `<`，不转义 `>`。另外把 `]]>` 序列写成 `]]&gt;`：XML 文本不允许出现该序列。
2. 属性值只转义 `&`、`<` 和该属性自己的定界引号。需要在 `TextTarget` 增加可选字段 `attribute_quote: str | None = None`，由 `document/tokenizer.py:197-217` 从 `AttributeSpan.quote` 填入。
3. 无引号属性值（`quote is None`）两种引号都转义，保持保守行为。
4. CDATA 分支保持不变。

**约束**：`change_id` 的计算包含 target 文本（`planner.py:139-142`），修改后含 `>` 或引号的变更 id 会变化，这是预期的。`tests/fixtures/*.jsonl` 只是 CLI 差分语料，不含 change_id；如果有单测硬编码了受影响的 id，同步更新并在交付说明中列出，不得借机改动差分期望值。

**验证（自动化）**：在 `tests/unit/test_source_preserving_pipeline.py` 增加：

- 复现用例：全部接受后输出包含原始 ` a > b `，不含 `&gt;`。
- exact 规则 target 为 `A&B<C`：文本节点输出 `A&amp;B&lt;C`。
- `alt="x"` 中 exact 规则 target 含 `"`，输出 `&quot;`；同一属性中未变化的 `'` 保持原样。
- `alt='x'` 中 target 含 `'`，输出 `&#x27;` 或 `&apos;`（二选一，写入测试）。
- 属性测试：随机生成含 `> ' "` 的长文本，全部接受后，所有未被 OpenCC 改变的 ASCII 字符字节不变，`verify_staged_file` 通过。

---

### L-03 规则窗口新建的规则集下次启动静默失效（P1，代码确认）

**位置**

- `app/settings.py:75-97`：`edit_rules` 只把新规则集 ID 追加到内存中的 `self.active.ruleset_ids`。
- `app/settings.py:31-33`：下次启动时 `active` 从方案文件读取；没有保存的方案时直接用 `ruleset_ids=("default",)`。
- `ui/run_options.py:87-94`：`values()` 用 `services.active.ruleset_ids` 覆盖 `run_options` 里保存的值。

**结果**

- 用户在规则窗口输入新 ID（如 `mine`）并保存规则，本次运行生效。
- 下次启动时 `mine` 不在 `ruleset_ids` 里，规则不再应用，界面也没有任何提示。
- 即使当前是已保存的方案，追加也只在内存里，方案文件本身没有更新。

**修改要求**（推荐方案 A）

1. `RunSettings.__init__`：当 `profile_id` 为空时，从 `preferences["run_options"]["ruleset_ids"]` 取值；只保留磁盘上存在或等于 `default` 的 ID，作为默认方案的 `ruleset_ids`。
2. `edit_rules` 追加规则集后：
   - 若当前方案是已保存方案（`profiles/<id>.json` 存在），弹确认"将规则集 X 加入方案 Y？"，确认后 `ProfileStore.save`。
   - 若用户拒绝，界面显示"规则集 X 仅本次生效"。
3. 转换设置对话框显示当前启用的规则集列表（见 U-08），用户能看到哪些规则集会生效。
4. 已被删除的规则集 ID 在 `freeze_rules` 前过滤，并显示一次非阻断提示，而不是抛 `ruleset not found`。

**约束**：`snapshot_guard`（`settings.py:121-127`）仍然覆盖 `profiles/` 与 `rules/` 目录。保存方案必须发生在 `snapshot_guard()` 创建之前，也就是分析开始之前（不变量 23）。

**验证（自动化）**：新增 `tests/integration/test_ruleset_persistence.py`。

1. 第一次运行：monkeypatch `QInputDialog.getItem` 返回 `("mine", True)`，`show_rules_window` 返回一条 exact 规则，运行完成。
2. 用同一 `data_dir` 新建 `Controller` 进行第二次运行，不打开规则窗口。
   - 断言计划的 `rules_snapshot.rules_hash` 与第一次相同；
   - 断言规则命中出现在变更里（`rule_source` 以 `UserRule:` 开头）。
3. 已保存方案场景：确认后 `profiles/<id>.json` 的 `ruleset_ids` 包含 `mine`；拒绝时文件不变。
4. 删除 `rules/mine.json` 后再运行：不抛异常，出现一次提示，计划不含该规则。

---

### L-04 方案编辑器无法保存 Jieba 配置的方案（P1，代码确认）

**位置**

- `ui/profile_window.py:127-129`：转换下拉框只列基础方向（`_base_config_options` 经 `base_direction` 去掉了 `_jieba`）。
- `ui/profile_window.py:153`：对 `s2twp_jieba` 调用 `findData` 返回 -1，`setCurrentIndex(-1)` 让下拉框变空。
- `ui/profile_window.py:170-173`：保存时 `str(currentData())` 得到 `"None"`，`ProfileStore.save` 校验失败并弹出英文错误。

也就是说，用"另存为方案"保存的 Jieba 方案，只要进编辑器改个名字就保存不了。

**修改要求**

1. 编辑器显示"方向 + 高级 Jieba 复选框"，与转换设置对话框一致（复用 `JIEBA_CONFIG_BY_BASE`）。
2. 若方案的配置在本机不可用（例如 Jieba 探测失败），下拉框显示该配置并标注"（本机不可用）"，保存时保留原值，不静默改写。
3. 禁止任何代码路径调用 `setCurrentIndex(-1)` 后再读 `currentData()`；读取不到时保留原值。
4. `segmentation` 由配置推导（与 `settings.py:47` 一致），编辑器不再单独保存旧值。

**验证（自动化）**：新增 `tests/unit/test_profile_window.py`，使用带 `findData/currentData/setCurrentIndex/addItem` 的 fake 下拉框。

- 加载 `conversion="s2twp_jieba"` 的方案，只改名后保存：文件中 conversion 仍为 `s2twp_jieba`，segmentation 为 `jieba`。
- `available_configs` 不含 Jieba 时加载 Jieba 方案：显示"不可用"，保存保留原值，不报错。
- 切换为 `s2t` 保存：segmentation 变为 `mmseg`。

---

### L-05 强制中转链加载时被重置、选项互不联动（P1，代码确认；Qt 行为需宿主实测）

**位置**

- `ui/run_options.py:69-74`：中转链下拉框以 tuple 为 item data，初始化时 `findData(tuple(...))`。
- `ui/run_options.py:121-122`：加载方案时 `findData(values.get(key, "keep"))`，其中 `pivot_chain` 来自 `Profile.to_dict()`，是 list。
- 在 fake 与 Python 语义下 list ≠ tuple，找不到时回退到第 0 项，也就是排序后的第一条链 `("s2hk","t2s")`。
- 若方案方向是 t2s，这条链末端恰好是 t2s，校验会通过，结果静默使用了错误的中转链。
- PySide6 对 tuple/list 的 QVariant 比较是否相等未经验证；即使相等，这种写法也不可靠。

**联动缺失**

- 中转链下拉框始终可选，并列出与当前方向不匹配的链，点"继续"才报错 `force-pivot must end in the selected configuration`（英文）。
- `language_preset`、`language_region` 在 `language_metadata = keep` 时仍可编辑。
- `language_region` 只对通用繁体（s2t/tw2t/hk2t）+ legacy 有意义，其他情况下也可选。

**修改要求**

1. 所有下拉框的 item data 一律用字符串键：中转链用 `"t2s>s2tw"`，读取时 `tuple(value.split(">"))`；方案加载与初始化共用同一个转换函数。
2. 新增纯函数 `option_enablement(config: str, values: dict) -> dict[str, bool]`（放在 `ui/run_options.py`，不依赖 Qt），规则如下：
   - `pivot_chain` 仅在 `force_pivot` 勾选时可用；
   - 下拉框只列出末端等于当前方向的链；没有可用链时禁用 `force_pivot`，tooltip 说明原因；
   - `language_preset` 仅在 `language_metadata != keep` 时可用；
   - `language_region` 仅在 mode≠keep、preset=legacy、且基础方向属于 s2t/tw2t/hk2t 时可用；
   - `include_metadata` 在 `metadata_available=False` 时禁用（已有）。
3. 方向改变、复选框改变时都重新计算可用状态；被禁用的控件保留值，但 `values()` 输出时对被禁用的 `pivot_chain` 输出 `()`。

**验证（自动化）**：新增 `tests/unit/test_run_options.py`。

- `option_enablement` 的真值表：至少 8 组组合（方向 × force_pivot × language 设置）。
- fake 下拉框（按 `==` 比较 data）：加载 `force_pivot=True, pivot_chain=["t2s","s2tw"]`、方向 s2tw 的方案后，`values()["pivot_chain"] == ("t2s","s2tw")`。
- 方向改为 s2hk 后，链下拉框只剩末端为 s2hk 的项。

**验证（手动）**：在 Sigil 中保存一个 force-pivot 方案，重新打开"方案"加载它，链显示不变；在 language=保持时，风格和地区不可编辑。

---

### L-06 规则"添加 / 更新"只会追加（P1，代码确认）

**位置**：`ui/rules_window.py:422-441`、`449-459`。

**现状**

- 选中表格行会把该规则载入表单，但"添加 / 更新"总是新建一条规则（新 uuid）并追加。
- 改了 target 再点这个按钮，结果是同源两条、target 不同，形成 `SAME_SOURCE_DIFFERENT_TARGET` 阻断冲突，"保存"被禁用（`rules_window.py:419`）。用户必须自己找出并删掉旧规则。
- 方向下拉框默认第一项 s2t（`343-344`），而不是当前转换方向；用 t2s 转换时新建的规则默认不会命中。
- 表格单元格可直接编辑（`QTableWidgetItem` 默认可编辑），但编辑内容不会写回 `self.rules`，静默丢失。
- 类型为 protect 时 target 输入框仍可编辑，实际会被忽略。

**修改要求**

1. 拆成"新增"和"更新所选"两个按钮。"更新所选"替换 `self.rules[row]`：保留 `id` 与 `created_at`，刷新 `updated_at`。没有选中行时禁用"更新所选"。
2. 方向默认值 = `base_direction(self._config)`，下拉框仍允许 `*`。
3. 表格设为 `NoEditTriggers`、整行选择。
4. 类型为 protect 时禁用 target 输入框并清空显示。
5. 冲突提示区显示可点击定位：点冲突项时选中对应行（可用规则 id 反查行号）。

**验证（自动化）**：新增 `tests/unit/test_rules_window.py`，用 `object.__new__(RuleManagerDialog)` 注入 fake 控件。

- 选中第 0 行，改 target，点"更新所选"：`len(rules)` 不变，`rules[0].id` 不变，`find_conflicts` 为空，保存按钮可用。
- 点"新增"：`len(rules)` 加 1。
- `config="t2s"` 构造时方向默认 t2s。
- protect 类型：`_add` 生成的规则 target 等于 source（现有逻辑保留）。

---

### L-07 规则覆盖层每节点重复校验、线性扫描全部规则（P1，已复现）

**位置**

- `core/converter.py:92-97`：每个文本节点都执行 `RuleSnapshot.freeze(...)`（重算 JSON+SHA256）并调用 `lock_spans`。
- `rules/engine.py:97-105`：每次调用都做 `validate_snapshot`（全量校验）、`validate_no_blocking_conflicts`（内部两次 `find_conflicts`，各自再全量校验），并重新排序。
- `rules/engine.py:108-121`：对文本的每个字符位置遍历所有候选规则 `startswith`，复杂度 O(文本长度 × 规则数)。

**实测**（80 字/节点，s2t，关闭分类与混合诊断）：

| 规则数 | 300 节点耗时 | 推算 3000 节点 |
| --- | --- | --- |
| 0 | 0.032 s | 0.3 s |
| 50 | 0.142 s | 1.4 s |
| 497 | 0.977 s | 9.8 s |
| 1976 | 3.654 s | 36.5 s |

cProfile（1976 条规则，100 节点）：约 57% 耗时在逐节点重复的 `validate_rules`/`find_conflicts`/哈希，约 35% 在 `startswith` 扫描（100 节点共 1566 万次调用）。导入一个 OpenCC TXT 词表就可能达到上千条规则。

**修改要求**

1. 新增 `rules/compiled.py` 的 `CompiledOverlay`，每个计划只构建一次：
   - 输入：`RuleSnapshot`、config、profile_id、book_fingerprint；
   - 构建时依次做：校验快照哈希一次、`validate_no_blocking_conflicts` 一次、`applies_to` 过滤、`ordered_rules` 排序；
   - 建首字符索引 `dict[str, tuple[Rule, ...]]`，每个桶内保持全局排序顺序。
2. `lock_spans_compiled(text, overlay)`：在每个位置只遍历 `index.get(text[cursor], ())`。结果必须与现有 `lock_spans` 完全一致，包括优先级、最长匹配和 id 次序。
3. `OfficialBackendConverter` 持有按 `(rules_hash, config, profile_id, book_fingerprint)` 缓存的 overlay。`_convert_rules` 不再逐节点 `freeze`：请求中的 `rules_hash` 在构建 overlay 时校验一次，不一致即报错（保持现有 `rule snapshot hash mismatch` 语义）。
4. `lock_spans`（沙箱、检查器仍在用）改为内部构建临时 overlay 后调用 `lock_spans_compiled`，对外签名不变。

**约束**：不变量 22/23 要求规则经过 precedence、scope、snapshot、conflict 校验。本修改只减少重复次数，不能跳过其中任何一步。

**验证（自动化）**

- `tests/unit/test_rules_compiled.py`：属性测试 300 轮，随机生成 0-200 条规则（混合 exact/protect、scope、优先级、`*` 方向、重叠前缀）和随机文本，断言新旧 `lock_spans` 输出逐项相等。
- 计数测试：monkeypatch `rules.validators.validate_rules` 计数，规划 50 个节点时调用次数 ≤ 3（与节点数无关）。
- 哈希不一致时仍抛 `ValueError("rule snapshot hash mismatch")`。
- 现有 `tests/unit/test_rules_m3.py`、`tests/integration/test_rules_transform_workflow.py` 全部通过。

**验证（性能）**：新增 `tools/benchmark_rules.py`，复现上表设置。验收：1976 条规则、3000 节点在开发机上 ≤ 3 秒，基线为 36.5 秒。取三次中位数，结果写入交付说明。

---

### L-08 每次启动同步探测 Jieba 约 2.2 秒（P1，已复现）

**位置**：`app/controller.py:122` 的 `backend.available_configs()` 触发 `probe_jieba()`（`backend.py:84-105`），逐个构造 7 个 Jieba OpenCC 实例。

**实测**：`available_configs()` 首次调用 2.236 s；标准后端冷构造只要 0.197 s，自检 0.024 s。

这 2.2 秒发生在用户点"继续选择转换方向"之后、转换设置对话框出现之前，期间没有任何界面反馈。即使用户从不使用 Jieba，每次启动也要付出这段时间。

**修改要求**（推荐后台探测）

1. 标准预检通过后，立即在单独线程里启动探测：`concurrent.futures.ThreadPoolExecutor(max_workers=1)` 提交一个函数，只调用官方 `self._module.OpenCC(config).convert("汉字")`，返回 `(ok, error)`，不修改 backend 属性。
2. 主线程在打开转换设置对话框时读取 future：
   - 已完成：按结果设置 `_jieba_checked/_jieba_error`，并决定 `available_configs()` 是否包含 Jieba。
   - 未完成：对话框先打开，Jieba 复选框禁用并显示"正在检测 Jieba…"；用 `QTimer` 轮询 future，完成后再启用或显示原因。
3. 探测失败时保持禁用，原因放进 tooltip 和"详情"，不改变标准配置。
4. 若上次偏好就是 Jieba 配置（`_preferred_config` 返回 `*_jieba`），在探测完成前"继续"按钮保持禁用，避免静默回退为标准配置。
5. 日志事件 `optional_jieba_probe` 记录 `elapsed_ms` 与结果。

**约束**

- 不变量 15：探测未成功之前 Jieba 不可选。payload 哈希/来源失败仍在 selector 阶段阻断，不能降级为可选警告。
- 线程只构造和使用自己的 OpenCC 对象，不触碰 Qt 与 BookContainer，与 `plan_in_worker` 的线程所有权规则一致。

**验证（自动化）**：扩展 `tests/unit/test_optional_jieba.py`，用 fake module 让 Jieba 构造 `sleep(0.3)`。

- `choose_scope`（monkeypatch）被调用时，探测尚未结束（记录时间戳比较）。
- 探测进行中：fake 对话框的 Jieba 复选框为禁用。
- 探测成功：复选框可用；失败：禁用且显示原因；标准配置不受影响。
- 偏好为 `s2t_jieba` 且探测未完成：继续按钮禁用；探测失败后提示并要求用户重新选择方向。

**验证（手动）**：在 Sigil 中从范围对话框点"继续"到设置对话框出现 < 0.5 秒。

---

### L-09 混合脚本诊断对无汉字文本也做两次转换（P2，代码确认 + 实测）

**位置**：`core/diagnostics.py:44-46` 先调 s2t、t2s，再计算 `evidence_length`；`core/converter.py:51-54` 对每个文本节点都调用。

**实测**（s2twp，3000 节点）：基础 0.309 s；加混合诊断 0.367 s（+19%）；加对比分类 1.257 s（+307%）。

**修改要求**

1. `diagnose_mixed_script` 先计算 `evidence_length`：小于 `min_evidence` 时直接返回 `unknown`，不调用后端。
2. 当前配置正好是 s2t 或 t2s 时，复用已算出的官方输出，不重复转换（在 converter 里把 `official` 传入诊断函数，新增可选参数）。
3. 对比分类的开关文案改为"对比官方配置以标注变更类型（较慢）"，默认值保持不变。是否改默认值属于产品决定，本条不改。

**验证（自动化）**：新增计数测试。fake backend 统计 `convert_for_config` 调用次数：纯标点/英文节点为 0 次诊断调用；s2t 配置下含汉字节点诊断只额外调用 1 次（t2s）。诊断结果与修改前相同（对现有 `tests/unit/test_m4_transforms.py` 中的样例逐一比对）。

---

### L-10 后台分析进度每 25 ms 只取一条更新（P2，代码确认）

**位置**：`core/workflow.py:233-241`。每轮循环 `updates.get(timeout=0.025)` 只取一条。worker 每个文件产生两条更新，小文件很多时队列积压，进度条落后于实际进度，最后一次性跳到 100%。

**修改要求**

1. 每轮先阻塞等待一条（保留 25 ms 超时），然后用 `get_nowait()` 取空队列，只保留最后一条再调用一次 `progress(*last)`。
2. 检测到取消后调用进度器的新方法 `set_cancelling()`，把标签改为"正在取消，当前文件分析结束后停止…"并禁用取消按钮（需新增 i18n 键）。

**验证（自动化）**：扩展 `tests/unit/test_worker_planning.py`。

- worker 在 10 ms 内产生 1000 条更新：循环结束前记录到的最后 index 等于 total，`progress` 调用次数远小于 1000。
- 取消后 fake 进度器收到 `set_cancelling()` 一次，最终仍抛 `WorkflowCancelled`，零写入（已有断言保留）。

---

### L-11 所有失败路径都没有用户界面提示（P1，代码确认）

**位置**

- `app/controller.py:372-383`：通用异常只写日志并 re-raise。
- `plugin.py:38-40`：只 `print(..., file=sys.stderr)`。
- 目录里的 `error.read`、`error.failed`、`error.backend_self_test`、`error.scope_invalid` 四个键在代码中引用次数为 0。

**会走到这里的真实场景**

- 结构校验失败：`workflow.py:381-382`，报错不说明是哪个文件、什么原因。
- 源在预览后变化：`workflow.py:395-399`。
- 规则/方案在预览后变化：`settings.py:124-126`。
- 方案文件缺失或损坏（L-12），偏好文件损坏。
- 后端自检失败、目标文件消失（`adapter.py:165-167`）、分组语言变更被部分接受（`workflow.py:279-280`）。

用户只能在 Sigil 插件运行窗口里看到一行英文 stderr。

**修改要求**

1. 在 `ui/preview_window.py`（或按 C-01 拆出的 `ui/dialogs.py`）新增 `show_error(*, kind, detail, files_written, log_path)`。内容包括：
   - 本地化标题与一句话原因；
   - 明确的"是否已写入书籍"说明：写回前失败统一为"没有文件被修改"；部分写回沿用现有 `result.partial`；
   - 下一步建议，例如"请重新运行插件以重新分析"；
   - 可展开的详情：错误码、文件 href、诊断码列表、日志路径；
   - "复制诊断"按钮，把错误码、文件、诊断码和日志路径复制为纯文本，不包含书籍正文。
2. 把异常映射到 `kind`：给 `WorkflowError` 增加 `code` 属性（如 `VERIFY_FAILED`、`SOURCE_CHANGED`、`SETTINGS_CHANGED`、`GROUP_PARTIAL`）。verify 失败的异常携带 `(href, diagnostic codes)` 列表。
3. `Controller._run_once` 的通用 `except` 分支在 re-raise 前调用 `_show_error_safely(...)`，继续返回非 0（不变量 20）。`UserCancelled` 与取消路径不弹错误。
4. 错误对话框不能出现在写回边界之前的"成功"路径上，也不能吞掉异常。

**验证（自动化）**：新增 `tests/integration/test_error_reporting.py`。monkeypatch `show_error` 记录调用；以下每个场景都断言 `show_error` 被调用一次、`kind` 正确、`run()` 返回 2、`writefile` 调用 0 次：

- verify 失败：在 `show_preview` stub 里接受全部，再 monkeypatch `core.workflow.verify_staged_file` 返回 `passed=False` 并带诊断。
- 源变化：在 `show_preview` stub 里修改 fake book 对应文件。
- 设置变化：在 `show_preview` stub 里写入 `rules/x.json`。
- 方案缺失：preferences 指向不存在的 `profile_id`（配合 L-12，改为提示并回退后，本场景应改为"不报错、有提示"）。
- 部分写回：沿用现有 partial 测试，断言结果对话框而非错误对话框。

**验证（手动）**：在测试副本中把某章改成不良构（见 L-13），确认对话框三语显示且"复制诊断"可用。

---

### L-12 偏好、方案、历史文件损坏会让插件无法使用（P1，代码确认）

**位置与现状**

| 文件损坏/缺失 | 位置 | 现状 |
| --- | --- | --- |
| `preferences.json` 不是 JSON 或 schema 不符 | `sigil/storage.py:74-81` | 启动即抛 `StorageError`，每次运行都失败，直到用户手动删文件 |
| `profile_id` 指向已删除/损坏的方案 | `app/settings.py:31-33` | 用户选完范围后崩溃 |
| `profiles/` 下任一文件损坏 | `app/profiles.py:419-427` | "方案"窗口整体打不开，只弹英文错误 |
| `rules/` 下任一文件损坏 | `rules/store.py:115-121` | 打开规则工具时 `list()` 抛异常 |
| `history/index.json` 损坏 | `logging_ext/history.py:159-178` | 历史窗口永远打不开，新记录也写不进去 |

**修改要求**（遵循 `storage.py` "不静默重置"的原则：先备份，再告知）

1. 新增 `UserDataStore.quarantine(path) -> Path`：把损坏文件重命名为 `<name>.corrupt-<UTC时间戳>`，返回新路径。
2. 偏好损坏：隔离后使用默认值继续运行，范围对话框顶部显示一次提示"偏好文件已损坏，已备份为 X，本次使用默认设置"。schema 版本更高（未来版本写入）时不隔离，改为只读运行：不写回偏好，并提示升级。
3. 方案缺失或损坏：回退为默认 `conservative`，提示一次，并清除偏好中的 `profile_id`。
4. `load_all` 与 `RuleStore.list` 跳过损坏文件，返回 `(items, errors)`；窗口顶部列出被跳过的文件名。
5. 历史损坏：历史窗口提供"备份并重建空历史"按钮；`record_session` 失败时保持现有行为（记录 `history_failed`，不影响转换结果）。

**约束**：不得删除用户文件；不得在无提示的情况下丢弃数据；隔离操作只发生在插件自有的用户数据目录。

**验证（自动化）**：新增 `tests/unit/test_storage_recovery.py`，每种损坏各一个用例。

- 断言原文件被重命名为 `*.corrupt-*`，内容不变；
- 断言运行继续或窗口可打开；
- 断言提示回调收到一次；
- 未来 schema 版本：偏好文件内容与 mtime 均未改变。

---

### L-13 源文件本身不良构时，决定完才整体失败（P1，代码确认）

**位置**：`core/verifier.py:46-50` 只校验转换后内容的 XML 良构性，没有先校验原文件。

**结果**：如果某章原本就不良构（Sigil 允许关闭良构检查后保存这类文件），用户在预览里做完全部决定后，verify 失败会阻断整本书的写回，错误还没有界面提示（L-11）。

**修改要求**

1. 在规划阶段（worker 内，`ConversionWorkflow._plan_document`）对 XHTML/NAV 原文调用 `validate_xhtml_syntax`。
2. 原文不良构时：该文件生成零变更的计划，附诊断 `SOURCE_INVALID_XHTML`（含 expat 行列号）。预览顶部与文件筛选中标注"已跳过：源文件不是良构 XHTML（第 L 行第 C 列）"。结果统计计入"没有建议变更"。
3. verifier 保持现有严格校验不变：转换后不良构仍然阻断。
4. NCX/metadata 已在 `tokenize_xml` 阶段抛 `XMLDocumentError`，行为不变，但要经过 L-11 显示给用户。

**约束**：不能因为跳过坏文件而扩大或缩小其他文件的范围；跳过的文件读取次数不变，写入次数为 0。

**验证（自动化）**：在 `tests/integration/test_plugin_conversion.py` 增加用例。两文件书：`a` 为 `<p>汉字<br></p>`（未闭合），`b` 正常。

- 计划中 `a` 零变更且带 `SOURCE_INVALID_XHTML`，`b` 正常；
- 全部接受后 `b` 被写入、`a` 写入 0 次；
- 结果统计 `files_without_changes == 1`。

---

### L-14 规则导入不传范围、不显示诊断（P2，代码确认）

**位置**：`ui/rules_window.py:513-535`。

- `import_rules(path, direction=combo)` 没有传 `scope/profile_id/book_fingerprint`，导入的规则一律是 global。
- `strict=True`：任一行错误中止整个导入。
- OpenCC TXT 必须有方向，但界面只是悄悄使用方向下拉框当前值。
- 只显示冲突；`ImportDiagnostic`（如"discarded candidates"）和重复项从不显示。
- 这与 `docs/rules-and-profiles.md` 中"Import diagnostics and conflicts are visible before saving"不符。

**修改要求**

1. 导入前弹一个小表单：格式（按扩展名预选）、方向（TXT 必选，默认当前方向）、范围（global/profile/book，book 在无指纹时禁用）、"遇到错误行时跳过并报告"（默认勾选，即 `strict=False`）。
2. 导入后显示汇总：新增 N 条、与现有规则重复 M 条（不重复加入）、丢弃候选 K 行、错误 E 行（行号 + 原因）、冲突列表。用户点"加入"后才合并进 `self.rules`。
3. 与现有规则去重时使用 `importers.py:96-97` 的同一键。

**验证（自动化）**：`tests/unit/test_rules_window.py` 增加：

- TXT 含一行多候选、一行空 target：非严格模式下导入 1 条，诊断 2 条；
- profile 范围导入：规则的 `profile_id` 等于当前方案；
- 与现有规则完全相同的行：不重复加入，计入重复数。

---

### L-15 词典检查不传 profile/book，也不显示对比配置输出（P2，代码确认）

**位置**

- `ui/rules_window.py:502-509` 调 `show_dictionary_inspector` 时没传 `profile_id/book_fingerprint`（`inspect_dictionary` 支持），导致 profile/book 范围规则在"测试"里命中、在"词典检查"里不命中。
- `app/settings.py:90-93` 调用 `show_rules_window` 时没传 `comparison_configs`，检查器的对比输出列表恒为空。

**修改要求**：两处参数补齐：`comparison_configs=comparison_configs(config)`，来自 `opencc_backend.configs`。

**验证（自动化）**：

- `inspect_dictionary` 带 profile 规则时 `matched_rules` 非空；
- s2twp 下 `comparisons` 的配置名为 `("s2t","s2tw","s2twp")`。

---

### L-16 保留期清理从未被调用；历史"书名"列恒为空（P2，代码确认）

**位置**

- `logging_ext/retention.py:36-110` 没有任何调用方；`docs/privacy.md` 说明它是"显式操作"，但界面没有入口。JSONL 日志与 `history/index.json` 会无限增长，每次 `record_session` 都要全量加载并校验整个索引。
- `ui/history_window.py:91` 读取 `summary["book_name"/"book_path"]`，但 controller 的 summary（`controller.py:441-470`）从不写这两个字段。

**修改要求**

1. 历史窗口增加"清理旧记录…"：先 `cleanup(dry_run=True)` 显示将删除的会话数和日志文件数，确认后执行。默认参数使用 `retention_policy()`。
2. summary 增加 `book_label`：取 `bk.get_epub_filepath()` 的文件名（basename）。无路径时为空。
   - 不写入 dc:title：书名属于书籍内容还是元数据，需要用户确认隐私边界；本条不做此决定。
   - `docs/privacy.md` 相应补一句说明。
3. 历史窗口"书名 / 文件"列显示 `book_label`；旧记录为空时显示"—"。

**验证（自动化）**：

- 历史窗口 fake 测试：点击清理 → dry-run 结果显示 → 确认后 `index.json` 会话数减少、对应 `*.jsonl` 被删除；取消则不变。
- controller 集成测试：fake book 提供 `get_epub_filepath` 返回 `/x/书.epub`，历史记录的 summary 含 `book_label == "书.epub"`，且不含正文字段（沿用 `_TEXT_KEYS` 隐私断言）。

---

### L-17 `run_options` 把过期字段带进方案（P2，代码确认）

**位置**：`ui/run_options.py:87-94`。`values()` 先展开 `self._extra`，其中包含 `profile_options()` 返回的完整方案字典（`attributes`、`scope`、`segmentation`、`protected_elements` 等），再保存进 `preferences["run_options"]`。随后 `current_profile` 会把这些字段带入新方案。

**结果**：保存的方案中 `attributes` 可能与 `convert_alt/convert_title/convert_aria_label` 不一致（`profiles.py:158-169` 用的是 `setdefault`）。转换本身读的是 `convert_*` 标志，所以目前不影响输出，但会影响方案文件、`settings_hash` 和用户对方案的理解。

**修改要求**

1. `values()` 只输出白名单键：面板上的复选框、下拉框，以及 `profile_id`、`ruleset_ids`。`_extra` 只用于初始化控件，不再原样输出。
2. `current_profile` 根据 `convert_*` 重新生成 `attributes`。
3. 转换设置对话框顶部显示"当前方案：<名称>"。当前值与方案文件不同时加"（已修改）"，比较时使用 `settings_hash`。

**验证（自动化）**：

- 保存的方案中 `attributes` 与三个 `convert_*` 标志一致；
- `run_options` 不含 `scope/segmentation/attributes`；
- 加载方案后修改一个选项，标签出现"已修改"。

---

## 4. UI 调整

### U-01 "返回设置"不能修改文件范围（P1，代码确认）

**位置**：`app/controller.py:104-118` 在循环外只调用一次 `choose_scope`；`241-248` 的"返回设置"只回到转换设置对话框。转换设置对话框也没有"上一步"。

**修改要求**

1. controller 循环改为 `while True: scope → config → plan → preview`。
2. 转换设置对话框增加"上一步（更改文件）"按钮，返回值区分"取消 / 上一步 / 继续"。
3. 从预览"返回设置"时回到范围对话框：预填上一次的范围模式与勾选；再次"继续"时回到转换设置，预填上次选项。
4. 每次重新进入分析都重新冻结 `TargetSelection`、重新创建 workflow 与 `snapshot_guard`，旧计划与决定全部丢弃，与现有 `docs/rules-and-profiles.md` 的描述一致。
5. `SessionState` 迁移沿用 PREVIEWING → SCANNING。设置阶段反复返回不新增状态；如需区分，在 SCANNING 内部处理。

**约束**：不变量 18：返回和重新设置的全过程 `writefile` 为 0。未被新范围选中的文件读取次数为 0。

**验证（自动化）**：在 `tests/integration/test_plugin_conversion.py` 增加用例。

- `choose_scope` stub 第一次返回 `("a",)`、第二次返回 `("c",)`；`show_preview` stub 第一次返回 `back_to_settings=True`，第二次全部接受。
- 断言 `choose_scope` 调用 2 次；`b` 读取 0 次；`c` 被写入；`a` 写入 0 次。
- 断言第二次 `show_preview` 收到的计划只含 `c`。

**验证（手动）**：在 Sigil 中预览后点"返回设置"，再改选另一章，确认预览只包含新选的章。

---

### U-02 Checkpoint 提醒时机错误（P1，代码确认；Sigil 模态行为需宿主实测）

**位置**：`ui/preview_window.py:836-860` 在点"应用"时弹出。提示文字要求用户"应用前请先在 Sigil 中建立 Checkpoint"，按钮是"我已建立 Checkpoint，继续"。

**问题**：插件运行期间 Sigil 主窗口被插件运行对话框占用（需在目标 Sigil 版本实测并记录版本）。用户此时无法去建立 Checkpoint，只能取消整个插件，丢掉全部预览决定。

**修改要求**

1. 在范围对话框顶部加一条可关闭的提示条："开始前建议先在 Sigil 中建立 Checkpoint；插件运行期间无法操作 Sigil 主窗口。"受同一个"以后不再提示"偏好控制。
2. 应用时的确认改写为"插件修改无法用 Ctrl+Z 撤销。确认你已在启动插件前建立 Checkpoint 或备份？"，按钮改为"已备份，继续应用"和"返回预览"。默认按钮仍是"返回预览"。
3. 提示文字全部进入 i18n 目录（见 U-15），不再使用 `_LOCAL_TEXT`。

**验证（自动化）**：

- fake 范围对话框：`checkpoint_notice_enabled()` 为真时提示条可见，为假时隐藏；
- 在提示条上勾选"不再提示"后，`hide_checkpoint_notice` 被调用一次；
- 应用确认沿用现有测试，改为断言新文案键。

**验证（手动）**：记录 Sigil 版本号，确认插件运行时主窗口不可操作；确认提示条三语显示正常。

---

### U-03 预览中 Esc/关闭/取消直接丢弃全部决定（P1，代码确认；Esc 行为需宿主实测）

**位置**：`ui/preview_window.py:585` 取消按钮直接 `reject`。QDialog 默认按 Esc 或点标题栏关闭也会走 `reject`，controller 随即取消整个会话（`controller.py:249-260`）。

**修改要求**

1. 预览对话框改用一个小的 QDialog 子类，覆盖 `reject()`：
   - 已有任何决定时，弹确认"放弃本次预览中的 N 项决定并退出？"，默认按钮"返回预览"；
   - 没有决定时直接退出。
2. "返回设置"同样确认（与原设计文档 `ui-interaction-optimization-plan.md` 第 6 节一致）。
3. 预览取消后显示与分析取消一致的结果提示 `result.cancelled`。目前预览取消后没有任何提示（`controller.py:249-260`）。

**验证（自动化）**：fake 测试。

- 有 1 项决定时调用 `reject()`：确认回调被调用；选择"返回预览"时 `dialog` 未关闭且决定保留。
- 无决定时：确认回调未调用，直接关闭。
- controller 集成测试：预览返回未接受时 `show_result(status="cancelled")` 被调用一次。

**验证（手动）**：在 Sigil 中做几项决定后按 Esc、点关闭按钮，都会先弹确认。

---

### U-04 预览列表可读性（P1，代码确认）

**位置与现状**

- `ui/preview_window.py:682-687`：每行格式为 `? chapter01: '汉字' → '漢字'`：
  - 显示的是 manifest ID，不是文件路径；元数据显示为 `urn:opencc-for-sigil:metadata`；
  - 使用 Python `repr`，带引号，换行显示为 `\n`；
  - 状态只用 `? ✓ ×` 符号表示。
- `ui/preview_window.py:523-528`：文件筛选下拉框同样列 manifest ID，按 ID 排序；类别（`character/phrase/regional/variant/quotation/user_rule/language_metadata`）和风险（`LOW/REVIEW/HIGH`）显示原始英文代码。
- `core/planner.py:143-159`：`context_before/after` 取原始源码前后 32 个字符，包含标签和实体（如 `<p class="x">`）。详情区只显示"转换前"，没有"转换后"。
- 变更的 target 在 L-02 修复前可能显示 `&gt;` 之类的转义。

**修改要求**

1. 列表改为 `QTableView` + 自定义 `QAbstractTableModel`，列为：状态 | 文件 | 原文（含上下文）| 转换后 | 类别 | 风险。
   - 状态列用文字"接受/跳过/待定"加颜色，不能只靠颜色区分（原设计第 8 节要求）；
   - 文件列显示 href；
   - 类别和风险用本地化标签，风险 HIGH/REVIEW 加粗。
2. 抽出纯函数 `format_change_row(change, href_by_id, translator) -> tuple[str, ...]`，供模型和测试共用。
3. 上下文改为纯文本：在 `TokenChange` 增加 `text_context_before/after`（取自所在 `TextTarget.source_text`，最多 20 字，越界加 `…`），保留原有源码上下文字段供"显示源码"切换。
4. 详情区显示两行，变化部分用 `【】` 标出：

   ```text
   转换前：……他使用【软件】处理……
   转换后：……他使用【軟體】处理……
   规则：OpenCC:s2twp    类别：地区词汇    风险：需复核
   ```

5. 文件筛选按书脊顺序列 href，并显示每个文件的"变更数 / 待定数"。

**约束**：纯展示层修改，不改变 change_id、span、决定语义，也不改变 `ConversionPlan` 中已有字段的含义。

**验证（自动化）**：新增 `tests/unit/test_preview_model.py`。

- `format_change_row` 对含换行、引号、非 BMP 字符的变更输出不含 `repr` 引号与 `\n` 转义；
- 文件列为 href；元数据显示为本地化的"OPF 元数据"；
- 纯文本上下文不含 `<`；
- 模型 `rowCount` 与筛选后条目数一致；筛选变化后当前选中项按 change_id 保持（见 U-05）；
- 1 万、5 万条变更时构建模型 < 200 ms（纯 Python 部分）。

**验证（手动）**：三种界面语言各截一张预览截图，检查长路径省略、125%/200% 缩放下的可读性。

---

### U-05 决定效率：自动前进、快捷键、应用按钮说明（P1，代码确认）

**现状**

- 接受/跳过单项后选中项不动，用户要自己点下一条。
- 没有快捷键。
- 筛选变化后按旧行号恢复选中项（`preview_window.py:653-676`），会落到另一条变更上。
- "应用"禁用时没有原因：`preview.incomplete` 键在代码中从未使用。
- 按钮文字不含数量（原设计要求"应用到 N 个文件"）。
- 窗口没有设置默认按钮，Enter 行为取决于焦点链。

**修改要求**

1. 单项接受/跳过后自动选中下一个"待定"项；没有待定项时停在原处。
2. 快捷键（`QShortcut`，在对话框范围内生效）：`A` 接受此项、`S` 跳过此项、`N` 下一个待定、`Shift+N` 上一个待定。`↑/↓` 保留表格默认行为。
3. 筛选或批量操作后按 change_id 恢复选中项；原项不在当前筛选中时选第一行。
4. "应用"按钮文字随状态变化：
   - 有待定项时禁用，旁边标签显示 `preview.incomplete`，并附"剩余 N 项待定"；
   - 全部决定后显示"应用 {accepted} 项修改到 {files} 个文件"；
   - 接受数为 0 时显示"完成（不修改）"。
5. 所有按钮 `setAutoDefault(False)`，预览窗口不设默认按钮，Enter 不触发应用或批量操作。
6. 按钮分三组：
   - 单项/本文件：接受此项、跳过此项、接受本文件、跳过本文件；
   - 筛选/全部：接受筛选项、跳过筛选项、接受全部、跳过全部；
   - 底部右侧：导出报告、返回设置、取消、应用（主按钮）。

**验证（自动化）**：扩展 `tests/unit/test_preview_window.py`。

- 3 条变更，当前第 0 条，`_accept_this()` 后当前行为 1；第 1 条已决定时跳到 2。
- 按 change_id 恢复：设置筛选后当前项 id 不变。
- 应用按钮文字三种状态各一个断言。
- 统计 `setAutoDefault(False)` 的调用覆盖所有按钮（fake 按钮记录调用）。

**验证（手动）**：在 Sigil 中只用键盘完成 20 项决定并应用；确认 Enter 不会触发应用。

---

### U-06 没有任何变化时仍弹出空预览（P1，代码确认）

**位置**：`app/controller.py:241-242` 无条件 `show_preview(planned)`。零变更时预览窗口列表为空，大部分按钮禁用，用户必须点"应用已接受的修改"才能结束。

**修改要求**

1. `planned_change_count == 0` 时跳过预览，直接显示结果对话框（`result.noop`），提供"返回设置"和"关闭"两个按钮。
2. "返回设置"走 U-01 的循环。
3. 若有 `SOURCE_INVALID_XHTML` 等诊断（L-13），结果对话框列出这些文件。

**约束**：零变更路径 `writefile` 为 0；summary 与 history 行为与现有 noop 一致（现有 `result.noop` 测试保留）。

**验证（自动化）**：集成测试。fake book 全部是已转换内容：`show_preview` 未被调用，`show_result(status="success", accepted_changes=0)` 调用一次，写入 0 次；返回设置分支再次调用 `choose_scope`。

---

### U-07 语言标签组跨文件联动不可见（P1，代码确认）

**位置**

- `core/planner.py:61-65` 所有语言变更共用 `group_id="language_metadata"`，覆盖所有 XHTML 与 OPF。
- `ui/preview_window.py:800-818` 的"接受本文件/跳过本文件"会顺带决定整个组，因此其他文件的语言变更也被改动，界面无任何说明。

**修改要求**

1. 分组变更的行加标记"语言标签组（共 N 处 / M 个文件）"，详情区说明"此项与其他文件的语言标签一起接受或跳过"。
2. "接受本文件/跳过本文件"只作用于本文件的非分组变更。若本文件含分组变更，按钮旁提示"语言标签组需单独决定"，并提供"接受语言标签组 / 跳过语言标签组"两个按钮（仅在存在分组时显示）。
3. 单项接受/跳过分组变更时仍决定整个组（现有行为），但在状态栏显示"已同时更新 N 处语言标签"。
4. `_accept_file/_reject_file` 中 `_decide_group` 的重复调用改为先收集 group_id 集合再逐组处理，避免 O(变更数×总数) 的重复遍历。

**约束**：`workflow.finalize` 的"组内全接受或全跳过"校验（`workflow.py:273-280`）保持不变。

**验证（自动化）**：

- 两文件各有 1 个语言变更和 1 个普通变更。对文件 A "接受本文件"后，A 的普通变更为接受、两个语言变更仍为待定；
- "接受语言标签组"后两个语言变更都为接受；
- `finalize` 不抛异常。

---

### U-08 转换设置对话框布局与联动（P1，代码确认）

**现状**

- `ui/run_options.py:37-83`：12 个复选框 + 6 个下拉框平铺在一个 `QFormLayout` 里，外面套一个高 280-420 的滚动区。
- 分组标题是"附加文档与语言"，但里面包含属性、ruby、code、引号、中转等无关项。
- 转换方向下拉框 16 项不分组，没有"转换方向"标签（`config.direction` 键未使用）。
- Jieba 状态标签无论是否相关都显示，失败时直接显示技术原因字符串（`preview_window.py:953-969`）。
- 底部按钮没有 stretch，取消/继续会被拉宽铺满整行（`preview_window.py:924-929`），与范围对话框不一致。
- 工具按钮（方案、另存为方案、规则/沙箱、历史/报告、自检）挤在一行（`run_options.py:96-103`）。其中"自检"只以 JSON 文本显示结果（`settings.py:140-145`）。
- 界面不显示当前方案（见 L-17）和启用的规则集（见 L-03）。

**修改要求**

1. 布局自上而下：
   - 方向区：带标签的方向下拉框，按"简繁 / 地区字形与词汇 / 日文"分组，用分隔项；下面是配置说明和 Jieba 复选框。Jieba 失败原因放进 tooltip 和"详情"。
   - 方案区："当前方案：X（已修改）"，右侧为 [方案…] [另存为…]；下一行"规则集：default, mine"与 [规则…]。
   - 文档区（默认展开）：NAV、NCX（标"全书"）、OPF 元数据（标"全书 · 高风险"）；当前范围不含导航文档时，NAV 复选框禁用并说明原因。
   - 高级选项（默认折叠，`QToolButton` 箭头展开）：
     - 属性：alt、title、aria-label；
     - 内容：ruby 注音、code/pre、数字汉字引用；
     - 标点：引号、竖排标点；
     - 语言标签：模式、风格、地区；
     - 诊断：混合脚本、对比官方配置（较慢）；
     - 高风险：强制中转与中转链。
   - 底部：左侧"工具 ▾"菜单（历史/报告、自检），右侧用 `QDialogButtonBox` 放 [上一步] [取消] [分析并预览]，按钮顺序遵循平台习惯。
2. 联动规则使用 L-05 的 `option_enablement`。
3. 自检结果改为表格：检查项 / 通过或失败，加"复制诊断"按钮；原始 JSON 放进"详情"。
4. 折叠状态与对话框尺寸保存在 `preferences["ui"]`。

**约束**：Jieba 复选框仍须遵守不变量 15；布局调整不改变 `values()` 的键集合（L-17 白名单除外）。

**验证（自动化）**：

- `option_enablement` 真值表（与 L-05 共用）；
- fake Qt 构造对话框：高级区默认折叠，展开状态写入偏好；
- 范围不含 nav 时 NAV 复选框禁用。

**验证（手动）**：三语、125%/200% 缩放各截图一张，检查中英文按钮不截断、无横向滚动。

---

### U-09 范围对话框（P2，代码确认）

**现状**（`ui/preview_window.py:994-1223`）

- "单个文件"模式仍使用复选框，要求恰好勾一个；勾了两个时点"继续"才报错。
- "书脊正文/全部 XHTML"模式下列表被禁用，但仍显示用户之前的手动勾选，看起来像只处理这几个文件。
- 列表按 `text_iter` 顺序，没有书脊顺序，也没有导航文档标记。
- 筛选时计数不显示可见项数量。
- 没有默认按钮，Enter 的行为取决于焦点。
- `scope.all` 文案写"含 XHTML 导航"，但转换设置里的 NAV 选项可以排除导航文档（`adapter.py:104-106`），两处矛盾。

**修改要求**

1. 单个文件模式改为单选：隐藏复选框，点击行即选中；从其他模式切回时保留原勾选状态。
2. 书脊/全部模式：列表只读，勾选状态实时反映将被处理的文件（书脊模式勾书脊文件，全部模式全勾）；切回自定义模式时恢复用户原来的勾选。
3. 列表按书脊顺序排列，非书脊文件按路径排在后面；导航文档加"（导航）"后缀。
4. 计数显示"已选 3 / 28（筛选后可见 5）"。
5. "继续"设为默认按钮；筛选框里按 Enter 不触发"选择可见项"。
6. 没有初始选择时，列表上方显示引导文字"在列表中勾选要转换的文件"。
7. 把 NAV 选项移到范围对话框，放在"全部 XHTML"下方，或者把 `scope.all` 文案改为"全部 XHTML"，由 NAV 选项单独说明。二选一，推荐前者。

**验证（自动化）**：fake 测试。

- 单文件模式点选第二行：`selected_ids() == (id2,)`；
- 切换到全部再切回：原勾选恢复；
- 书脊模式勾选状态等于 `spine_ids`；
- 排序：书脊文件在前。

---

### U-10 不可取消阶段的进度窗与写回阶段（P2，代码确认；Qt 行为需宿主实测）

**位置**

- `app/controller.py:276-294`：staging/verify 使用 `disable_cancel()` 去掉取消按钮，但标题栏关闭按钮仍可用。关闭会触发 `canceled` 信号，窗口消失，而流程继续写回，用户以为已取消。
- `app/controller.py:300-301`：写回（逐文件复读源哈希 + `writefile`）在进度窗关闭后进行，没有任何状态显示。
- Qt 源码中 `QProgressDialog::cancel()` 会隐藏对话框并重置 `shown_once`，之后的 `setValue` 可能让窗口重新出现，分析阶段点取消后可能出现"消失又弹回"。需在真实 Qt 中确认。

**修改要求**

1. 预览之后使用一个进度窗覆盖 准备修改 → 校验 → 写回 三个阶段，新增 `progress.phase.committing`。
2. 不可取消阶段：去掉关闭按钮（`setWindowFlag(Qt.WindowCloseButtonHint, False)`），并通过事件过滤器忽略 `QEvent.Close` 与 Esc；`_mark_cancelled` 在这些阶段不改变状态。
3. `workflow.commit` 增加可选 `progress` 回调：复读源哈希与写入各算一个阶段，或合并为"写回 i/N"。
4. 分析阶段取消：捕获 `canceled` 后自行调用 `setLabelText(正在取消…)` 并重新 `show()`，避免"消失又出现"（与 L-10 的 `set_cancelling` 合并实现）。

**约束**：写回阶段绝不可取消（原设计第 7 节）；进度回调不得调用任何 BookContainer API 以外的写操作。

**验证（自动化）**：扩展 `tests/unit/test_progress_reporter.py`。

- 不可取消阶段 fake 对话框发出 `canceled` 后，`cancelled()` 仍为 False；
- 集成测试：staging 期间模拟关闭事件，写回仍完成，结果为 success，进度阶段序列含 `committing`。

**验证（手动）**：在 Sigil 中对大书点应用，校验阶段尝试点关闭或按 Esc，窗口不关闭；分析阶段点取消，窗口显示"正在取消"而不是消失后再弹回。

---

### U-11 结果对话框（P2）

**修改要求**

1. 成功结果末尾加一句"修改已交给 Sigil，请在 Sigil 中检查并保存 EPUB。"（原设计第 6 节已要求，但目录里没有这句话）。
2. 把长句改为分行的标签式：

   ```text
   已分析：38 个文件
   已写回：37 个文件（应用 512 项修改，跳过 9 项）
   未写回：1 个文件（其中没有建议变更：1 个）
   ```

   这样可以避免英文单复数和包含关系的歧义；数值字段与现有 summary 语义保持一致（见 `docs/review-v001-to-head-luna-plan.md` 的 A 批次）。
3. 提供"查看报告"按钮，打开本次会话的 Markdown 报告（复用 `settings.inspect_report`）。

**验证（自动化）**：沿用 `tests/unit/test_result_counts.py`，改为逐行断言三语输出；partial/cancelled/noop 各一例。

---

### U-12 方案窗口（P2）

**现状**（`ui/profile_window.py`）

- 只能编辑名称、方向（不含 Jieba，见 L-04）和逗号分隔的规则集 ID。
- "保存"同时承担"选择并关闭"。
- "新建"用默认值而不是当前设置。
- 不能删除方案，名称可以重复。
- 标签来自私有 `_LABELS`。

**修改要求**

1. 左侧方案列表，右侧只读摘要（方向、主要选项、规则集）。
2. 按钮：[使用] [重命名] [复制] [删除] [关闭]。"使用"只切换当前方案，不写文件；删除需要确认，且不能删除当前正在使用且已修改的方案。
3. "从当前设置新建"取代"新建"。
4. 规则集用复选列表选择已存在的规则集，不再手输。
5. 名称重复时提示。

**验证（自动化）**：

- "使用"不改变 `profiles/` 下任何文件的 mtime；
- 删除后文件移除，偏好中的 `profile_id` 被清除；
- 重名保存被拒绝。

---

### U-13 规则窗口（P2）

**现状**

- 进入前先弹 `QInputDialog.getItem` 让用户输入"规则集 ID"（`app/settings.py:80-88`）；ID 不合法时抛出的 `RuleValidationError` 显示为英文警告。
- 范围下拉框显示 `global/profile/book` 原文（`rules_window.py:348-349`）。
- 8 个按钮挤在一行。
- 沙箱只显示命中数量，不显示命中了哪条规则。
- 测试输入是单行输入框。
- "No official conversion callback supplied"、"Enter text for dictionary inspection"、"UserRule:" 等文字硬编码英文。

**修改要求**

1. 规则集选择放进规则窗口顶部：下拉框 + [新建] [重命名]，去掉前置的 `QInputDialog`。
2. 范围显示本地化名称：全局 / 当前方案 / 当前书。
3. 按钮分组：编辑（新增、更新所选、删除）| 导入导出 | 测试（测试、词典检查）| 底部 [取消] [保存]。
4. 沙箱输出列出命中规则（规则 id、源 → 目标、位置）；测试输入改为多行。
5. 所有文字进入 i18n 目录。

**验证（自动化）**：

- 新建规则集 ID 含 `/` 时显示本地化错误，且不创建文件；
- 沙箱输出包含命中规则的 source；
- 窗口内切换规则集后，表格内容随之刷新。

---

### U-14 历史窗口（P2）

**现状**（`ui/history_window.py`）

- 表格单元格可编辑；列不自适应宽度；不能排序。
- 状态显示原文 `success`；日期是 ISO 原文。
- "包含完整差异"复选框永远不可用：`full_diff_provider` 从未传入（`settings.py:148-152`），勾选后导出只会弹出"不可用"。
- 只支持 PySide6，与其他窗口的 PyQt5 回退不一致。
- 私有 `_LOCAL_CATALOGS` 翻译。

**修改要求**

1. 表格 `NoEditTriggers`、整行选择、列宽拉伸、按日期倒序且可排序；双击行等同"查看报告"。
2. 状态本地化；日期显示为本地时间 `YYYY-MM-DD HH:MM`。
3. 移除历史窗口里的"完整差异"复选框。历史中本来就没有差异，完整差异只能在预览导出（`docs/privacy.md` 已说明）。
4. 增加 L-16 的"清理旧记录…"按钮。
5. Qt 加载使用 C-01 的公共函数。

**验证（自动化）**：`history_rows` 输出本地化状态和格式化日期；fake 表格的编辑触发器为 NoEditTriggers；窗口中不存在完整差异复选框。

---

### U-15 i18n 完整性（P2，代码确认）

**现状**：除三份 JSON 目录外，还有三套私有翻译表，绕过了 `ui/i18n.py:_validate_catalogs` 和 `tools/validate_artifact.py` 的键/占位符检查：

- `ui/preview_window.py:149-223` 的 `_LOCAL_TEXT`（书脊、筛选、返回设置、Checkpoint、诊断、导出）；
- `ui/profile_window.py:12-40` 和 `ui/rules_window.py:15-112` 的 `_LABELS`；
- `ui/history_window.py:11-66` 的 `_LOCAL_CATALOGS`。

另外 `ui/preview_window.py:237-254` 的 `CONVERSION_LABELS` 是简体中文兜底，英文界面缺键时会显示中文。

用户可见的原始英文包括：
- 所有 `QMessageBox.warning(..., str(exc))`（`preview_window.py:987`、`run_options.py:131`、`rules_window.py:438/535/552`、`profile_window.py:187`）；
- 预览诊断文字（`MIXED_SCRIPT: current text contains mixed simplified and traditional evidence`、`INLINE_BOUNDARY: ...`）；
- `options.region_required` 键存在却未使用，界面直接显示 `target_language` 的英文 ValueError。

**修改要求**

1. 私有翻译表全部并入三份 JSON，按前缀命名（`preview.*`、`profile.*`、`rules.*`、`history.*`），删除私有字典与 `_ui_text` 回退。
2. 删除 `CONVERSION_LABELS`，缺键由测试拦截。
3. 为用户可见错误建立"错误码 → i18n 键"映射：
   - 规则校验用 `RuleValidationError.field/index` 组织本地化句子；
   - 冲突用 kind + 源文本；
   - 语言地区缺失用 `options.region_required`；
   - 方案不可用、强制中转链不匹配各新增一个键。
   - 对话框显示本地化句子，原始英文放进"详情"。
4. 诊断码映射为本地化名称和一句说明；预览顶部按诊断码汇总计数，例如"混合简繁 12 处、跨内联边界 3 处"，不再逐条拼接原文。
5. 新增的运行时必需键加入 `tools/validate_artifact.py:46` 的 `_I18N_REQUIRED_KEYS`。

**验证（自动化）**

- 扩展 `tests/unit/test_i18n.py`：
  - 静态检查 `ui/` 下不存在 `_LOCAL_TEXT`、`_LABELS`、`_LOCAL_CATALOGS`、`CONVERSION_LABELS`；
  - 三语目录键集合相等；
  - 每个 `config.<id>` 覆盖 `V1_CONFIGS`；
  - 每个诊断码和错误码都有对应键。
- 扩展 `tests/unit/test_artifact_validator.py`：删除任一新增必需键时归档校验失败。

---

## 5. 代码结构（P3）

### C-01 重复代码与隐式传参

**现状**

- `_load_qt_widgets`、`_ensure_application`、`_application` 在 `preview_window.py`、`profile_window.py`、`rules_window.py`、`history_window.py` 各有一份，且回退策略不一致（历史窗口没有 PyQt5 回退）。
- `STANDARD_CONFIGS` 与 `_base_config_options` 在方案窗口和规则窗口各一份，与 `opencc_backend.configs.V1_CONFIGS` 重复。
- 用模块级全局变量传参：`ui/run_options.py:15-24`（`_initial/_metadata_available/_services`）、`ui/preview_window.py:146-147`（`_translator/_jieba_unavailable_reason`）。
- controller 在构造后给 `RunSettings` 注入属性（`controller.py:170-173` 的 language、session_id、profile、backend）；`export_preview` 直接读 `self.profile`，缺少时会 AttributeError。
- 占位模块 `ui/main_window.py`、`ui/theme.py`、`ui/widgets.py` 只有一行文档字符串，`widgets.py` 还写着 "Tk/ttk"。
- `core/planner.py:118-121` 的 `plan_not_implemented`、`core/models.py:154-158` 的 `ChineseConverter` 占位，以及多处"兼容别名"函数，没有调用方。

**修改要求**

1. 新增 `ui/qt.py`，集中提供 `load_qt()`、`ensure_application()`、`exec_dialog(dialog)`；四个窗口统一改用。
2. 配置列表统一从 `opencc_backend.configs` 导入。
3. `RunOptionsPanel` 与 `_ConversionConfigDialog` 通过构造参数接收 `initial`、`metadata_available`、`services`、`translator`、`jieba_state`；删除模块级全局变量。`configure_run_options` 暂时保留为薄兼容层，供现有测试迁移后删除。
4. `RunSettings` 在构造时接收 `language`、`session_id`；`profile` 与 `backend` 通过显式方法 `bind_run(profile, backend)` 设置；`export_preview` 在未绑定时抛出清晰错误。
5. 删除占位模块与无调用方的别名前先全仓 grep（含 `tests/` 与 `tools/`），确有调用方的保留。

**约束**：纯重构，不改变任何行为，不改测试断言语义；单独提交，放在所有功能批次之后。

**验证**：`make check` 全绿；`ruff check .` 无新告警；`grep -rn "_ensure_application\|_load_qt_widgets" plugin/` 只剩 `ui/qt.py`。

---

## 6. 建议批次与提交顺序

每个批次先检查工作区、保留已有正确改动；批次内每个条目单独提交，提交信息沿用仓库风格。

| 批次 | 条目 | 建议提交主题 | 前置 |
| --- | --- | --- | --- |
| A 正确性 | L-01、L-02 | `fix: pair quotations across inline and rule boundaries`、`fix: escape only markup-significant characters in patches` | 无 |
| B 设置持久化 | L-03、L-04、L-05、L-06、L-17 | `fix: keep rule sets and profile configs across runs` 等 | 无 |
| C 性能 | L-07、L-08、L-09、L-10 | `perf: compile rule overlays once per plan`、`perf: probe native Jieba in the background` | A（L-01 改动 `_convert_rules`，需先合入） |
| D 失败与恢复 | L-11、L-12、L-13 | `ui: report failures with localized recovery guidance` | 无 |
| E 流程 | U-01、U-02、U-03、U-06、U-10 | `ui: return to scope selection and guard preview exits` | D（错误对话框复用） |
| F 预览 | U-04、U-05、U-07 | `ui: show readable preview rows and keyboard review` | E |
| G 设置与工具窗口 | U-08、U-09、U-12、U-13、U-14、L-14、L-15、L-16 | `ui: group conversion settings and tool windows` | B、C（L-05、L-08 的状态） |
| H i18n 与结构 | U-11、U-15、C-01 | `i18n: move private catalogs into shipped resources`、`refactor: share Qt helpers` | 其余全部 |

每个批次结束运行：

```sh
mise exec -- uv run pytest
mise exec -- ruff check .
git diff --check
```

最终状态再运行一次完整检查与打包校验：

```sh
make check
mise exec -- uv lock --check
mise exec -- uv run python tools/build_plugin.py --output /tmp/OpenCCForSigil_review_candidate.zip
mise exec -- uv run python tools/validate_artifact.py /tmp/OpenCCForSigil_review_candidate.zip
mise exec -- uv run python tools/benchmark_rules.py
```

本机归档只含 macOS arm64 payload；四平台 `--require-runtimes` 校验仍需 CI 产物，不能用本机结果代替。

---

## 7. 手动宿主验收清单（由用户在 Sigil 中完成）

准备一本测试副本，至少包含：
- 5 个正文 XHTML、XHTML 导航、NCX；
- 一个含 `<p>"……<em>……</em>……"</p>` 的章节；
- 一个含 `a > b` 的超长段落（> 1024 字）；
- 一个不良构章节（仅用于 L-13）。

记录 Sigil 版本、OS/架构和样本大小。

1. 启动插件：范围对话框出现 Checkpoint 提示条；点"继续"后设置对话框 0.5 秒内出现，Jieba 状态随后更新（L-08、U-02）。
2. 开启"角括号"引号：预览中跨 `<em>` 的闭引号显示为 `」`；超长段落中的 `>` 不出现在变更中（L-01、L-02）。
3. 新建规则集并加入规则，完成转换；关闭插件再次启动：规则集仍在"规则集"一行中，规则仍命中（L-03）。
4. 保存一个 Jieba 方案和一个强制中转方案，重新打开"方案"加载后值不变（L-04、L-05）。
5. 预览中做几项决定后按 Esc：出现确认；点"返回设置"：回到范围对话框，可以改选文件（U-01、U-03）。
6. 键盘 A/S/N 完成决定；应用按钮文字随状态变化；Enter 不触发应用（U-05）。
7. 校验阶段尝试关闭进度窗：窗口不关闭；写回阶段显示进度（U-10）。
8. 不良构章节：预览中标注"已跳过"，其他章节正常写回；故意制造 verify 失败时出现本地化错误对话框，"复制诊断"可用（L-11、L-13）。
9. 手动把 `preferences.json` 改坏再启动：出现备份提示，插件可用（L-12）。
10. 三种界面语言、125%/200% 缩放下各截图：设置、预览、结果三个窗口，无英文残留、无截断（U-08、U-15）。
11. 保存 EPUB 并重新打开，确认内容与预览一致。

未完成的平台或步骤在交付说明中标记"未验证"，不得写成通过。

---

## 附录 A：本次复现与测量方法

脚本位于同目录的 `scripts/round1/`，用 `.venv/bin/python docs/reviews/2026-09-23/scripts/round1/<脚本>` 运行，工作目录不限，使用仓库自带的真实 payload。下表"结果"一列是基线 `b2f674b` 上的输出；在修复后的代码上运行会得到修复后的结果。

| 项目 | 脚本 | 方法 | 结果 |
| --- | --- | --- | --- |
| 引号配对（L-01） | `check_quotes.py` | fake Book + `ConversionWorkflow(...).plan()`，`quotation_mode="corner"`，打印 `apply_changes` 结果 | 见 L-01 复现 |
| 转义（L-02） | `check_escape.py` | 同上，超长文本 `"汉"*1500 + " a > b " + "汉"*1500`；`verify_staged_file` 仍通过 | 输出含 `&gt;` |
| 规则性能（L-07） | `bench_rules.py`、`prof_rules.py` | 随机 80 字节点，`Rule(type="exact", direction="s2t", source=随机2字)` 去重，计时 300 节点并推算 3000 节点；cProfile 看热点 | 见 L-07 表格 |
| 启动（L-08）与转换选项开销（L-09） | `bench_backend.py` | 分别计时 `OpenCCBackend("s2t")`、`self_test`、`available_configs()`；s2twp 3000 节点四种开关组合 | 0.197 s / 0.024 s / 2.236 s；0.309 / 0.367 / 1.257 / 1.320 s |
| 预览单击（U-04 参考） | `bench_preview.py`（仅适用于基线） | 仿照 `tests/unit/test_preview_window.py` 的 fake 控件，调用 10 次 `_accept_this` 取均值 | 2k 条 0.6 ms、2 万条 7.6 ms、5 万条 23.7 ms（不含 Qt 绘制） |

预览单击成本在 5 万条时仍在可接受范围。U-04 改用模型/视图主要是为了可读性和筛选、批量刷新时的构建成本，不是因为单击本身慢。改用前后都应在真实 Qt 中测量筛选切换和"接受全部"的耗时。
