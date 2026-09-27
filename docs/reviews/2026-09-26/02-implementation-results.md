# UI 与规则审查实现结果

日期：2026-09-27。规格：[01-ui-rules-luna-plan.md](01-ui-rules-luna-plan.md)。

## 条目验收

基线脚本在 `e5329e7` 上有 16 个预期失败断言，覆盖 R-01 至 R-10、R-12；
当前全部转绿。实现先按规则/转换行为拆分提交，再单独提交 UI 与发布变更。

| 条目 | 实现提交 | 正式测试 | 复现结果 | Qt / Sigil | 状态 |
| --- | --- | --- | --- | --- | --- |
| R-01 | `b188591` | `tests/integration/test_ruleset_persistence.py` | 通过 | 不适用 | 完成 |
| R-02 | `ad0f819` | `tests/unit/test_rules_window.py` | 通过 | 假 Qt 状态测试 | 完成 |
| R-03 | `539d19c` | `tests/unit/test_rule_import_export_roundtrip.py` | 通过 | 不适用 | 完成 |
| R-04 | `e4469e2`, `c7698fa` | `tests/unit/test_rules_m3.py`, `tests/unit/test_rules_window.py` | 通过 | 三语言文案纳入 i18n 测试 | 完成 |
| R-05 | `9899749` | `tests/integration/test_rules_transform_workflow.py` | 通过 | 不适用 | 完成 |
| R-06 | `0f4449e` | `tests/unit/test_rules_window.py` | 通过 | 假 Qt 状态测试 | 完成 |
| R-07 | `0f4449e` | `tests/unit/test_rules_window.py`, `tests/unit/test_regex_rules.py` | 通过 | 假 Qt 状态测试 | 完成 |
| R-08 | `f703322`, `f7c60f7` | `tests/unit/test_rules_window.py`, `docs/reviews/2026-09-26/scripts/check_rules_layout.py` | 通过 | 真实 Qt Enter/Esc 路径通过；Sigil 未验证 | 完成 |
| R-09 | `f703322` | `tests/unit/test_rules_window.py` | 通过 | 三语言真实 Qt 截图 | 完成 |
| R-10 | `7df5c4a` | `tests/unit/test_regex_rules.py` | 通过 | 不适用 | 完成 |
| R-11 | `f703322`, `f7c60f7` | `docs/reviews/2026-09-26/scripts/check_rules_layout.py` | 通过 | 三语言真实 Qt 尺寸/折叠检查通过；Sigil 未验证 | 完成 |
| R-12 | `8a31239` | `tests/unit/test_rule_import_export_roundtrip.py` | 通过 | 不适用 | 完成 |
| U-01 | `f703322`, `f7c60f7` | `tests/unit/test_rules_window.py`, `docs/reviews/2026-09-26/scripts/check_rules_layout.py` | 通过 | 长文本详情可读；Sigil 未验证 | 完成 |

R-04 的测试夹具在全套检查中暴露出漏填方向字段的问题；补齐有效方向后，
`tests/unit/test_rules_m3.py` 为 22 项通过。这个夹具修正单独记录在 `c7698fa`。

## 自动验证

```text
make check
611 passed, 1 skipped
Ruff: passed
vendor manifest: passed; local runtime macOS arm64
official OpenCC CLI/Binding differential: 28 cases, 100% equality
official Jieba CLI/Binding differential: 10 cases, 100% equality
plugin metadata: 0.2.6
```

唯一跳过项是 `tests/unit/test_rules_window.py:335` 的假 Qt 尺寸断言；该假 Qt
不计算布局尺寸。尺寸和显隐行为由下方真实 Qt 检查覆盖。

审查复现命令：

```sh
PYTHONPATH=plugin/OpenCCForSigil mise exec -- uv run python -m pytest \
  docs/reviews/2026-09-26/scripts/test_review_regressions.py -q
```

结果：`16 passed`。真实 Qt 检查命令：

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=plugin/OpenCCForSigil mise exec -- \
  uv run --with PySide6==6.11.2 python \
  docs/reviews/2026-09-26/scripts/check_rules_layout.py \
  --output docs/reviews/2026-09-26/evidence/after --verify
```

[layout.json](evidence/after/layout.json) 记录了完整数据；三种语言最小宽度均为
188 px、初始窗口为 800×540 px、规则表高 192 px。最小高度为英文 353 px、
简体/繁体中文 355 px。沙箱收起时输入区不可见，展开后可见。真实 Qt 键盘检查
验证了 Enter 应用新增草稿、Esc 触发放弃草稿并关闭，以及长正则和目标全文可在
详情区读取。Esc 的确认选择在自动检查中固定为“放弃”，真实 QMessageBox 文案和
宿主键盘顺序仍未作手动验收。

三语言截图：[英文](evidence/after/rules-en.png)、
[简体中文](evidence/after/rules-zh-Hans.png)、
[繁体中文](evidence/after/rules-zh-Hant.png)。

## 0.2.6 发布验收

发布候选提交为 `8b02a4d9c43d4e150b555f8e23e91fe59bdf5bf3`，tag `v0.2.6`
指向该提交。

- [E-01 main workflow](https://github.com/liyafly/OpenCCForSigil/actions/runs/36281951105)：
  六种 runtime payload、跨平台 Jieba 比较、打包和六个平台 smoke 全通过。
- [Tagged release workflow](https://github.com/liyafly/OpenCCForSigil/actions/runs/36282624821)：
  所有 job 通过，包含 `Attest tagged release assets` 和 `Publish tagged GitHub release`。
- [GitHub Release v0.2.6](https://github.com/liyafly/OpenCCForSigil/releases/tag/v0.2.6)：
  已发布七个 ZIP 和 `SHA256SUMS.txt`。下载后
  `tools/release_assets.py --version 0.2.6` 校验通过，七个 ZIP 的 SHA-256 全部
  匹配，八个文件的 `gh attestation verify` 均成功。Fat Plugin 为 29,509,760
  字节，六个平台包均小于 7,000,000 字节。

本机 `make package` 与 `make artifact-check` 也通过。本机 ZIP 只有检出树中已有
的 macOS arm64 payload；多平台正式资产由上述 GitHub Actions 原生构建生成。

## 尚未验证

未在真实 Sigil 中安装发布 ZIP 并执行 EPUB 转换、保存、关闭后重新打开。真实
Sigil 宿主验收仍为 **Not verified**；offscreen Qt、原生 CI smoke 与 ZIP 检查都
不能替代这项宿主验收。
