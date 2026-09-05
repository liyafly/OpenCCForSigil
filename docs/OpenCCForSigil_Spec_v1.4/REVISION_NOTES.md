# OpenCCForSigil Engineering Spec — v1.3 → v1.4 修订说明

日期：2026-09-05  
主题：**在官方 Python Binding production backend 上增加官方 native Jieba payload 与可检测高级选项**

## 1. Changed

v1.2 的 Production Backend：

```text
Python → ctypes stable C ABI → self-packaged libopencc + data
```

v1.4 的 Production Backend：

```text
Sigil Plugin
  → OpenCCForSigil Core
  → OpenCCBackend
  → exact vendored official `opencc` Python Binding payload
  → official OpenCC C++ Core
  → same-release configs/dictionaries
```

Production code 使用：

```python
import opencc

converter = opencc.OpenCC(config)
target = converter.convert(source)
```

这里的 `opencc` 是 BYVoid/OpenCC 官方 Python Binding；PyPI 项目显示名为 `OpenCC`，规范化 distribution 名称和 wheel 文件名为 `opencc`。它通过官方 CPython native extension 调用 OpenCC C++ Core，不是 Python 重写版。

## 2. Why

- 继续使用 OpenCC 官方 C++ Core 和官方 config/dictionary 语义；
- 让 OpenCC upstream 维护 CPython extension、Python/native ownership 和 wheel 构建；
- 减少 OpenCCForSigil 自己维护 FFI、descriptor/buffer lifetime 和跨平台 shared-library loader 的范围；
- 减少手工 DLL/dylib/so packaging 与 dynamic dependency 维护；
- 用 official wheel 的 exact CPython ABI、OS、architecture tags 明确表达兼容性；
- Build/Release 阶段只需 vendor、hash、验证官方 wheel payload，Runtime 不需要联网或安装依赖；
- 将 V1 正式运行时统一为 CPython 3.14.x / `cp314`；当前 Sigil bundled Python 3.14.2 是生产基准，其他 CPython 3.14.x 仅在 exact OS/architecture/ABI 匹配时作为 best-effort；3.14.7 不作为最低运行版本。

这不是退回 Python 实现：Python 侧只是官方 binding 的调用面，最终转换仍由 OpenCC 官方 C++ Core 完成。

## 3. Facts verified for the baseline

以同级参考仓库 `../OpenCCForSigil-References/OpenCC` 的 `ver.1.4.2` tag，以及 PyPI `OpenCC` 1.4.2 metadata 为基线，已核对：

- public import name 是 `opencc`；
- public constructor 是 `opencc.OpenCC(config, include_tofu_risk_dictionaries=True, resource_zip=None)`；
- public conversion method 是 `convert(text)`；
- `opencc.CONFIGS` 和 `opencc.__version__` 可用于 self-test；
- upstream Python extension implementation is `opencc.clib.opencc_clib`，但这是 private implementation detail，OpenCCForSigil 不直接 import；
- 1.4.2 PyPI wheels 观测到 CPython 3.10–3.14 的 macOS x86_64/arm64、manylinux2014 x86_64/aarch64、Windows x86_64 variants；最终正式矩阵仍必须由实际 Sigil Bundled Python CI 验证；
- pinned upstream config directory contains the 16 V1 configs listed by §4.1.2。
- 本仓库开发/CI 工具链已由 mise 验证并固定为 Python 3.14.7、uv 0.12.9、Ruff 0.16.6；3.14.7 只用于开发/CI。3.14.2 与 3.14.7 选择同一个 `cp314` payload，patch 版本仅写入 provenance。

这些是 `BUILD-TIME VERIFIED` 事实；升级 OpenCC 或 Sigil 后必须重新核对。

## 4. Removed production assumptions

以下内容不再是 Production Backend：

- `ctypes.CDLL` / `ctypes.util.find_library`；
- 手工绑定 `opencc_open`、`opencc_close`、`opencc_convert_utf8*`、`opencc_error`；
- 手工管理 native descriptor、返回 buffer 和释放函数；
- 自维护 `libopencc.dylib`、`libopencc.so`、`opencc.dll` platform matrix；
- 以 `vendor/MANIFEST.json` 直接加载 shared library；
- `opencc-py`、系统 OpenCC、PATH CLI、user site-packages fallback；
- Runtime `pip install`、联网下载或系统 package manager；
- 以 Production Backend 自己生成 golden expected。

C/C++ API、C ABI、wheel 内 extension 文件仍可在 upstream 技术背景、许可证、供应链审计和历史对比中出现，但不得被实现为 OpenCCForSigil 的 Production runtime path。

## 5. Not changed

以下设计从 v1.2 原样保留：

- OpenCC authoritative semantics 与 official dictionary read-only；
- XHTML/XML token-preserving、absolute source-span mapping、only planned spans may change、未计划 bytes byte-identical；
- `HTMLParser` 不被假定直接提供 absolute offset；
- source SHA-256 concurrency guard、RuleSnapshot/BackendProvenance freeze；
- SCAN → ANALYZE → PLAN → PREVIEW → APPLY TO STAGE → VERIFY → WRITE/COMMIT → REPORT；
- preview before write、staging buffer、structural verifier、atomic commit 和 Sigil non-zero failure transaction boundary；
- exact/protected/regex overlay rules、direction、precedence、scope、profile、import/export、conflict detection；
- regional conversion explicitness；`s2t` 不自动等同 `zh-TW`，通用繁体建议 `zh-Hant`；
- `comparative_config_diff`，comparison 不伪造 dictionary hit trace；
- 不提供任意 segmentation dropdown；仅在 manifest-approved 官方 native
  `opencc-jieba` payload 存在并通过完整校验时提供高级开关；
- mixed simplified/traditional diagnostics、force pivot 默认关闭、review annotation mode 与 remove annotations；
- idempotency、logging/history、persistent JSONL、privacy-safe logging、Conversion Report、Self-Test；
- CI、release governance、official CLI oracle、golden、ambiguity/regional corpus、EPUB structural fixtures、fuzz/property tests；
- EPUB structural safety > conversion coverage；UI/core/document/backend 分离；
- AI implementation constraints 与“不得用快捷实现”的完整约束。

## 6. Version and compatibility policy

本次工作区当前稳定规范升级为 **v1.4**。v1.2 与 v1.3 目录保留为历史基线；v1.4 是后续实现模型的唯一 backend architecture authority。

V1 Python compatibility is fixed to CPython 3.14.x with wheel ABI `cp314`.
The current Sigil bundled Python 3.14.2 is the production baseline; mise's
Python 3.14.7 is the development/CI baseline. Patch versions are provenance
only and never participate in payload compatibility selection. `3.14.7` must
not be presented as the minimum runtime version.

插件自身的发布版本仍遵循 §45 的 SemVer（当前 skeleton 为 `0.1.0`），与工程规范版本 `v1.4` 不混用。

## 7. v1.4 Native Jieba enablement

### Changed

增加同一 pinned OpenCC release 的官方 `plugins/jieba` C++ native plugin
payload，并在 `OpenCCBackend` 中通过 manifest-approved `opencc.OpenCC`
config（例如 `s2t_jieba`）使用它。新增：

- `native_plugins.opencc-jieba` manifest record；
- plugin library/config/dictionary/resource hashes 与 upstream tag/commit；
- `tools/build_opencc_jieba.py` Build/Release 构建工具；
- `tools/differential_jieba_test.py` 独立 CLI/Python Binding 差分测试；
- Windows/macOS/Linux runner 各自构建 DLL/dylib/so 后再组装 Fat Plugin；
- payload 已验证时才出现的高级 Jieba checkbox。

### Why

该 plugin 是官方 OpenCC native plugin，不是参考项目中的 Python 逻辑，也不
改变唯一 production backend。它可以改善需要词级分词的官方 config 结果，
同时保留 upstream 语义、官方 C++ Core、无 runtime pip/network 和完整
provenance。由于 upstream 将 external plugin mechanism 标为 optional/
experimental，版本升级必须重新构建、校验 ABI/hash 并完成 100% differential
与人工 golden review。

### Not Changed

以下原则没有变化：

- OpenCC authoritative semantics、official dictionary/resource read-only、用户
  rule overlay；
- XHTML source-span safety、only planned spans may change、preview-first、
  staging、structural verifier、atomic commit、source SHA256 concurrency guard；
- RuleSnapshot/provenance freeze、rule precedence、regional explicitness、
  `comparative_config_diff`、logging/history、golden/CI/release governance；
- 不使用 `opencc-py`、Python Jieba 重写、ctypes production path、system
  OpenCC/plugin、runtime pip、runtime network 或 custom converter；
- V1 Python compatibility 仍为 CPython 3.14.x / `cp314`；Sigil bundled 3.14.2
  为生产基准，3.14.7 仅开发/CI，patch 只记录 provenance；
- EPUB structural safety > conversion coverage，且不恢复任意 segmentation
  dropdown。
