# v0.0.1-beta → HEAD 审查采纳与 Luna 修改方案

日期：2026-09-08。初始核对 HEAD：`9f353e1`。状态：A–F 已实施并独立提交；E 保留严格校验并补充计数证据，未引入没有原子快照保证的整树缓存。剩余 G 版本发布治理与 payload 瘦身专项，本轮不 push/tag/release。

## 结论

优先修复结果文案、必需资源闸、缓存失效范围和 runfiles 回退。采纳哈希开销优化方向，但不能用常驻 `(root, sha)` 缓存替代延迟导入校验。进度模态需要结合 Sigil 独立进程边界设计，不能声称 `WindowModal` 会锁住宿主。版本在未发布开发期间保持上一版并非运行 bug，发布时必须同步。

| 编号 | 判定 | 处理批次 |
| --- | --- | --- |
| 1 | 文案歧义成立，统计集合有包含关系，数值本身不是相加错误 | A |
| 2 | 成立，缺少运行必需资源校验 | B |
| 3 | 成立，缓存命中可掩盖 workflow ref 变化 | B |
| 4 | notice 审计采纳；payload 瘦身需单独的派生载荷设计 | C / 后续专项 |
| 5 | 冷导入路径有重复全树校验，采纳优化但修订缓存生命周期与安全方案 | E |
| 6 | modeless 成立；“因此宿主可重入”和“WindowModal 可消除”不能据此推出 | D |
| 7 | 阶段间回退成立，采用明确分阶段重置 | D |
| 8 | 成立，磁盘上不存在候选不等于加载边界封闭；优先封堵 | C |
| 9 | 成立，使用公开 spec 工厂 | C |
| 10 | 清理采纳，但保留核心供非 UI 调用者使用的 scope 兼容入口 | F |
| 11 | 发布治理与示例歧义，分开发版本和历史规范示例处理 | G |
| 12 | 全量读入成立；字节码目前先被拒绝，不需要放宽为忽略后接受 | B |

## A：结果统计——先修文案，不改变已有日志字段

位置：`app/controller.py` 的摘要与 `show_result` 调用、`ui/preview_window.py`、三份 `resources/i18n/*.json`。

定义 N=分析目标、W=实际写回、U=无建议变更、NW=N−W。U 是 NW 的子集。保留 `files_not_written` 为总数；不要悄悄改成残差，避免日志消费者语义漂移。

成功例句：“已分析 38 个文件，实际写回 37 个；未写回 1 个，其中 1 个没有建议变更。”英文用 “1 file was not written, including 1 with no proposed changes” 或无单复数陷阱的标签式表达。繁体同步。用“没有建议变更”替代“没有可转换内容”，后者容易让用户误认为文件没有正文。

`result.done/skipped/partial` 都明确包含关系。部分失败中的 NW 还包括失败与尚未处理的文件，不能把 NW−U 统一称为“全部跳过”。若未来需要互斥分类，另加明确字段分别统计用户全部跳过、失败、尚未写入。

验收：2 个目标、1 写回、1 无变化；全部跳过；混合跳过；第 2 个写入失败；全部无变化；三语文案和日志都一致。原集成测试 NW=1/U=1 可以保留，替换固化歧义文案的测试。所有成功路径 N=W+NW，U≤NW。

## B：资源、CI 缓存与归档内存

### B1 必需资源

`tools/validate_artifact.py` 增加四个必需条目：

- `OpenCCForSigil/resources/defaults/conservative.json`
- `OpenCCForSigil/resources/i18n/en.json`
- `OpenCCForSigil/resources/i18n/zh-Hans.json`
- `OpenCCForSigil/resources/i18n/zh-Hant.json`

在归档中直接读取解析 JSON，检查 profile 被 controller 无条件访问的字段、类型、有效 scope，以及三语键/占位符一致。避免为了验证归档而 import 工作区 UI；否则工作区资源可能掩盖包内缺失。错误包含条目路径。schema 检查应复用现有契约或小型纯函数，不引入 JSON schema 新依赖。

验收：从实际构建 ZIP 分别删除每个资源、损坏 JSON、删 profile 必填项或语言 key/占位符，均失败；正常归档通过。精确描述 validator 覆盖的资源，不承诺能发现任意未知代码依赖遗漏。

### B2 缓存 key

`.github/workflows/ci.yml` 的 `hashFiles` 至少追加 workflow 本身、`tools/export_verified_payload.py`、`tools/merge_verified_payloads.py`；检查构建工具 import 的其他本地 recipe/helper 是否应纳入。保持平台隔离、PR 不复用缓存及命中后 hash 验证。

更稳妥的后续设计：把上游 commit 统一从 lock 读取，在恢复缓存前检查 lock 与 manifest 一致，再将该值传给 checkout，消除第三份 ref。若本批不重构，添加运行于缓存恢复之前的 workflow ref↔lock↔manifest 一致性检查。现有 `build_opencc_jieba.py` 在冷构建会校验实际源码 commit，但缓存命中跳过它，不能当成热路径闸。

验收：单独改变 workflow ref、export 或 merge 工具会改变 cache key 输入；ref 与 lock 不一致时即使模拟缓存命中也拒绝。不得自动重写 lock 接受一个新版本。

### B3 流式 ZIP tree hash

`_zip_tree_hash` 只收集并排序相对路径/成员索引，逐成员用 `archive.open()` 分块更新 digest；保持 `relative UTF-8 + NUL + bytes + NUL` 的既有契约。禁止持有全 payload 的字节列表。

现有 validator 在算树哈希前拒绝 `.pyc` 与 `__pycache__`，这与“独立校验任意输入 ZIP”不矛盾：任意输入可以被拒绝。继续拒绝字节码；补 `.pyo`，用路径组件/后缀精确匹配，避免 `.pyc` 子串误伤正常文件。不能为了让哈希一致而放行包内字节码。

五处散落的规则可先建立参数化契约测试；共享实现应放在不引入 vendor import 副作用的纯模块，并保证构建工具和插件都能找到它。不要让插件运行时 import `tools/`。

验收：新旧有效归档树哈希一致；大成员流式读取；字节码归档明确失败；篡改/缺失数据继续失败；路径穿越、重复条目、目录条目策略不退化。

## C：导入失败边界与第三方 notice

### C1 runfiles 回退（先于哈希缓存优化）

已核对官方 payload `opencc/__init__.py`：包内 native 导入的 `ImportError` 会被捕获，然后直接从 `payloads/src`、`payloads/src/pyd` 创建 spec 并执行 native loader。该路径不经过 meta_path finder，也不要求加入 sys.modules；事后检查无法撤销 native 初始化产生的副作用。

推荐小范围方案：保留第一次全局 `opencc_clib` 被 ImportError 阻止的兼容探测；但对**包内必需 native** `opencc.clib.opencc_clib` 的缺失、越界及 loader create/exec 阶段 ImportError，转换成项目自己的、非 ImportError 子类的完整性/来源异常，使官方代码不能继续 runfiles 回退。核对 `opencc.clib` 父包路径失败也应 fail-closed。不要全局 monkeypatch importlib，不要直接改官方 wheel 源码。

验收：受控子进程让包内扩展加载失败，同时在逃逸候选目录布置加载标记/探针；断言候选没有被打开或执行，导入失败后 finder 和模块清理正确。保留恶意 pyc、延迟导入、预加载伪模块、二次 native 复用和源码/native 篡改回归。探针不能仅依赖最终抛异常，必须证明执行前阻断。

### C2 ModuleSpec

extension 分支用 `spec_from_file_location(fullname, str(extension_path), loader=loader)` 替代私有 `_set_fileattr`。测试 `__file__`、`spec.origin`、loader、native 模块复用，以及已支持的平台路径。

### C3 notice 补齐

仓库目前没有单独的 marisa/darts 等 notice。参考源码中 marisa 0.3.1 `COPYING.md` 明确 BSD-2-Clause OR LGPL-2.1-or-later；可选择 BSD 分支满足该组件的分发条件，不能将双授权描述为必须同时承担两套条款。

按 pinned commit 和实际 wheel/构建输入列组件清单：marisa、darts-clone、rapidjson、tclap、pybind11、cppjieba；区分实际包含、只用于构建/测试、尚待确认。符号字符串可作为线索，不单凭符号推定精确版本/完整许可。从对应版本保留完整 license、copyright、适用 notice（含子文件例外），记录路径和来源。许可证放插件自有 `resources/third_party/` 并更新索引和 artifact required，不篡改原 wheel 数据。

验收：每个实际随包组件都有对应许可记录；必需 notice 缺失时包校验失败；原有 OpenCC/LICENSE/AUTHORS 保留。资料不完整的组件列明缺口，不宣称完成全面法律审计。

## D：进度与重入

Qt `show()` 本身不代表必须 modeless；modality 可以独立设置。当前 reporter 无 parent 且无 modality。`WindowModal` 只能限制窗口层级；Sigil API 指南明确插件运行在独立进程，插件 QApplication 的模态不能保证禁止另一个进程里的宿主操作。不能按“加一行 WindowModal 就消除宿主重入”验收。

实现顺序：确定插件自有窗口的 parent/生命周期；选择 WindowModal（有真实父窗口）或 ApplicationModal（插件进程内）；提交按钮设置运行态防重入。真实 Sigil 实测是否允许二次启动，由宿主行为决定是否需要基于书籍/会话身份的额外锁，不直接上全局锁。源哈希 guard 保留，但它检查的是 BookContainer 可见内容，不宣称覆盖宿主所有并发状态。

注意 QProgressDialog 模态时 `setValue()` 本身可能 pump 事件；梳理 update/cancelled 中重复泵事件，不简单删取消检查。取消状态查询与事件处理可分开；每个安全边界在事件泵之后检查取消。保留最后一个文件取消零写回测试，取消不得依靠虚假进度推进。

进度推荐明确分阶段：读取文件、构造计划、准备修改、验证；阶段切换 `reset`/0 并更新标题或阶段说明，避免把每阶段百分比当总体。显示完成数应在操作后增加，不能在最后一个操作开始时显示已经完成。零文件正常结束。若改总体 2N，需覆盖已经 scan、空输入以及后续阶段，不假设每个阶段都同权耗时。

验收：捕获阶段/value 序列；同阶段单调递增；阶段重置可辨识；在真实 Qt 检查模态、关闭/取消、重复应用和焦点；真实宿主行为单独记录，fake Qt 通过不算宿主验证。

## E：单次导入哈希优化（独立安全/性能提交）

冷导入调用路径支持“select 一次 + 两个源码模块 exec + native create/exec”这五次全树校验；热模块复用不必重走所有 loader，所以不能把 5 次描述成每次固定值。用户提供的 0.30/0.28 秒作为实测报告，本轮未复测。

不接受常驻 finder 永久记住 `(root, sha)`：路径和期望 hash 不变时，磁盘仍可能变化。现有额外检查确实覆盖了较晚的变化时点，不能无条件称为没有安全效果；同时现有先 hash 后 read 也不是原子快照。

建议两步：先引入严格限制在一次 `import_opencc()` 调用栈内的验证上下文，`finally` 失效；select 仍是每次导入入口闸。为源码执行保留从本次已验证快照读取并编译相同字节的能力，native 初始化前仍校验实际将加载的文件（不能只按 mtime/size）。延迟导入必须重新验证，二次 selector 调用必须重新验证。若暂时无法建立等价边界，保留校验次数并先完成其他批次，禁止以性能为由跳过安全测试。

测试：计数冷/热导入的全树哈希；在 select 后、源码执行前、native create 前注入受控篡改；首轮成功后篡改延迟模块，再次导入拒绝；失败上下文不得复用。性能测量至少三次中位数，记录 cold/hot、载荷大小、哈希次数、时间；目标是减少整树 IO，不预设倍数。

## F：死代码与条件收敛

全仓检索后移除 `_selected_xhtml_ids` 包装、无人调用的 `verify_staging` 及相关 import/无用参数。controller scope 闸后 targets 已非空，可直接创建 reporter；保留 finally close。`run_scope` 仍被传参，只是目标集合优先时不参与选择，可直接采用本次 selection 的 scope 或移除重复局部变量；不要顺手删除 workflow 的兼容 scope API，现有测试/非 UI 调用仍使用它。运行范围隔离与空选择测试。

## G：版本与发布

当前 HEAD 相对 v0.0.2-beta 多 5 个提交，版本仍 0.0.2-beta，且 CHANGELOG 有 Unreleased；这属于尚未发布开发状态，不必每次提交都 bump。

真正准备下一版时同步 `app/version.py`、`plugin.xml`、`pyproject.toml`、lock 元数据（若包含本项目）、CHANGELOG，并用 tag↔metadata 校验。候选小版本可为 `0.0.3-beta`，须由用户实际发布安排确定；本方案不授权打 tag/push/release。

v1.4 规范中的 `0.0.1-beta` 是版本化示例，标明“示例，实际见 plugin.xml”，或使用明确占位版本；不要将历史修订记录的当时版本机械替换成最新版本。

## payload 瘦身专项边界

headers、cmake、pkgconfig、静态库、CLI 可作为裁剪候选，但先建立运行/构建用途白名单。Jieba 构建依赖 headers/static core，差分测试需要独立 CLI，不能在构建和差分之前删除。保持完整 wheel 用于构建/审计，再导出经过测试的 runtime 子集；记录原 wheel hash、裁剪 recipe 版本、保留/排除清单及派生树 hash，原始 RECORD 不宣称匹配裁剪后的完整树。

检查每个平台动态依赖、安装路径以及 OpenCC 配置资源读取；分发测试用裁剪后的实际 ZIP。不能在 build_plugin 最后一刻删文件而不重建 manifest。未实测四平台前不承诺“25 MB × 4”的压缩下载节省。该专项另起方案，不与本轮 notice 修复绑定。

## Luna 执行顺序与交付

每批先检查工作区，保留正确改动；按 A → B → C → D → E → F → G 顺序，每批独立 commit。E 若无法证明边界等价，交付阻塞说明和测试证据，其他批次仍可完成。G 只在用户要求准备发布时执行；瘦身专项不自动实施。

建议提交主题：

1. `fix: clarify overlapping result counts`
2. `build: validate runtime resources and invalidate payload caches`
3. `security: close native fallback and preserve dependency notices`
4. `ui: clarify progress phases and constrain reentry`
5. `perf: reduce redundant import verification safely`
6. `refactor: remove unused preview and verification helpers`

按变化选针对测试；每批通过后，在最终状态执行一次：

```sh
make check
mise exec -- uv lock --check
mise exec -- uv run python tools/build_plugin.py --output /tmp/OpenCCForSigil_review_candidate.zip
mise exec -- uv run python tools/validate_artifact.py /tmp/OpenCCForSigil_review_candidate.zip
mise exec -- uv run python tools/benchmark_staging.py
git diff --check
```

CI 完整矩阵必须使用 `--require-runtimes`，不能用本机单平台结果代替。不得为了通过测试自动重算篡改 fixture 的期望值或绕过 source-only 校验。

最终提供：逐项采纳/延期状态、commit 列表、测试结果、缺失资源/非法回退负例、导入哈希计数、性能记录、真实 Qt/宿主验证范围。Astra 独立 review 安全相关批次；实现、测试执行和提交由 Luna 完成。

## 实施记录（2026-09-08）

已完成的独立提交如下：

| 批次 | Commit | 实际结果 |
| --- | --- | --- |
| A | `4adaa09` | 三语文案明确 `files_not_written` 包含 `files_without_changes`；N/W/U/NW 覆盖测试通过 |
| B | `79cbb75` | 归档资源、CI ref/lock/manifest 闸和流式 ZIP hash 校验完成；21 项 validator/provenance/package 定向测试通过 |
| C | `46da6c3` | native runfiles 回退 fail-closed、公开 spec 工厂和六项随包 notice 完成；B/C 合计 34 项定向测试通过 |
| D | `228a7fa` | 阶段重置/同阶段单调进度、父对象与模态范围、窗口幂等关闭和运行态重入闸完成；23 项 UI/workflow 定向测试通过 |
| E | `4aba543` | 冷导入 5 次全树 hash，热导入入口 1 次；延迟篡改拒绝，导入故障后下一次完整冷导入（总计 11 次）；13 项 source-import 测试通过。未采用无原子快照的整树缓存 |
| F | `6fb2d85` | 移除无人调用的 preview/verifier 辅助和恒定条件，保留 workflow scope 兼容入口；27 项范围/workflow/插件定向测试通过 |

各批次 Ruff 与 `git diff --check` 均通过；主会话另已报告 `make check` 66 项通过（95.19 秒）、vendor/OpenCC/Jieba 配置校验、`uv lock --check`、构建及归档 validator 通过。以上自动化与 fake Qt 结果来自本机 macOS arm64 / CPython 3.14.7；真实 Qt、真实 Sigil 宿主重入行为以及 Windows、Linux、macOS Intel 四平台仍未验证。

本轮剩余 G 版本与发布治理、payload 瘦身专项。E 的安全优化可在建立一次调用内的原子源码快照并继续校验 native 实际文件后另行设计；当前保持延迟导入与 native loader 的逐次校验。

## 核对来源

- 当前仓库 HEAD `9f353e1`：controller、workflow、runtime_selector、validate_artifact、CI、现有测试和 pinned wheel 源码。
- 本地 Sigil API guide：`../OpenCCForSigil-References/plugin-api-guide/src/OEBPS/Text/sigil_python_plugins.xhtml`，独立进程说明。
- [Qt WindowModality](https://doc.qt.io/qt-6/qt.html#WindowModality-enum)：窗口与应用模态范围。
- [Qt QProgressDialog setValue](https://doc.qt.io/qt-6/qprogressdialog.html#value-prop)：模态进度更新的事件处理行为。
- [Python importlib](https://docs.python.org/3/library/importlib.html#importlib.util.spec_from_file_location)：公开 spec 工厂。
- [Apache-2.0 正文](https://www.apache.org/licenses/LICENSE-2.0)：分发与归属条件；各第三方具体许可以 pinned 来源为准。
