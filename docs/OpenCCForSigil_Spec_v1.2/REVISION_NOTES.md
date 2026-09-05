# OpenCCForSigil Engineering Spec — v1.1 → v1.2 修订说明

日期：2026-09-03  
主题：**锁定 Native OpenCC 架构，并修复 v1.1 中会导致实现偏移的规范冲突。**

## A. Backend 架构变更

### 1. 唯一 Production Backend 改为 BYVoid/OpenCC native

v1.1：

```text
opencc-py + opencc-data
native OpenCC 主要作为 oracle / future backend
```

v1.2：

```text
Production Backend = pinned BYVoid/OpenCC native libopencc
Canonical Oracle   = same pinned BYVoid/OpenCC official CLI
Python binding     = stdlib ctypes + stable C ABI in opencc.h
```

运行时不再依赖：

- `opencc-py`；
- 独立 `opencc-data` Python package；
- PyPI native Python extension；
- 用户系统安装的 OpenCC。

### 2. 为什么采用 C ABI + ctypes

- OpenCC upstream 将 `opencc.h` C API 定义为稳定 ABI；
- 避免 CPython extension ABI 与 Sigil Python 版本绑定；
- 不需要每个 TextTarget 启动一次 CLI；
- 可以按 OS/Arch 打包并 hash 验证真实 `libopencc`；
- conversion semantics 完全由官方 native engine 执行。

v1.2 锁定的 C API：

```text
opencc_open
opencc_open_w (Windows build where available)
opencc_convert_utf8
opencc_convert_utf8_free
opencc_close
opencc_error
```

### 3. Native loader 改为 manifest + absolute path

删除 v1.1 的 `sys.path.insert()` / `opencc.__file__` 隔离规则。

新规则：

```text
platform triple
→ vendor/MANIFEST.json
→ verify library SHA-256
→ ctypes.CDLL(absolute_path)
→ verify C ABI symbols
```

禁止 `find_library()`、PATH、Homebrew、系统 OpenCC fallback。

## B. Native data / provenance

- config 与 `.ocd2` 来自同一 pinned BYVoid/OpenCC tag/commit；
- library、config、dictionary 全部进入 `vendor/MANIFEST.json`；
- Session/Plan 记录 native platform、library hash、data manifest hash、config hash；
- `includeTofuRiskDictionaries` 不再作为 Profile/runtime 开关；稳定 C API `opencc_open()` 使用 pinned OpenCC 的默认 `true`，记录为：

```text
tofu_policy = native_default_include
```

## C. Jieba 事实修正

v1.1 中“官方 Jieba 只有 Node 生态”的说法不准确。

OpenCC 1.4.x upstream 已存在 native external segmentation plugin `opencc-jieba` 与 plugin-backed configs。

V1.x 仍然不加入 Jieba，理由改为：

- 需要额外 native plugin library；
- 需要额外 Jieba resource；
- 每个平台都要构建、签名、hash、smoke test；
- 需要独立 regression/golden corpus。

因此 V1 UI 彻底删除“分词策略”下拉；标准 mmseg 是 pinned config 的 backend 行为。

## D. XHTML/XML 保真规范修复

### 1. 修复 HTMLParser offset 假设

v1.1 的表述容易让实现者误以为 `HTMLParser` 直接提供 absolute `(start,end)`。

v1.2 明确：

- `HTMLParser(convert_charrefs=False)` 只辅助事件/状态识别；
- tokenizer 自己维护 source cursor / line-start table；
- `getpos()` 需映射为 absolute character offset；
- start-tag 白名单属性使用 quote-aware scanner 精确定位 value span。

### 2. Structural invariant 从“所有 non-text token 不变”改成 planned-span invariant

旧规则与合法 `title/alt/lang/xml:lang` 修改冲突。

新规则：

> 只有 `ConversionPlan.allowed_spans` 可以变化；所有未计划 source slice 必须逐字符保持，其 UTF-8 bytes 因而保持一致。

计划修改 start-tag 时，也只允许目标 attribute value span 改变，标签其余 raw slice 保留。

### 3. NCX / OPF 同样改为 source-preserving patch

不再允许“因为文件小，所以 lxml parse → serialize”。

新策略：

```text
XML parser 找目标
→ source span patch
→ lxml verify only
```

OPF 仅对 `bk.getmetadataxml()` 返回的 metadata fragment 执行此约束；Sigil 自身重建 package document 的规范化不伪称为插件 byte-identical。

## E. lang 映射修复

v1.1：

```text
s2t → Legacy zh-TW
```

v1.2：

```text
s2t / tw2t / hk2t → Legacy 默认保持原值
BCP47 suggest → zh-Hant
```

原因：通用繁体没有台湾地区语义。插件不得为了字体兼容把普通 `s2t` 偷偷地区化。

台湾/HK 目标仍分别映射 `zh-TW` / `zh-HK`。

## F. OpenCC change attribution 修复

v1.1 名称：

```text
layered_diff
layer_chain
```

容易误解成 OpenCC 内部真实 execution trace。

v1.2 改为：

```text
attribution_method = comparative_config_diff
comparison_configs(...)
```

重要语义：

- 所有 comparison config 都独立转换**同一个原始 segment**；
- 不允许把 `s2t` output 再送 `s2tw`；
- selected config 的 output 是唯一 final target；
- `rule_source` 始终是实际 selected config，例如 `OpenCC:s2twp`；
- comparison 只决定 `variant/regional` 等解释标签与 confidence；
- 不声称命中 `TWPhrases.txt` 等具体词典。

## G. Golden / Differential Test 变更

Canonical oracle 现在只有一个：

```text
official OpenCC CLI built from pinned BYVoid/OpenCC source
```

Production path：

```text
bundled libopencc → C ABI → ctypes
```

Release differential：

```text
canonical CLI output == plugin native C-ABI output
```

允许差异数量：`0`。

Golden candidate 只能由 canonical CLI 生成，不能让 plugin backend 自己刷新 expected。

## H. 构建与供应链

新增 native build matrix：

```text
windows-x86_64
macos-x86_64
macos-arm64
linux-x86_64
linux-aarch64 (正式支持取决于稳定 CI runner；否则 experimental)
```

每个平台必须：

- 从 pinned upstream source 构建；
- upstream tests；
- C ABI symbol check；
- dynamic dependency check；
- clean-process ctypes load；
- 16 config load smoke test；
- SHA-256 manifest。

macOS 必须实际在 Sigil release build 上验证 native load；Windows 必须验证非 ASCII path。

## I. 同步更新的章节

重点更新：

- §4 全部；
- §7.4；
- §13；
- §15；
- §19.2–19.5；
- §21.1；
- §22；
- §24；
- §25.2；
- §29；
- §41–44；
- §47/§49；
- §55/§58；
- §62/§63；
- §68；
- §70；
- §74/§75；
- §93；
- §98；
- `INVARIANTS.md`。

## J. v1.2 最终技术路径

```text
Sigil BookContainer
       ↓
source-preserving Document Processor
       ↓
locked-span Rule Engine
       ↓
NativeOpenCCBackend
       ↓
ctypes stable C ABI
       ↓
pinned BYVoid/OpenCC libopencc
       ↓
pinned official config/.ocd2
       ↓
final target
       ↓
comparative classification (diagnostic only)
       ↓
Preview
       ↓
Verify allowed spans
       ↓
bk.writefile()
```

这条路径是 V1.x 的唯一生产实现路径；后续 AI 不应再自行选择 Python OpenCC backend、system OpenCC 或另一套 conversion engine。
