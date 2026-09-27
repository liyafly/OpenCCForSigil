# 性能与交互优化（2026-09-08）

## 2026-09-22：长文本差异计算

`core/diff.py` 对短文本保留原有细粒度对齐；长文本先剥离相同前后缀，
使用唯一锚点和有预算的局部对齐。歧义或超预算区域作为一个准确替换块呈现。
这会降低该区域逐字接受/跳过的粒度，不改变 OpenCC 结果，也不分割传入
官方转换器的原文。全部接受后的重建必须与官方完整输出完全一致。

回归测试覆盖重复中文、插入/删除、非 BMP 字符、组合字符、随机重建和
超长相同前后缀。后台分析与真实 Qt 大书验收仍需单独验证；快速差异计算
不代表所有 UI 等待均已消除。

基线：`e7d9717`。主会话定位、测量与验收，Luna 实现，Astra 独立审查。

## 本轮范围

1. 暂存补丁按原文坐标排序，一次拼接未修改片段与替换文本，避免每个变更都复制整篇内容。保留源码匹配、越界、重叠校验及原有插入顺序。
2. 单条接受/跳过只更新当前列表项和统计，保留当前选择，避免重写所有预览行。统计仍需遍历决定，不宣称整个操作为常数时间。
3. 应用按钮只检查是否仍有未决定项，最终计划由 workflow 构造一次，减少重复分配。

复现补丁算法对比：`mise exec -- uv run python tools/benchmark_staging.py`。
使用三个固定合成规模，各重复三次取中位数，并断言新旧结果完全一致。
这是补丁拼接微基准，不是 OpenCC 转换、整本书或真实 Qt 耗时。

本机 macOS arm64 / CPython 3.14.7 三次中位数（秒）：

| 原文字符数 | 变更数 | 原算法 | 新算法 |
| --- | --- | --- | --- |
| 10,000 | 100 | 0.000141 | 0.0000275 |
| 100,000 | 1,000 | 0.00964 | 0.000254 |
| 1,000,000 | 3,004 | 0.439 | 0.00101 |

三个样本新旧输出一致。数据受机器负载影响，不能外推为整书转换倍数。

## 验证结果（2026-09-08）

最终 HEAD `cc357ba` 在本机完成 `make check`：118 项测试通过（123.62 秒），并通过 Ruff、vendor 校验、OpenCC 标准配置 16/16、Jieba 配置 10/10、`uv lock --check` 及 `build_plugin` 内置校验；复核归档为 `/tmp/OpenCCForSigil_review_candidate.zip`，无矩阵要求的归档 validator 通过。该本机归档用 `--require-runtimes` 会按预期报告缺少 Linux x86_64、macOS x86_64 和 Windows x86_64 payload；四平台归档闸需 CI 多 runner 产物。`tools/benchmark_staging.py` 本次三个固定样本仍断言新旧输出一致。Astra 独立审查未发现阻塞问题。

验证环境仅为 macOS arm64。真实 Qt 交互以及 Windows、Linux、macOS Intel 的四平台兼容性仍未验证；合成基准和自动化测试不能替代这些宿主验收。

## 原后续专项的当前状态（2026-09-27）

本节只更新旧待办的状态，不改写上面的 2026-09-08 基准数据或历史结论。
本轮实现与验证过程见 [`reviews/2026-09-27/02-implementation-results.md`](reviews/2026-09-27/02-implementation-results.md)。

| 原项目 | 当前状态 | 实际边界 |
| --- | --- | --- |
| 超大单文件后台分析 | 已实现后台计划工作线程。 | 后端在 worker 内创建、使用和关闭；BookContainer 与 Qt 留在主线程。取消在目标边界协作生效，运行中的 native OpenCC 调用不能被强制中断。 |
| 分组预览与返回设置 | 已实现分组决定、返回设置后重分析。 | 规则单次出现组和跨资源语言标签组保持原子；返回设置会废弃旧计划与决定。 |
| 写回阶段持续状态 | 已实现阶段进度与不可取消阶段提示。 | staging、verify、source recheck 和 commit 在安全写回边界执行；不是可中断的原生写入。 |
| 大列表模型/视图 | 已实现基于 Qt table model 的惰性格式化。 | 正式回归覆盖 300,000 条预览变更；本地模型测试不能替代真实 Sigil 大书性能验收。 |

2026-09-27 又增加了预览状态筛选、来源和原文文字检索、预览决定 Undo/Redo、可折叠诊断列表及原文行列定位。检索、撤销、诊断查看只操作冻结计划和内存状态，不重新调用 OpenCC，也不写 EPUB。Undo/Redo 只恢复预览决定；已应用到 EPUB 的内容仍需通过 Sigil Checkpoint 或备份恢复。

真实宿主性能验收应使用同一 EPUB 副本、相同 OpenCC 配置与平台，记录设置至预览、接受单条、全部接受、应用至完成的耗时和峰值内存。自动测试或合成基准不能替代该验收。
# Worker planning

The controller reads selected sources on the main thread, then plans them with
a backend constructed, used, and closed in one dedicated worker. Queued
progress keeps Qt event processing on the main thread. Cancel discards the
entire plan at the next target boundary; a native OpenCC call already in
progress must return before the worker exits. Staging, verification, and every
Sigil read/write remain on the calling thread. This is cooperative cancellation,
not a hard interruption of the native library.
