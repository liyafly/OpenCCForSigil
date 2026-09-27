# v0.2.8 预览优化与功能实现结果

日期：2026-09-27。实现基线：`main`，计划文档见 [`01-optimization-feature-luna-plan.md`](01-optimization-feature-luna-plan.md)。本记录区分已合入实现、自动化/Qt 证据和真实 Sigil 宿主验收；这些状态不能互相替代。

## 提交批次

| ID | 提交 | 交付 |
| --- | --- | --- |
| R-01 | [`29e1087`](https://github.com/liyafly/OpenCCForSigil/commit/29e1087409e79f76d4a05f06fceee852d5025f08) | 区分规则替换组与跨资源语言标签组；文件操作覆盖本文件规则组，语言组按钮不再误处理规则组。 |
| R-02 | [`587139b`](https://github.com/liyafly/OpenCCForSigil/commit/587139b55737e7ecad4c4a6bb5f6d74db49d27ca) | MathML 配置开启时只允许 `mtext`，标识符及范围外元素仍受保护。 |
| R-02 验收补充 | [`17a11e8`](https://github.com/liyafly/OpenCCForSigil/commit/17a11e83412ef7335a6b345874ea9177bd0c1d45) | 增加 MathML 端到端保护测试，覆盖 plan、accept、stage、verify 和 commit。 |
| O-01 | [`e46a1e8`](https://github.com/liyafly/OpenCCForSigil/commit/e46a1e86b85f20916b862cfc323132a384baa1ba) | 预览构建 group/file 索引，批量决定不再为每个组反复扫描全表。 |
| R-01 补充 | [`908f616`](https://github.com/liyafly/OpenCCForSigil/commit/908f616f44e136b79e653e44b68e8b56ec710e5d) | 筛选命中组有隐藏成员时，确认完整联动范围；取消时不改决定。 |
| F-01 | [`948a9ab`](https://github.com/liyafly/OpenCCForSigil/commit/948a9ab331e6385b73020a9bea80405f29b60bcf) | 增加预览状态、来源和原文文字筛选，保留全局未处理计数。 |
| F-02 | [`4452777`](https://github.com/liyafly/OpenCCForSigil/commit/44527774d20d0826199ae712d15c88cb648cf8a0) | 增加有界的预览决定 Undo/Redo 和恢复未处理；不撤销已 Apply 的 EPUB 修改。 |
| F-03 | [`4750098`](https://github.com/liyafly/OpenCCForSigil/commit/47500987193c178ad5e3b59cb0096cf2e666c695) | 增加可筛选诊断列表、原文行列与片段定位；零变更结果也可查看计划诊断。 |
| F-02 性能补充 | [`1bd4547`](https://github.com/liyafly/OpenCCForSigil/commit/1bd4547e1a538f8394cfb05fe5b01c5f4771c8ae) | 将全接受/全跳过历史压缩为只含决定 ID/状态快照的一次操作，避免 300,000 条变更逐条创建 UI 历史对象。该提交的 [GitHub workflow](https://github.com/liyafly/OpenCCForSigil/actions/runs/36301827862) 全绿，包含全部六个平台包 smoke。 |

以上实现提交已逐项推送至 `origin/main`。O-02 文档同步提交随后单独推送；最后的 release-preparation 提交必须作为 `v0.2.8` tag 目标，不得在该提交之后向 `main` 追加提交。

## 条目结果与证据

| 条目 | 实现和自动化验收 | 证据及限制 |
| --- | --- | --- |
| R-01 分组语义 | 覆盖纯规则组、混合规则/语言组、同规则多次出现、文件范围和筛选隐藏组成员；正式回归在 `test_preview_window.py`、`test_rules_transform_workflow.py`。 | [`after-groups.json`](evidence/after-groups.json) 的断言确认规则组不显示语言组按钮、隐藏按钮点击不改变决定、文件操作处理全部本文件规则组、语言按钮只接受语言组。 |
| R-02 MathML 保护 | `test_profiles_m3.py` 覆盖 `Profile.to_dict() → from_dict()`、`mi`、`mo`、`mn`、`ms`、`annotation`、`annotation-xml`、属性、未知命名空间和嵌套标识符。新增 [`test_mathml_profile_stages_only_mtext_and_preserves_protected_source_slices`](../../../tests/integration/test_rules_transform_workflow.py) 覆盖 plan、accept、stage、verify 和 commit；只有两个 `mtext` 直接文本 span 改变，其他源码切片逐字不变。相关 integration/profile/UI 测试 **32 passed**。 | [`after-groups.json`](evidence/after-groups.json) 记录关闭时目标为空、开启时目标仅为 `mtext`。MathML annotation 与更广泛语义仍未开放。 |
| O-01 组操作复杂度 | `test_preview_group_scaling.py` 对索引和组操作做计数回归；批量结果与决定映射一致。探针每档运行三次，不使用时间阈值。 | [`after-groups.json`](evidence/after-groups.json)：1,000/2,000、2,000/4,000、4,000/8,000 组/变更分别访问 8,000、16,000、32,000 次；均低于计划的 `10 × changes` 上限。中位耗时约 0.0032、0.0072、0.0141 秒，仅为本机合成决定路径参考，不外推整书耗时。 |
| F-01 预览搜索 | `test_preview_filters.py` 与窗口测试覆盖状态/来源/文件/类别/风险 AND 筛选、实体解码文字匹配、空结果、清除、焦点/选择及接受后可见集合刷新。 | [`after-preview-search.json`](evidence/after-preview-search.json)：10,000 项约 0.00285 秒、300,000 项约 0.08301 秒；每次仅 1 项匹配、格式化行数 0、OpenCC 调用 0。仅为当前 macOS arm64 合成基准。 |
| F-02 预览 Undo/Redo | `test_preview_decision_history.py` 覆盖单项、组、文件、筛选、全量、恢复未处理、redo 清空、历史预算、不可变会话快照、未知 ID 及历史失效；控制器/集成测试确认不写 Book、不调用转换后端。 | 全量操作以紧凑决定快照作为一个有界历史操作。本机 300,000 行回归及 1bd4547 的 300,000 行远端回归均通过；此前失败的 1 秒性能断言已由该提交完整原生矩阵（payload、组包和六平台 smoke）重新验证。撤销只影响本次仍打开的预览决定。 |
| F-03 诊断定位 | `test_preview_diagnostics.py`、窗口/结果计数和控制器集成测试覆盖过滤、源码行列、CRLF、边界关联、零变更结果、只读诊断路径及无伪造变更。 | [`layout.json`](evidence/after-diagnostics-qt/layout.json) 和 Sigil bundled Python/PySide6 的 macOS Cocoa 检查截图：[English](evidence/after-diagnostics-qt/preview-diagnostics-en.png)、[简体中文](evidence/after-diagnostics-qt/preview-diagnostics-zh-Hans.png)、[繁體中文](evidence/after-diagnostics-qt/preview-diagnostics-zh-Hant.png)。初始窗口 900×620；三语言尺寸检查通过。该证据不是在 Sigil 中加载插件的宿主验收。 |

## 本地总检查

在 v0.2.8 release-preparation 候选工作树（包含 [`1bd4547`](https://github.com/liyafly/OpenCCForSigil/commit/1bd4547e1a538f8394cfb05fe5b01c5f4771c8ae) 及版本 0.2.8）运行 `mise exec -- uv run make check`：

- Ruff 通过；pytest **647 passed, 1 skipped**（唯一 skip 是 fake Qt 不计算实际控件布局尺寸）。
- vendored OpenCC 检查通过；当前本机只验证 `macos/arm64` payload。
- 官方 CLI/Python Binding 差分 28/28 一致；Jieba 差分 10/10 一致。
- 插件元数据检查通过，版本为 0.2.8。

本地 `make package` 与 `make artifact-check` 通过；ZIP 为 5,717,299 字节，SHA-256 `98e63c7b6bdf5381118455957fe3905a8c38c555edd17a86b4f2d840a3b03364`，仅含当前 checkout 的 `macos/arm64/cp314` payload。它是本地单平台包，不能替代远端 Fat Plugin 或六个目标包。

该本地检查不能代替最终 0.2.8 release-preparation `main` SHA 上的远端 E-01 原生矩阵。只有该 SHA 的 E-01、七个安装 ZIP 与校验清单验证、六个 smoke job、tag attestations 和已下载 Release 资产校验都通过后，发布才算完成，详见 [`release.md`](../../release.md)。

compact-history 修复提交 [`1bd4547`](https://github.com/liyafly/OpenCCForSigil/commit/1bd4547e1a538f8394cfb05fe5b01c5f4771c8ae) 的完整 push workflow 于 [run 36301827862](https://github.com/liyafly/OpenCCForSigil/actions/runs/36301827862) 通过：六个 native payload、跨平台 Jieba 对比、Fat 与六个 platform ZIP 组包/校验、六个 package smoke 全部成功。该记录证明性能修复通过原生矩阵；发版时仍以 release-preparation SHA 对应的 E-01、tag workflow 和下载资产验证为准。

## 验收边界

- 真实 Sigil 宿主中安装本次生成包，打开副本 EPUB，执行预览/应用/保存/关闭/重开并核对源文件：**Not verified**。
- Windows、Linux、macOS Intel 的本地 Qt 交互：**Not verified**；必须使用最终候选的 CI 平台作证，CI 也不等于用户 Sigil 版本矩阵的手动宿主验收。
- 预览检索词、撤销历史和诊断源码片段只在本次内存预览中使用，不新增正文日志/历史/报告写入；诊断定位不会重新分析、调用 OpenCC 或写 BookContainer。

只有最终候选完整 E-01 和资产检查通过后，才创建 `v0.2.8` 并推送 tag。GitHub Release 资产、SHA-256 与 attestations 必须从远端下载并逐项验证后，才可报告发布完成。
