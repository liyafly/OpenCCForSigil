# 2026-09-23 审查记录

本目录集中存放 2026-09-23 的审查文档和复现脚本，供实现模型按文档修改、按脚本核对。

## 文档

| 文件 | 内容 | 基线 |
| --- | --- | --- |
| [`01-ui-logic-spec.md`](01-ui-logic-spec.md) | 第一轮：UI 调整与逻辑优化的修改规格（L-xx、U-xx、C-01） | `b2f674b`（v0.1.0） |
| [`02-followup-review.md`](02-followup-review.md) | 第二轮：对照第一轮规格复审实现，列出剩余问题（R-01 至 R-26），其中 R-14、R-15 为阻断问题 | `263f657` |
| [`03-packaging-plan.md`](03-packaging-plan.md) | 打包拆分与瘦身：Fat 包 + 各平台独立包、Linux ARM64、Windows ARM64 路线；含已发布 Windows payload 的 Jieba 数据缺陷（P-00） | `263f657` |

建议阅读顺序：先读 `02` 的第 1 节和第 6 节（阻断问题与批次顺序），再读 `03`。`01` 是 `02` 的对照依据。

## 脚本

```text
scripts/
  _env.py        共用引导：定位仓库根目录、设置 import 路径、下载缓存目录
  ruff.toml      继承仓库 lint 规则，仅放宽"引导之后再 import"一项
  round1/        第一轮复现与测量（结果对应基线 b2f674b）
  round2/        第二轮复现（对应 02 中的 R-xx，见其附录）
  packaging/     打包体积与平台数据测量（对应 03，见其附录）
```

运行方式（工作目录不限）：

```sh
.venv/bin/python docs/reviews/2026-09-23/scripts/round2/scope_repro.py
.venv/bin/python docs/reviews/2026-09-23/scripts/packaging/release_zip_analysis.py v0.1.0
```

说明：

- 脚本使用仓库自带的 macOS arm64 payload。其他平台的 payload 只在 CI 构建中存在。
- `packaging/` 下的脚本会联网下载 PyPI wheel、GitHub Release 资产和上游源码，缓存在 `build/review-cache/`（git 忽略，可随时删除）。
- `round1/bench_preview.py` 只适用于基线 `b2f674b` 的列表式预览；在当前代码上会直接提示并退出。当前代码请看 `round2/preview_repro.py` 与 `round2/perf_model.py`。
- `round2/fakeqt.py` 是按真实 Qt 信号规则写的假 Qt，只用于复现，不能代替在 Sigil 中的实测。
- `round2/probe_check.py`、`round2/s1_jieba_loop.py` 和 `round2/preview_repro.py` 对应提交 `263f657`；自 `4706a92` 起不再适用于当前实现。
- 这些脚本用于复现与核对，不是回归测试。修复时应按文档各条目的"验证"部分把场景写进 `tests/`。
- 脚本通过仓库的 `ruff check .`（`make check` 的一部分）。
