# OpenCC for Sigil：专业级 EPUB 中文简繁与地区转换插件工程规范

> 文档类型：Implementation Specification / Architecture & Acceptance Specification  
> 目标读者：AI Coding Agent、插件开发者、维护者、测试人员  
> 基线日期：2026-09-03  
> 文档版本：**1.3（Official Python Binding 架构锁定版，2026-09-05）**  
> 建议插件暂定名：`OpenCCForSigil`  
> 插件类型：Sigil `edit` plugin  
> 核心目标：在 **不破坏 EPUB 结构与排版语义** 的前提下，提供可预览、可审计、可扩展、可测试的简繁体及地区词汇转换能力。

> **1.3 修订摘要**（详见 `REVISION_NOTES.md`）：
> 1. V1 唯一 Production Backend 改为 pinned BYVoid/OpenCC 官方 Python Binding；PyPI distribution 的规范化名称为 `opencc`，版本锁定为 1.4.2。
> 2. Python 运行时只通过 `opencc.OpenCC(config)` 使用官方 binding；binding 底层仍是 OpenCC 官方 C++ Core，但插件不再自行维护 `ctypes`、C ABI wrapper 或 `libopencc` loader。
> 3. Build/Release 阶段获取并校验官方 wheel，提取为 vendored payload；Runtime 只选择 manifest 精确匹配的 CPython/OS/architecture/ABI payload，禁止 pip、联网和系统 OpenCC fallback。
> 4. 以 `opencc.__file__`、版本、payload hash 和 manifest provenance 验证实际 import 来源；预装在 user site-packages 的同名模块不视为可用依赖。
> 5. 保留 v1.2 已锁定的 XHTML/XML source-span 保真、preview/transaction、rules、logs、golden、regional explicitness、`comparative_config_diff` 与 Jieba 延期设计。
---

## 0. 规范用语

本文使用 RFC 风格约束词。任何实现模型或开发者必须按以下含义理解：

- **MUST / 必须**：不满足则视为实现错误，不得发布。
- **MUST NOT / 禁止**：不得以“实现方便”为理由违反。
- **SHOULD / 应当**：除非存在明确且记录在案的技术原因，否则必须实现。
- **SHOULD NOT / 不应**：通常禁止；若例外必须有测试与文档。
- **MAY / 可以**：可选增强，不影响 V1 合格性。

本文优先级高于任何自动生成代码中的默认习惯。若实现过程中发现本文与 Sigil 当前 Plugin API 或 OpenCC 当前版本存在事实冲突，**不得自行猜测**；应以当前官方 API 为准，并在 `docs/deviations.md` 记录偏差、原因、替代实现与测试结果。

## 0.1 文档地图（按 Phase 阅读，不要一次全量载入）

本文接近 4,000 行。给 AI Agent 下达单个 Phase 任务时，只需载入下表所列章节，外加 `INVARIANTS.md`（§98 的一页摘录）。

| Phase | 必读章节 | 参考章节 |
|---|---|---|
| 0 Skeleton | §0, §22, §23, §24, §19, §46, §71, §72 | §41, §42 |
| 1 OpenCC Core | §4（含 §4.5）, §5, §25, §29, §68, §70 | §44, §36 |
| 2 Document Processor | §7（含 §7.4–7.6）, §8, §27, §32, §77, §78 | §16 |
| 3 Sigil Adapter | §3.1-C, §6, §9, §26, §65, §66, §67, §79, §80, §81 | §52 |
| 4 Preview | §10, §21.1–21.2, §50, §69, §87, §88, §91 | §89, §90 |
| 5 Configs / NCX / Metadata / lang | §5, §6.3, §15, §31 | §29.2 |
| 6 Rules / Profiles | §11（含 §11.8）, §12, §13, §33, §34, §51, §82, §83, §84, §85 | §86 |
| 7 Transforms / History / Self-Test | §14, §16, §17, §20, §49 | §35 |
| 8 Review Annotation | §18 | §66, §67 |

重复内容的权威归属：状态机以 §65 为准（§9 为流程叙述）；禁令与不可妥协项以 §98 为准（§56、§95 为展开与示例）；默认值以 §47 为准（§13 为 Profile 序列化字段）。

---

# 1. 产品定位

## 1.1 一句话定义

`OpenCCForSigil` 是面向电子书制作、校对和精排用户的 **Sigil 专业中文转换插件**：使用 OpenCC 的配置式转换体系，对 EPUB 中真正面向读者显示的中文文本进行简繁、台湾、香港等转换，同时保护 XHTML/XML 结构、CSS、脚本、链接、ID 与资源引用，并提供预览、规则覆盖、日志、差异统计和准确率回归测试。

## 1.2 用户群

主要用户：

1. EPUB 精排用户；
2. 出版编辑、校对人员；
3. Sigil 高级用户；
4. 简繁双版本电子书制作人员；
5. 中文文本数字化/OCR 后处理用户；
6. 需要自定义术语表、专名表、地区词汇表的专业用户。

不以“一键把所有字替换掉”为产品目标。

## 1.3 核心设计原则

插件必须遵循以下原则，按优先级排序：

1. **结构安全 > 转换覆盖率**
2. **可解释 > 黑盒智能**
3. **官方 OpenCC 兼容 > 自创转换算法**
4. **用户显式选择 > 自动猜测用户意图**
5. **预览与审计 > 无提示批量修改**
6. **用户规则 Overlay > 修改上游官方词典**
7. **一次运行原子化 > 边处理边写入**
8. **可复现 > “当前最新词库但无法确认版本”**
9. **测试结果 > 主观感觉**
10. **核心逻辑与 Sigil UI 解耦**

---

# 2. 明确非目标

V1/V1.x **不得**把项目扩张成通用 EPUB 清洗工具。

以下功能不属于本插件核心范围：

- OCR；
- 图片删除、图片压缩、图片格式转换；
- 字体删除、字体子集化、字体替换；
- 封面替换；
- DRM；
- EPUB 重新打包器；
- 通用 HTML Cleaner；
- CSS 格式化；
- 全局错别字纠正；
- AI 文本润色；
- 自动改写港澳台政治、机构、人名等专有词；
- 联网提交整本电子书进行转换；
- Calibre 书库管理能力。

这些能力即使存在于参考项目 `tradsimp` 或其他 EPUB 工具中，也不得混入核心功能。

---

# 3. 参考实现与继承原则

## 3.1 主要参考项目

### A. OpenCC

项目：

`https://github.com/BYVoid/OpenCC`

用途：

- 转换语义的权威基准；
- 官方 configs；
- 官方 dictionaries；
- mmseg 逻辑语义；
- Jieba plugin configs；
- upstream golden tests；
- 版本与词典更新来源。

插件不得自己发明一套“OpenCC 风格”的最长匹配算法，然后声称结果等价于 OpenCC。

### B. tradsimp

项目：

`https://github.com/sheldonrrr/tradsimp`

参考以下思想：

- 只转换可见文本节点；
- 跳过 `<style>` / `<script>`；
- 保留 comment / entity / processing instruction；
- 大陆、台湾、香港转换分开；
- 用户词组覆盖；
- 用户词典 copy-on-write；
- 用户规则必须与 OpenCC 分词协同而非事后字符串替换（本文以 §11.8 锁定片段模型实现）；
- 引号与横竖排标点作为独立选项；
- 双语批注；
- 混合简繁诊断；
- 转换统计；
- 地区词汇转换；
- 用户规则按 conversion direction 管理。

**不得直接照搬 Calibre UI、Calibre Container、书库复制、OCR、删字体/删图片等逻辑。**

如果复制 `tradsimp` 的 GPLv3 代码而非仅参考设计，必须重新评估整个插件的许可义务。推荐方案是：

> **新实现 + 参考逻辑 + 独立测试。**

### C. Sigil Plugin API

官方参考：

`https://github.com/Sigil-Ebook/plugin-api-guide`  
`https://github.com/Sigil-Ebook/Sigil`

必须使用 Sigil 的 `BookContainer` 处理当前已打开 EPUB，不得自行把 EPUB 再解压、重打包。

已确认的核心 API 包括：

- `bk.readfile(id)`（文本文件返回 `str`，已按 UTF-8 解码）
- `bk.writefile(id, data)`
- `bk.text_iter()` / `bk.spine_iter()` / `bk.manifest_iter()` / `bk.selected_iter()`
- `bk.gettocid()`（NCX manifest id，可能为 `None`）/ `bk.getnavid()`（EPUB3 NAV，可能为 `None`）
- `bk.getmetadataxml()` / `bk.setmetadataxml()`
- `bk.getPrefs()` / `bk.savePrefs()`
- `bk.epub_version()` / `bk.get_opf()`
- `bk.colorMode()`（`"light"`/`"dark"`；旧版 Sigil 可能不存在，必须 `getattr` 回退）
- `bk.sigil_ui_lang`（UI 语言）
- `bk._w.usrsupdir`（Sigil 用户偏好目录；非正式 API，但 Sigil 官方示例插件在用，见 §19.6）

已确认的运行时语义：

- `run(bk)` 返回 `0` 视为成功，Sigil 才把插件写入的文件复制回书；返回非 `0` 时 Sigil 丢弃全部修改。§9.7 的事务边界建立在此语义上。
- 插件写入的修改**不进入 Sigil 的 Undo 栈**。用户唯一的回滚手段是 Sigil 的 Checkpoint（Edit → Checkpoint）。插件无 API 创建 Checkpoint，因此 §9.5、§21.2 要求 Apply 前提示。
- Sigil 2.x 的 Windows/macOS 打包版自带 Python 3、`lxml`、`css-parser`、`regex`、Tk 与 PySide6；Linux 发行版包中 Tk/PySide6 为可选依赖。插件必须在启动时检测 UI 工具包是否可用（§21）。

---

# 4. OpenCC 后端决策

## 4.1 V1 唯一 Production Backend：官方 Python Binding

V1 **只允许一个 Production Backend**：

- BYVoid/OpenCC 官方 Python Binding，版本锁定为 **1.4.2**；
- PyPI 项目的显示名称为 `OpenCC`，其规范化 distribution 名称与 wheel 文件名为 `opencc`；
- Python 代码只通过公开的 `opencc.OpenCC(config)` 和 `convert(text)` 使用它；
- 该 binding 是官方 OpenCC C++ Core 的 CPython native extension，不是 Python 重写版转换器；
- 官方 configs/dictionaries 与 binding 来自同一个 upstream release；
- **不使用 `opencc-py`、独立 `opencc-data`、系统 OpenCC、用户 site-packages 或 PATH 中的 converter。**

Canonical oracle 仍然是同一个 pinned BYVoid/OpenCC release 构建出的官方 CLI，但它与 Production Backend 是两条独立调用路径：CLI 只用于 golden/differential validation，用户 EPUB 转换必须经过 vendored official Python Binding（§29、§75）。

插件不得自行实现 C++ conversion logic、Python longest-match 算法或另一套 config/dictionary 语义；也不得把官方 CLI 逐 TextTarget 启动作为普通 runtime 转换路径。

### 4.1.1 已核验的官方 Python API

以下 API 以同级参考仓库 `../OpenCCForSigil-References/OpenCC` 的 `ver.1.4.2` tag，以及对应 PyPI 1.4.2 source/wheel metadata 为准（`BUILD-TIME VERIFIED`）：

```python
import opencc

converter = opencc.OpenCC("s2t")
result = converter.convert("汉字")
```

公开 package 还提供：

```python
opencc.CONFIGS
opencc.__version__
opencc.OpenCC(
    config="t2s",
    include_tofu_risk_dictionaries=True,
    resource_zip=None,
)
```

`opencc.clib.opencc_clib` 是 upstream package 的实现细节；OpenCCForSigil 不得直接 import 它，不得依赖其 private class 或自行管理 native buffer/handle lifetime。所有 Production Backend 调用都必须集中在 `opencc_backend.backend.OpenCCBackend`。

### 4.1.2 已核验事实（2026-09-05，作为本文基线）

| 项目 | 事实 / 规范结论 |
|---|---|
| Canonical source | `BYVoid/OpenCC` tag `ver.1.4.2`，peeled commit `025f371dc76b598d77384fbdab90c937471844d8` |
| PyPI distribution | PyPI JSON 的项目名为 `OpenCC`，规范化安装/文件名为 `opencc`; release version `1.4.2` |
| Python package | import name `opencc`; public class `opencc.OpenCC`; public methods `convert()`、`CONFIGS`、`__version__` |
| Native implementation | upstream `src/py_opencc.cpp` uses pybind11 to expose the official C++ Core; this is an official CPython extension, not a pure-Python converter |
| Official wheel tags observed | `cp310`, `cp311`, `cp312`, `cp313`, `cp314`；macOS x86_64/arm64、manylinux2014 x86_64/aarch64、Windows x86_64；每个 exact ABI/OS/architecture 必须单独入 manifest；V1 正式只纳入 `cp314` |
| V1 configs | pinned upstream `data/config` contains the 16 configs：`s2t t2s s2tw tw2s s2twp tw2sp s2hk hk2s s2hkp hk2sp t2tw tw2t t2hk hk2t t2jp jp2t` |
| V1 Python compatibility | **CPython 3.14.x / `cp314`**；当前 Sigil bundled Python **3.14.2** 是生产基准；**3.14.7** 仅为开发/CI 基线；patch 版本记录在 provenance，不参与 payload 选择 |
| normalization | 官方 config 可含 normalization 阶段；它属于 canonical output，插件不得绕过 |
| tofu-risk | 官方 Python API 默认 `include_tofu_risk_dictionaries=True`；V1 固定使用该默认值，不提供 UI 开关，provenance 记录 `native_default_include` |
| Jieba | upstream 存在额外的 native Jieba plugin 体系；V1 不 vendor、不暴露配置，见 §4.4 |

这些事实在 OpenCC 升级或 wheel 矩阵变化时必须按 §44 重新核验，不得从旧版本或模型记忆推断。

## 4.2 版本、wheel 与 payload 锁定

每个 release 必须锁定：

```text
OpenCC upstream tag + peeled commit
PyPI distribution/version
每个官方 wheel 的 URL、filename、SHA-256
每个 extracted payload 的 SHA-256
Python implementation/minor/ABI
OS + architecture
官方 config/dictionary provenance 与 hash
实际运行时 Python patch version（仅 provenance，不参与 payload 选择）
```

唯一权威 manifest 是 `vendor/opencc/manifest.json`，至少包含：

```json
{
  "schema_version": 1,
  "opencc_version": "1.4.2",
  "distribution_name": "opencc",
  "import_name": "opencc",
  "opencc_upstream_tag": "ver.1.4.2",
  "opencc_upstream_commit": "025f371dc76b598d77384fbdab90c937471844d8",
  "tofu_policy": "native_default_include",
  "provenance_source": "https://pypi.org/project/OpenCC/1.4.2/",
  "python_compatibility": {
    "implementation": "CPython",
    "major": 3,
    "minor": 14,
    "abi": "cp314",
    "production_baseline": "3.14.2",
    "development_ci": "3.14.7",
    "patch_participates_in_payload_selection": false
  },
  "payloads": [
    {
      "python_implementation": "CPython",
      "python_version": "3.14",
      "python_abi": "cp314",
      "os": "macos",
      "architecture": "arm64",
      "wheel_name": "opencc-1.4.2-cp314-cp314-macosx_11_0_arm64.whl",
      "wheel_sha256": "...",
      "payload_path": "payloads/macos-arm64-cp314",
      "payload_sha256": "..."
    }
  ],
  "config_data": {
    "source": "same official OpenCC 1.4.2 wheel/upstream release",
    "files": {}
  }
}
```

`wheel_sha256` 是下载 provenance；`payload_sha256` 是 Runtime 对实际导入目录执行的完整树 hash。manifest 中不得只写“最新版”，不得只从文件名推断 ABI 或版本。V1 manifest 必须固定 Python policy 为 `CPython 3.14.x / cp314`，并记录生产基准 `3.14.2` 与开发/CI 基线 `3.14.7`；patch 版本不得成为 payload key。Phase 0 可以没有 payload，但必须明确标记为空并在 Runtime fail fast。

## 4.3 Official wheel vendor 与平台策略

### 4.3.1 Fat Plugin 默认策略

V1 默认发布一个 Fat Plugin ZIP。它可包含多个官方 wheel 的 extracted payload：

```text
vendor/opencc/
├── manifest.json
└── payloads/
    ├── macos-arm64-cp314/
    ├── macos-x86_64-cp314/
    ├── windows-x86_64-cp314/
    ├── linux-x86_64-cp314/
    └── linux-aarch64-cp314/
```

这些目录名只是示例；最终 entries 必须由 pinned PyPI metadata 与 CI 实际验证结果生成，不得凭空声明不存在的 wheel。每个 payload 是官方 wheel 的原样 Python package 内容，不能被改写成另一套 converter。

V1 正式支持范围是 **CPython 3.14.x / `cp314`**，当前 Sigil 官方发行版本自带的 Bundled Python **3.14.2** 是生产基准。Python **3.14.7** 只作为本仓库开发/CI 环境，不得写成最低运行版本。patch 版本只进入 session/backend provenance，不参与 payload selection；3.14.2 与 3.14.7 必须选择同一个 payload。非 Sigil Bundled Python 的 CPython 3.14.x 仅为 best-effort，必须仍然满足 exact OS/architecture/ABI；CPython 3.13、3.15、PyPy 或其他 ABI 必须 fail fast。

### 4.3.2 Build / Release 约束

- Build pipeline MUST 从 PyPI/官方 release metadata 获取官方 `opencc` wheel，并校验 wheel SHA-256；
- 不修改 wheel 内 `opencc` package、官方 config 或 dictionary semantics；
- extracted payload 必须生成确定性的 tree hash，并记录 wheel filename、hash、source URL 和 upstream provenance；
- Runtime 不得运行 `pip`、`python -m pip`、网络下载或系统 package manager；
- Runtime 不得依赖用户 site-packages、Homebrew、Conda、pyenv 或系统 OpenCC；
- wheel 内部可能包含 `.pyd`/`.so` 等官方 extension 文件，但 OpenCCForSigil 不把它们当作独立 `libopencc` binary 管理，不直接用 `ctypes` 加载，也不自行维护其 ABI/DLL/dylib/so 生命周期；
- 发布前必须在 clean process 中验证 exact import、version、config discovery、smoke conversion 与 payload integrity；
- vendored payload integrity hash 对应原始 wheel 提取内容；Runtime 必须禁止在 payload 内写入 Python bytecode cache，避免 `__pycache__` 污染 hash；
- 若官方 wheel 缺少 CPython 3.14.x 的某个正式支持 OS/architecture runtime，发布必须阻塞，不能静默换后端。

若未来因体积改成 platform-specific ZIP，版本、Python 代码、wheel/data provenance 与行为必须相同，只允许 payload 集合不同。

## 4.4 Jieba：不属于 V1.x

OpenCC upstream 1.4.x 已有 native external segmentation plugin `opencc-jieba` 以及 `s2t_jieba`、`s2tw_jieba`、`s2hk_jieba`、`s2twp_jieba`、`tw2sp_jieba` 等 plugin-backed config。

V1.x **仍不实现 Jieba**，原因是：

- 需要额外 native plugin library 与 Jieba resource；
- 各 OS/Arch 都需要额外构建、签名、hash 与 smoke test；
- 必须增加独立 golden/regression corpus；
- 这会显著扩大 V1 supply-chain surface。

因此 V1 UI **不出现“分词策略”选项**。`Profile.segmentation` 字段可保留为迁移占位，但 V1 只允许值 `"mmseg"`。

V2 重新评估时必须：

- 同样从 pinned OpenCC upstream 构建 `opencc-jieba`；
- 记录 plugin library 与 Jieba data hash；
- 独立 regression corpus；
- UI 明确把 Jieba 作为另一个 backend config family，而非普通 mmseg 的隐藏开关。

## 4.5 Official Python Binding Runtime 事实约束（实现必须遵守）

### 4.5.1 RuntimeSelector 与 import 隔离

启动流程必须严格为：

```text
stdlib bootstrap
→ detect Python implementation/major/minor/patch/ABI/OS/architecture
→ load vendor/opencc/manifest.json
→ select exact payload
→ verify payload tree hash and manifest compatibility
→ insert selected payload root into sys.path
→ import opencc
→ verify opencc.__file__ is inside selected payload
→ verify opencc.__version__ and CONFIGS
→ construct OpenCCBackend
```

标准库允许在 payload path setup 之前导入。任何 vendored third-party module（包括 `opencc`）必须在 exact payload 选择后才能 import。

禁止：

- 在选择 payload 前执行顶层 `import opencc`；
- 调用 `pip`、`python -m pip`、系统 package manager 或网络下载；
- 从 user site-packages、Homebrew、Conda、pyenv、系统 Python 或 PATH 中发现同名 `opencc` 后复用；
- payload 缺失、hash 不匹配、origin 不在选中目录或版本不一致时静默 fallback。

如果 `opencc` 已经存在于 `sys.modules` 且 origin 不属于当前选中 payload，必须阻断并报告 import contamination，而不是“有 OpenCC 就用”。

### 4.5.2 CPython ABI 精确匹配

RuntimeSelector 至少检测：

```text
python_implementation
python_major
python_minor
python_patch       # provenance only
python_abi
os
cpu_architecture
```

例如：

```text
CPython / 3.14 / cp314 / macos / arm64
```

The payload key is intentionally `CPython / 3.14 / cp314 / macos / arm64`, not
`3.14.2` or `3.14.7`. The actual patch version (`3.14.2` for the current Sigil
production baseline or `3.14.7` in development/CI) is recorded only in
provenance.

`cp314` 不等于 `cp313` 或 `cp315`。V1 只接受 CPython 3.14.x 的 `cp314`；3.14.2 与 3.14.7 的 patch 差异不影响 payload selection，但必须记录在 provenance。free-threaded/debug ABI 也必须使用 manifest 中完全匹配的 tag。找不到 exact payload 时，External Python 必须 fail fast，并提示用户切回 Sigil Bundled Python。

推荐的 blocking message：

```text
Unsupported external Python runtime.

OpenCCForSigil is built for Sigil's bundled Python runtime.
Please switch Sigil Plugin Preferences back to Bundled Python.
```

### 4.5.3 OpenCCBackend public lifecycle

项目内部保留唯一业务抽象：

```python
class OpenCCBackend:
    def __init__(self, config: str): ...
    def convert(self, text: str) -> str: ...
    def provenance(self) -> BackendProvenance: ...
    def self_test(self) -> SelfTestResult: ...
```

具体实现只允许：

```python
import opencc
converter = opencc.OpenCC(config)
target = converter.convert(source)
```

此处的 `import opencc` 只能出现在 RuntimeSelector 已完成 payload 选择和 origin 验证之后的受控 backend 初始化路径。UI、DocumentProcessor、Rules、Preview、Verifier 不得直接 import `opencc`。

Backend 不实现简繁算法，不读取或修改 upstream dictionary，不承担 XHTML/XML、用户规则、diff 分类或 Sigil `BookContainer` 责任。一个 session 内可按 config 复用官方 converter 对象；不得在未经证明的情况下跨 worker 共享对象。

### 4.5.4 Config/data 与 tofu policy

优先使用官方 wheel payload 内与 binding 同版本的 config/data。若构建时提取 wheel 或 pinned upstream data，必须记录每个 config/dictionary hash，并在 manifest 中确认它们与 OpenCC 1.4.2 provenance 一致。

V1 使用官方 Python API 的默认 `include_tofu_risk_dictionaries=True`：

- 不提供 UI/Profile 开关；
- provenance 记录 `"tofu_policy": "native_default_include"`；
- canonical CLI oracle 必须采用等价默认 policy；
- 不通过自写 config 或后处理偷偷改变 policy。

### 4.5.5 Import origin 与 self-test

启动 preflight / Professional Mode Self-Test 至少验证：

```text
manifest schema
runtime triple
exact payload exists
payload tree SHA-256
opencc import origin
opencc.__version__
required config names in opencc.CONFIGS
s2t/t2s/regional smoke conversions
storage path
logging path
```

任何一项与 manifest 不一致都是 blocking error。Self-Test 不得以加载系统模块、调用 CLI 或安装依赖来“修复”失败。

### 4.5.6 Custom config sandbox

未来若开放 custom config，不能把用户任意路径直接传给官方 binding。必须：

```text
parse JSON
→ schema validate
→ collect referenced resources
→ reject path traversal / unsupported Jieba plugin
→ copy approved config + resources into cache/configs/<sha256>/
→ create official OpenCC resource_zip or approved payload snapshot
→ hash snapshot
→ freeze BackendProvenance
```

custom config 只能通过官方 `opencc.OpenCC` 支持的 public parameter 使用；不得绑定 upstream private extension symbols。Preview 后 snapshot 不得变化。

### 4.5.7 C/C++ API 的允许范围

OpenCC 官方 Python Binding 底层当然仍然依赖官方 C++ Core；upstream 的 C/C++ API、pybind11 extension 和 wheel 内 native file 可以在 provenance、许可证、wheel 内容审计中说明。但是 OpenCCForSigil **不得**直接绑定 stable C ABI、C++ private symbols、`ctypes.CDLL`，也不得自行实现 descriptor/buffer lifetime。Production boundary 固定为官方 Python Binding public API。

# 5. 功能范围

# 5.1 转换类型

必须支持以下 OpenCC 标准转换：

| ID | 含义 | 默认风险 |
|---|---|---:|
| `s2t` | 简体 → 通用繁体 | 低 |
| `t2s` | 繁体 → 简体 | 低 |
| `s2tw` | 简体 → 台湾繁体字形 | 中 |
| `tw2s` | 台湾繁体 → 简体 | 中 |
| `s2twp` | 简体 → 台湾繁体 + 台湾词汇 | 高 |
| `tw2sp` | 台湾繁体 + 台湾词汇 → 简体 | 高 |
| `s2hk` | 简体 → 香港繁体字形 | 中 |
| `hk2s` | 香港繁体 → 简体 | 中 |
| `s2hkp` | 简体 → 香港繁体 + 香港词汇 | 高 |
| `hk2sp` | 香港繁体 + 香港词汇 → 简体 | 高 |
| `t2tw` | 通用繁体 → 台湾规范 | 中 |
| `t2hk` | 通用繁体 → 香港规范 | 中 |
| `tw2t` | 台湾规范 → 通用繁体 | 中 |
| `hk2t` | 香港规范 → 通用繁体 | 中 |

以上 14 个 config 在 pinned `BYVoid/OpenCC ver.1.4.2` 的 `data/config/` 中均存在。`jp2t`/`t2jp` 也存在，放在“高级”，默认 UI 不突出日本模式，但 golden 测试（§29.2）覆盖全部 16 个。

## 5.2 普通转换与地区本地化必须分离

禁止把：

```text
软件 → 軟件
```

和：

```text
软件 → 軟體
```

描述为同一“简转繁”结果。

UI 必须在普通模式旁显示解释：

- **通用繁体**：主要处理字形与词组歧义；
- **台湾繁体**：字形符合台湾习惯；
- **台湾繁体 + 地区词汇**：还会把“软件、内存”等词转换为地区用语；
- 香港同理。

地区词汇模式必须有高风险提示：

> 会修改术语和地区用词，不仅是字形转换。建议先预览。

---

# 6. 转换范围

## 6.1 范围枚举

必须提供：

```text
转换范围
● 整本正文 XHTML
○ Book Browser 当前选中的文件
○ Spine 正文
```

可选增强：

```text
□ NAV
□ NCX
□ OPF 元数据
```

说明：

- “整本正文 XHTML”使用 `bk.text_iter()`；
- Book Browser 范围使用 `bk.selected_iter()`；
- Spine 范围使用 `bk.spine_iter()`；
- OPF 元数据不得通过简单正则处理整个 OPF；
- NAV 本质上是 XHTML，但需要在报告中单独标记；
- NCX 是 XML，必须走 XML-aware processor。

## 6.2 默认范围

默认：

```text
✓ 正文 XHTML
✓ EPUB3 NAV（若存在）
□ NCX
□ OPF 元数据
```

metadata 默认关闭，防止 ISBN、identifier、路径、机器字段受到任何意外影响。

## 6.3 OPF 元数据白名单

用户显式开启 “OPF 元数据” 后，**只允许**转换以下元素的文本内容：

| 元素 | 说明 |
|---|---|
| `dc:title` | 含 EPUB3 `meta[property=title-type]` 关联的多个 title |
| `dc:creator` / `dc:contributor` | 人名；同时转换其 `refines` 的 `file-as`、`alternate-script` |
| `dc:publisher` | |
| `dc:description` | 可能含 HTML 实体，须走 XML-aware 路径 |
| `dc:subject` | |
| `dc:rights` | MAY，默认不勾选 |
| `dc:coverage` | MAY，默认不勾选 |

**永不转换**：`dc:identifier`、`dc:language`（由 §15 语言模块单独处理）、`dc:date`、`dc:source`、`dc:type`、`dc:format`、`dc:relation`、所有 `meta` 的 `property`/`name`/`scheme`/`refines`/`id` 属性、非上述 refinements 的 `meta` 文本值（如 `dcterms:modified`、`calibre:*`、`belongs-to-collection` 的 `group-position` 等）。

OPF 处理必须通过 `bk.getmetadataxml()` / `bk.setmetadataxml()`，以 lxml 解析后只改白名单元素的 `.text`，再序列化；**禁止**对整个 OPF 做字符串替换。任何 OPF 变更在 Preview 中标记 `HIGH`（§10.3）。

## 6.4 NAV / NCX 的转换目标

- EPUB3 NAV：`<nav>` 内所有 `<a>`/`<span>` 的文本（含 `toc`、`landmarks`、`page-list`）、`<h1>`–`<h6>` 标题文本、`title` 属性。NAV 是 XHTML，复用 §7 processor，但 Change 上标记 `document_kind: nav`。
- NCX：`docTitle/text`、`docAuthor/text`、`navLabel/text`（toc、pageList、navList 三类）。NCX 走 XML-aware processor，不得复用 HTML tokenizer 的宽松规则；`content@src`、`id`、`playOrder` 永不修改。
- 两者的定位方式与 XHTML 一致（§77）。

---

# 7. XHTML/XML 安全处理

这是插件最重要的部分。

## 7.1 禁止行为

**MUST NOT：**

```python
re.sub(r"<[^>]+>", ...)
```

作为 XHTML parser。

MUST NOT 以 “lxml 解析 → 修改 → 序列化” 作为 XHTML 的**写回**路径（见 §7.4）；lxml 只用于验证层与 NCX/OPF。

MUST NOT 将整个 XHTML 字符串直接传入 OpenCC。

MUST NOT 转换：

- tag name；
- `id`；
- `class`；
- `href`；
- `src`；
- `style`；
- `epub:type`；
- `role`；
- `aria-*` 标识性字段；
- CSS selector；
- JavaScript；
- JSON-LD；
- SVG path data；
- MathML identifier；
- URL；
- file path；
- fragment ID。

## 7.2 应处理内容

默认转换：

- XHTML visible text node；
- `<head><title>`（阅读器把它当章节标题显示；不在 `<body>` 内但属于可见文本，**必须**默认转换）；
- heading；
- paragraph；
- list；
- table text（含 `<caption>`、`<th>`）；
- blockquote；
- figcaption；
- `<summary>` / `<details>` 文本；
- ruby base text；
- footnote text；
- EPUB nav label；
- `alt`；
- `title`（属性）；
- 可配置的 `aria-label`。

## 7.3 特殊元素

### `<script>`

完全跳过内容。

### `<style>`

完全跳过内容。

### `<code>` / `<pre>`

默认：

```text
不转换
```

用户可以在高级设置开启：

```text
□ 转换 code/pre 中自然语言文本
```

默认关闭，因为代码、命令、变量名可能包含中文标识符或固定字符串。

### `<math>`

默认不转换 MathML 内部。

但 `<annotation>` 的自然语言是否转换作为高级选项。

### `<svg>`

默认：

- 不碰 path / id / class / href；
- `<text>` / `<tspan>` 可见中文 MAY 转换；
- 默认关闭 SVG text 转换；
- 开启后必须单独计数。

### `<ruby>`

默认：

```html
<ruby>汉<rt>hàn</rt></ruby>
```

只转换 base text，不转换 `<rt>`，除非用户启用：

```text
□ 同时转换 ruby 注音文本中的中文
```

### 注释

`<!-- -->` 原样保留。

### Entity

命名 entity 与 numeric entity 必须保持语义，不得被二次 escape。具体策略见 §7.5。

## 7.4 解析与序列化保真策略（双层模型）

§7.1 禁止 regex 充当 parser，也**不允许**用“lxml 解析 → 修改 → 重新序列化”作为 XHTML 普通写回路径。XHTML 写回必须采用 source-preserving span patch：只替换 `ConversionPlan` 明确批准的 source span，其余 source slice 原样复用。

因此处理分两层，职责不得混合。

### 7.4.1 输出层：offset-preserving tokenizer + source slicing

推荐使用 `html.parser.HTMLParser(convert_charrefs=False)` 辅助识别事件和 raw-text 状态，但必须注意：**`HTMLParser` 不直接提供原始字符串的绝对 `[start, end)` offset。**

本插件自己的 `document/tokenizer.py` MUST：

1. 维护 source cursor 与 line-start offset table；
2. 将 `HTMLParser.getpos()` 的 line/column 映射回 absolute character offset；
3. 用 `get_starttag_text()` 与 source slice 校验 raw start-tag；
4. 对 start-tag 内属性使用 quote-aware lexical scanner 定位白名单 attribute **value span**，不得重新 format 整个 tag；
5. 输出：

```python
@dataclass(frozen=True)
class Token:
    kind: str
    raw: str
    start: int       # source string character offset, inclusive
    end: int         # exclusive
```

`TextTarget` / `AttributeTarget` 最终必须落到原始 source string 的绝对 `[start, end)` span。

Apply 采用：

```text
source[0:a]
+ replacement_1
+ source[b:c]
+ replacement_2
+ ...
+ source[z:]
```

**绝不重新生成未修改标签。**

### 7.4.2 允许变化与不可变化的精确定义

旧表述“所有非文本 token byte-identical”过强，会与合法 `title/alt/lang/xml:lang` 修改冲突。V1.2 统一改为：

> **只有 ConversionPlan 明确列出的可写 span 可以变化；所有未计划 source slice 必须逐字符相同，其 UTF-8 编码因此 byte-identical。**

允许的 planned span：

- visible text node；
- §67 白名单 attribute value；
- language 模式下 `lang/xml:lang` value；
- Review Annotation 模式明确新增的受控 span。

例如：

```html
<p class='abc' title="汉语" id="x">软件</p>
```

若计划转换 `title` 和文本，允许的变化仅是：

```text
"汉语" 中 value 内容 span
"软件" 文本 span
```

`<p class='abc' title="`、`" id="x">`、`</p>` 等 source slice 必须原样保留，包括空格、单双引号风格与属性顺序。

### 7.4.3 验证层：lxml + span invariant

Apply 后：

- 用 `lxml.etree` 解析 before/after，仅用于结构验证；
- 检查 §27 的 id/href/src/class 等 invariants；
- 重新 tokenize after；
- 根据 `ConversionPlan.allowed_spans` 验证所有**计划外** source segment 未改变；
- 对计划修改的 start-tag，除目标 attribute value span 外的 raw bytes 必须相同。

验证层只读，不产出写回内容。

### 7.4.4 NCX / OPF

NCX 与 OPF metadata 也采用“parser 定位 + source-preserving span patch”原则；`lxml` 只负责确认 XML 结构与目标节点，不作为最终 serializer。

OPF：

- 只通过 `bk.getmetadataxml()` / `bk.setmetadataxml()` 操作 metadata fragment；
- source-preserving processor 只替换 §6.3 白名单元素的 `.text` span；
- Sigil 在 `setmetadataxml()` 后如何重建 package document 属 Sigil 自身行为，不应被插件伪称为 byte-identical；插件自己的 metadata fragment 必须无计划外变化。

NCX：

- 保留 XML declaration、DOCTYPE、namespace prefix、空元素写法及无关 whitespace；
- 只 patch §6.4 允许的可见 label text span。

不得以“NCX/OPF 比较小”为理由放宽到全量 lxml serialize。

## 7.5 字符引用与实体的处理策略

| 形式 | 默认行为 | 说明 |
|---|---|---|
| 命名实体 `&nbsp;` `&amp;` `&lt;` … | 原样保留 | tokenizer 作为独立 token 输出；它会**切开**前后文本节点，属预期行为，对 OpenCC 的影响等同标点边界 |
| 数字字符引用 `&#x8F6F;` `&#36719;` | 原样保留，不转换 | 引用的是码位而非可见字，转换会改字节；Preview 中统计“数字字符引用中的 CJK 字符：N 个” |
| 可选：`decode_numeric_cjk_refs` | 默认 `false` | 开启后把 CJK 范围的数字引用解码为字符再参与转换，输出为字符；标记 `HIGH`，Profile 字段见 §13 |
| CJK 兼容表意文字 U+F900–U+FAFF 等 | 由 OpenCC 官方 `normalization` 步骤处理 | 分类 `normalization`，见 §4.5.4 |
| 变体选择符 / IVS / 私用区 | 原样保留 | 不作任何映射 |

## 7.6 已知限制：跨行内标签的整词匹配

所有以“文本节点”为转换单元的工具（本插件、`tradsimp`、`epub_tool`）都无法把 `头<em>发</em>` 作为 `头发` 整词匹配，因为两个字位于不同 TextTarget，OpenCC 分别看到 `头` 和 `发`。

V1 的处理方式：

- 在 README 与 `docs/architecture.md` 中列为已知限制；
- 增加诊断 `INLINE_BOUNDARY`（级别 `REVIEW`）：当某 TextTarget 的首/尾字符为 CJK，且相邻兄弟节点是行内元素（`em strong span a b i u s sub sup rt ruby code mark small` 等）并同样以 CJK 开头/结尾时，标记该位置；Preview 可按此诊断筛选；
- 不得为了“修复”这一限制而把多个文本节点拼接后转换再按长度切回——转换前后长度不保证一致，切回会破坏结构。

V2 候选：对由行内元素连接的连续 CJK run 做整体分词，再把 OpenCC 输出按 segment 边界投影回各文本节点（需要后端暴露 segment 信息，见 §4.5.3）。

---

# 8. HTML Processor 架构

不得把 OpenCC backend 与 HTML parser 写在同一函数。

接口：

```python
class DocumentProcessor:
    def analyze(
        self,
        text: str,
        options: ProcessingOptions
    ) -> DocumentAnalysis:
        ...

    def apply(
        self,
        text: str,
        plan: ConversionPlan
    ) -> ConvertedDocument:
        ...
```

转换目标必须抽象为：

```python
@dataclass(frozen=True)
class TextTarget:
    node_id: str              # DOM-like path + ordinal，见 §77
    source_text: str
    source_start: int         # 在原始文档字符串中的偏移（仅用于 Apply 拼接）
    source_end: int
    context: str
    tag_name: str | None
    attribute_name: str | None
    document_kind: str        # xhtml | nav | ncx | opf
    convert: bool
    skip_reason: str | None   # script/style/code/pre/math/svg/protected/...
```

OpenCC 只接触：

```text
TextTarget.source_text
```

不得接触完整文档结构。

---

# 9. 两阶段执行模型

> 状态名称、转移与约束以 §65 状态机为准；本节描述各阶段职责。

任何转换必须执行：

```text
SCAN
 ↓
ANALYZE
 ↓
PLAN
 ↓
PREVIEW
 ↓ 用户确认
APPLY
 ↓
VERIFY
 ↓
WRITE
 ↓
REPORT
```

禁止：

```text
readfile()
→ convert()
→ writefile()
→ 下一个文件
```

## 9.1 Scan

收集：

- 文件；
- MIME；
- spine 状态；
- NAV/NCX/metadata；
- 字符数量；
- 简繁混合情况。

## 9.2 Analyze

生成：

- TextTargets；
- 命中规则；
- OpenCC diff；
- 用户规则 diff；
- 高风险 diff；
- 跳过内容。

## 9.3 Plan

建立不可变 `ConversionPlan`。

```python
@dataclass(frozen=True)
class ConversionPlan:
    session_id: str
    profile_id: str
    config_id: str
    segmentation: str
    scope: Scope
    document_plans: tuple[DocumentPlan, ...]
    rule_snapshot_hash: str
    backend_provenance_hash: str
```

## 9.4 Preview

预览阶段 **不得调用 `bk.writefile()`**。

## 9.5 Apply

用户确认后把 Plan 应用于 staging buffer。

确认对话框必须包含 Checkpoint 提示（插件修改不进入 Sigil Undo 栈，见 §3.1-C）：

```text
插件修改无法用 Ctrl+Z 撤销。建议先在 Sigil 中 Edit → Checkpoint 保存当前状态。
[我已建立 Checkpoint，继续应用]   [取消]
□ 以后不再提示
```

“不再提示”状态保存在 `bk.savePrefs()`；session summary 记录 `checkpoint_notice_shown: true|false`。

## 9.6 Verify

写入 Sigil 容器前必须验证：

- parser（lxml）可重新解析；
- 原 tag/attribute 结构约束（§27）；
- protected attributes 未变化；
- href/src/id 集合未变化；
- XHTML namespace 未丢失；
- XML declaration 规则正确；
- **planned-span 不变量**：只有 `ConversionPlan.allowed_spans` 可以变化；所有未计划 source slice 必须与输入相同；计划修改 start-tag 时，除目标 attribute value span 外其余 raw slice 不变（§7.4.2/§27.1.1）；
- 所有产生变化的文本 token 都对应 Plan 中的某个 TextTarget（不存在计划外修改）；
- UTF-8 输出有效。

## 9.7 Write

全部 verify 通过后才能批量：

```python
bk.writefile(...)
```

若任何文件失败：

- 返回非零；
- 不得主动吞异常；
- Sigil Plugin Runner 应放弃整次变更。

Sigil 官方插件模型本身支持：插件失败/取消时，修改不会正式复制回 Sigil。实现必须利用该事务边界。

---

# 10. Preview / Diff 系统

## 10.1 必需统计

预览页显示：

```text
文件：37
扫描字符：128,431
发生转换：4,728
OpenCC 转换：4,611
用户规则：117
地区词汇：83
高风险转换：24
跳过 script/style/code：19
冲突：2
```

## 10.2 Diff 行

每一条变化至少包含：

```python
@dataclass
class Change:
    file_id: str
    href: str
    location: str
    source: str
    target: str
    category: ChangeCategory
    rule_source: str
    attribution_method: str | None
    comparison_stage: str | None
    attribution_confidence: str | None
    context_before: str
    context_after: str
```

`category`：

```text
character          单字符 OpenCC change（基于 diff 的近似分类，不代表字符词典命中）
phrase             多字符 OpenCC change
opencc_change      无法稳定细分/归因的普通 OpenCC change
variant            比较配置显示的地区字形差异（如 s2tw 相对 s2t）；属于 heuristic
regional           比较配置显示的地区词汇差异（如 s2twp 相对 s2tw）；属于 heuristic
user_rule          用户 exact/protect 规则（锁定片段，§11.8）
regex_rule         用户 regex 规则
punctuation
quotation
language_metadata
normalization      仅当受控 diagnostic comparison 明确证明时使用（§4.5.6）；否则归普通 OpenCC change
annotation
```

`character` 与 `phrase` 在纯字符串 diff 下无法严格区分（后端不提供命中信息，§4.5.3）：变化 span 长度为 1 记 `character`，否则记 `phrase`，并在 `attribution_method` 字段注明 `comparative_config_diff`。`variant` 与 `regional` 由 §68 的 comparative config diff 分类得到；它不是实际词典命中 trace。

## 10.3 高风险标签

以下默认 `HIGH`：

- regex 用户规则；
- force pivot；
- 混合简繁强制归一；
- 1→N 或 N→1 长度变化的用户规则；
- 专名规则；
- 同一个 source 存在多个 target；
- 转换 `<svg><text>`；
- OPF metadata conversion 与 `dc:language` 修改；
- `decode_numeric_cjk_refs` 引起的变化。

以下默认 `REVIEW`（与 §87 一致；1.0 版曾把地区词汇列为 HIGH，1.1 起统一为 REVIEW，因为 `s2twp` 模式下地区词汇是用户明确选择的主功能，全部标 HIGH 会淹没真正的高风险项）：

- 地区词汇（`regional`）；
- 用户 exact 规则（`user_rule`）；
- 用户规则覆盖了官方 OpenCC 本会给出的不同结果；
- `INLINE_BOUNDARY` 诊断命中处；
- `attribution_confidence: low` 的变化。

## 10.4 Preview 筛选

必须支持：

```text
全部
高风险
用户规则
地区词汇
仅当前文件
仅指定词
```

支持搜索 source / target。

---

# 11. 用户规则系统

这是专业版插件的重要功能。

## 11.1 原则

官方 OpenCC dictionary：

```text
READ ONLY
```

用户不得直接修改 bundled OpenCC 文件。

所有自定义内容采用 Overlay。

## 11.2 规则优先级

固定如下，从高到低：

```text
1. Exclusion / Protected Rules
2. Book-local Exact Rules
3. Global Exact Rules
4. Imported Profile Exact Rules
5. Advanced Regex Rules
6. OpenCC selected config
7. Optional punctuation / quote transform
```

实现不得随意改变。

注意：

- “保护规则”优先于转换；
- exact rules 默认优先于 OpenCC；
- regex 必须在 exact 后、OpenCC 前还是 OpenCC 后，由规则字段 `phase` 决定；
- 默认 regex phase = `pre_opencc`；
- post-opencc regex 必须标记 HIGH。

## 11.3 Exact Rule Schema

```json
{
  "id": "uuid",
  "enabled": true,
  "type": "exact",
  "direction": "s2twp",
  "source": "服务器",
  "target": "伺服器",
  "scope": "global",
  "priority": 100,
  "source_note": "个人术语表",
  "comment": "",
  "created_at": "...",
  "updated_at": "..."
}
```

## 11.4 Protected Rule

示例：

```json
{
  "type": "protect",
  "direction": "*",
  "source": "Apple",
  "scope": "global"
}
```

以及：

```text
保护文本：
乾隆
软件工程师 Zhang San
```

保护规则可以是：

- exact；
- regex；
- selector scoped。

## 11.5 Regex Rule

高级用户功能。

```json
{
  "type": "regex",
  "pattern": "...",
  "replacement": "...",
  "phase": "pre_opencc",
  "scope": "global",
  "enabled": true
}
```

必须：

- 有测试按钮；
- 显示 sample；
- 有最大替换次数保护；
- 禁止 catastrophic backtracking；
- 单规则超时或复杂度检测；
- 默认关闭。

## 11.6 Scope

规则范围：

```text
global
profile
book
file
selector
```

V1 必须支持前三个；`selector` MAY V1.1。

## 11.7 Direction

规则必须明确方向：

```text
s2t
s2tw
s2twp
s2hk
s2hkp
t2s
tw2s
tw2sp
hk2s
hk2sp
t2tw
t2hk
*
```

不得使用一个无方向的 `UserPhrases.txt` 对所有模式无条件生效。

这是对 `tradsimp` 用户词典系统的重要改进。

## 11.8 规则与 OpenCC 的集成方式：锁定片段模型

### 11.8.1 为什么不能“先替换再 OpenCC”，也不能“叠加进 OpenCC 词典”

两种直觉方案都已验证不可用：

1. **先字符串替换再交给 OpenCC**：target 会被 OpenCC 二次转换。例如用户希望保留 `着`，OpenCC `s2tw` 仍会把它变成 `著`；用户写 `服务器→服務器`，OpenCC 也可能继续改。
2. **把用户词典叠加进 config 的 conversion_chain**：官方多步 config 下失效。实测 `s2twp` 链为 `STPhrases/STCharacters → TWPhrases → TWVariants`，把 `服务器\t服務器` 放进第一步后，第二步 `TWPhrases` 立刻把 `服務器` 改回 `伺服器`。要让用户词条在每一步都“幸存”，需要为每一步补恒等映射，规则越多越不可维护，且与官方词典行为纠缠。

### 11.8.2 模型

用户 exact/protect 规则被编译为**锁定片段（locked spans）**，OpenCC 只作用于未锁定的片段：

```text
输入文本 T
  → RuleEngine.lock(T, snapshot) 
      按规则 source 做最长优先、从左到右、不重叠匹配
      每个匹配产出 LockedSpan(start, end, target, rule_id)
      protect 规则的 target == source
  → 未锁定的片段逐段送 OpenCC.convert(config)
  → 按原顺序拼接：opencc(seg0) + target1 + opencc(seg1) + target2 + …
```

性质：

- target 就是用户写的字面，不会被 OpenCC 触碰；
- 锁定边界等价于 OpenCC 遇到标点时的分词边界，未锁定片段内部完全是官方行为，golden 兼容性不受影响；
- 归因精确：锁定片段的 `rule_source = UserRule:<uuid>`，无需差分；
- 确定性：同一 snapshot + 同一输入必得同一切分。

以下样例是该规则模型的**必须回归用例**，实现后应使用 pinned official Python Binding OpenCC 1.4.2 / `s2twp` 验证：

```text
规则：服务器→服務器（exact），乾隆→乾隆（protect），着→着（protect）
这台服务器着火了   → 這臺服務器着火了
乾隆时期的服务器   → 乾隆時期的服務器
穿着睡衣去着手处理 → 穿着睡衣去着手處理
```

### 11.8.3 匹配细则

- 候选规则集 = snapshot 中 `enabled` 且 `direction ∈ {当前 config, *}` 的 exact/protect 规则；
- 同一位置多条规则匹配：先按 §11.2 优先级，再按 source 长度（长优先），再按 `priority` 字段，再按规则 id 字典序（保证确定性）；
- 冲突（同 scope、同 priority、同 source、不同 target）在 **Plan 之前**由 `rules/conflicts.py` 检出并 BLOCKING（§83），不允许进入 lock 阶段；
- 匹配是**字符级精确**（区分全半角、不做 NFC 归一）；需要归一的场景由用户用 regex 规则处理；
- source 为空、或全部为空白/标点的规则在 validate 阶段拒绝。

### 11.8.4 regex 规则的位置

- `phase = pre_opencc`：在 lock 之后、OpenCC 之前，只对**未锁定片段**逐段执行；替换结果参与 OpenCC；
- `phase = post_opencc`：在拼接之后对最终文本执行，但匹配**不得跨越锁定片段边界**（实现上仍按片段执行）；
- 两种 phase 均受 §11.5 的最大替换次数与超时保护；
- regex 规则的归因 `rule_source = RegexRule:<uuid>`，级别 `HIGH`。

### 11.8.5 与 Change 的对应

每个 `LockedSpan` 恰好产生 0 或 1 条 `Change`（protect 且 source==target 时不产生 Change，但计入 `protected_spans` 统计）。§10.1 的“用户规则：117”即锁定片段产生的 Change 数。

---

# 12. 规则导入/导出

## 12.1 支持格式

必须支持：

### TSV

```text
direction<TAB>source<TAB>target<TAB>comment
s2twp<TAB>服务器<TAB>伺服器<TAB>技术书
```

### CSV

UTF-8 BOM 与 UTF-8 无 BOM 均接受。

### JSON

使用本插件 schema。

### OpenCC TXT

```text
source<TAB>target
```

导入时必须要求选择 direction。多值条目（`source<TAB>t1 t2 t3`）只取第一个 target，并在导入预览中逐条标注“已丢弃候选：t2 t3”；以 `#` 开头的注释行忽略。

## 12.2 导入流程

```text
选择文件
→ Parse
→ Validate
→ Normalize
→ Detect duplicates
→ Detect conflicts
→ Preview
→ Import
```

不允许静默覆盖。

## 12.3 冲突类型

```text
SAME_SOURCE_DIFFERENT_TARGET
DUPLICATE
DIRECTION_OVERLAP
PROTECTED_CONFLICT
REGEX_OVERLAP
OFFICIAL_OVERRIDE
```

## 12.4 导出

支持：

- 当前全部规则；
- 当前 profile；
- 当前书局部规则；
- 仅启用；
- 仅冲突。

导出应包含 schema version。

---

# 13. Profile 系统

专业用户通常不是每次重新选参数。必须支持保存 Profile。

示例：

```text
通用繁体出版
台湾技术书
香港小说
繁转简校对
保守转换
```

Schema：

```json
{
  "schema_version": 1,
  "id": "uuid",
  "name": "台湾技术书",
  "conversion": "s2twp",
  "segmentation": "mmseg",
  "scope": "all_xhtml",
  "convert_nav": true,
  "convert_ncx": false,
  "convert_metadata": false,
  "convert_alt": true,
  "convert_title": true,
  "convert_aria_label": false,
  "convert_svg_text": false,
  "convert_ruby_rt": false,
  "convert_code_pre": false,
  "decode_numeric_cjk_refs": false,
  "quotation_mode": "keep",
  "punctuation_mode": "keep",
  "language_metadata": "keep",
  "language_preset": "legacy",
  "ruleset_ids": [],
  "preview_required": true
}
```

字段说明：

- `segmentation` 在 V1.x 只允许 `"mmseg"`，只是未来 migration 占位，**UI 不提供选择器**；
- `language_metadata`：`keep | suggest | force`；`language_preset`：`legacy | bcp47`（§15）；
- official Python Binding 的 tofu policy 不属于 Profile 参数，固定由 pinned API default 决定并记录在 provenance；
- `decode_numeric_cjk_refs` 见 §7.5，V1.1 才在 UI 暴露。

# 14. 引号与标点

参考 `tradsimp`，但作为**独立模块**。

## 14.1 默认

```text
引号：保持不变
标点：保持不变
```

不能因为用户选 `s2tw` 就自动改引号。

## 14.2 引号选项

```text
保持
中文弯引号：“ ”
东亚直角引号：「 」
嵌套直角：『 』
```

## 14.3 横竖排标点

高级：

```text
不变
横排标准
竖排兼容标点
```

必须与 writing-mode detection 分离。

不得未经用户确认修改 CSS `writing-mode`。

---

# 15. lang / xml:lang

提供：

```text
语言标记
● 不修改
○ 根据目标转换建议修改
○ 强制修改
```

## 15.1 两套映射 preset

BCP47 script tag 在语义上更精确；部分旧阅读器/字体规则又更依赖 `zh-TW` / `zh-HK` 这类地区标签，因此保留 `legacy` 与 `bcp47` 两种 preset。

**重要：普通 `s2t` 只表示通用繁体，不等于台湾繁体。插件不得为了字体兼容把它偷偷地区化。**

| config | Legacy preset | BCP47 preset |
|---|---|---|
| `s2t`, `tw2t`, `hk2t`（目标为通用繁体） | **保持原值，不自动改**；UI 可让用户显式选择 `zh-TW` 或 `zh-HK` | `zh-Hant` |
| `s2tw`, `s2twp`, `t2tw` | `zh-TW` | `zh-Hant-TW` |
| `s2hk`, `s2hkp`, `t2hk` | `zh-HK` | `zh-Hant-HK` |
| `t2s`, `tw2s`, `tw2sp`, `hk2s`, `hk2sp` | `zh-CN` | `zh-Hans` |
| `t2jp` / `jp2t` | 不修改 | 不修改 |

Profile：`"language_preset": "legacy" | "bcp47"`；`"language_metadata": "keep" | "suggest" | "force"`。

当 `conversion in {s2t, tw2t, hk2t}` 且 preset=`legacy`：

- `suggest` 只能提示“通用繁体没有地区 Legacy tag”，不得自动写 `zh-TW`；
- `force` 必须要求用户额外明确选择 `zh-TW` 或 `zh-HK`，否则 Apply disabled。

## 15.2 修改对象与一致性

“修改”时以下三处必须**同一次**处理，并在 Preview 中作为一组 `language_metadata` Change 显示：

1. OPF `dc:language`（多个时全部处理，非中文值不动）；
2. 每个转换范围内 XHTML 的 `<html lang>` 与 `<html xml:lang>`；
3. 正文内元素级 `lang`/`xml:lang`，仅当现值为中文标记（`zh`、`zh-*`）时替换。

注意：

- 不修改 `zh-Latn`、`zh-Bopo`、`zh-Cyrl`、`zh-Mong` 等明确非 Han script 标记；
- 不对非中文书自动强制修改；
- `dc:language` 更新属于 OPF metadata HIGH-risk 变更，必须单独出现在 Preview；
- source-preserving attribute patch 规则按 §7.4 / §67 执行。

# 16. 混合简繁诊断

必须提供 preflight。

输出：

```text
Detected:
Simplified dominant
Traditional dominant
Mixed
Unknown
```

不得仅依赖单个字符判断。

诊断结果用于提示，不用于未经用户确认自动改变 conversion direction。

Mixed 情况显示：

```text
警告：当前文件包含混合简繁。
普通 S2T/T2S 可能导致局部重映射。
```

提供：

```text
□ 强制统一后再转换
```

默认关闭，属于 HIGH 风险。

---

# 17. Force Pivot

参考 `tradsimp` 的 force pivot 思路，但必须严格控制。

例：

```text
混合繁体 → 先 T2S → 再 S2TWP
```

只作为高级功能。

必须：

- 默认关闭；
- 标 HIGH；
- preview required；
- 日志记录 pivot chain；
- 不得宣称是“纠错”；
- 不得用于自动错别字校正。

---

# 18. 双语/原文审校模式

参考 `tradsimp` 的 bilingual annotation，但重新定义为：

> **Review Annotation Mode**

用途是校对，不是默认发布格式。

模式：

```text
Off
Changed only
Full paragraph
```

生成结构必须带插件命名空间 class，例如：

```html
<span class="occs-review-pair">
  <span class="occs-review-target">...</span>
  <span class="occs-review-source">...</span>
</span>
```

并插入有明确 marker 的 CSS：

```text
/* OpenCCForSigil Review Annotation BEGIN */
...
/* OpenCCForSigil Review Annotation END */
```

必须提供：

```text
Remove Review Annotations
```

且清理是幂等的。

不得每次运行叠加一层 annotation。

---

# 19. 日志与审计

必须同时提供：

1. UI Summary；
2. stdout/stderr；
3. persistent JSONL log；
4. session summary JSON。

## 19.1 Session ID

每次运行：

```text
UUIDv4
```

## 19.2 JSONL Event Schema

```json
{
  "ts": "2026-09-03T10:00:00+08:00",
  "level": "INFO",
  "session_id": "...",
  "event": "conversion_change",
  "file": "Text/ch01.xhtml",
  "node": "p[12]/text()[1]",
  "source": "软件",
  "target": "軟體",
  "category": "regional",
  "rule_source": "OpenCC:s2twp",
  "attribution_method": "comparative_config_diff",
  "comparison_stage": "s2twp-vs-s2tw",
  "attribution_confidence": "high",
  "config": "s2twp"
}
```

## 19.3 日志级别

```text
DEBUG
INFO
WARNING
ERROR
```

## 19.4 默认隐私策略

日志默认不得把整段正文复制进去。

默认只记录：

- changed token；
- 最大前后文各 20~30 字；
- 文件；
- 位置；
- rule source。

用户可以选择：

```text
日志正文
● 最小
○ 上下文
○ 完整 diff
```

## 19.5 Session Summary

```json
{
  "session_id": "...",
  "started_at": "...",
  "finished_at": "...",
  "plugin_version": "...",
  "sigil_version": "...",
  "python_version": "3.14.2",
  "epub_version": "...",
  "book_path": "...",
  "profile": "...",
  "config": "s2twp",
  "segmentation": "mmseg",
  "backend_name": "BYVoid/OpenCC official Python Binding",
  "opencc_version": "1.4.2",
  "opencc_python_binding_version": "1.4.2",
  "python_implementation": "CPython",
  "python_abi": "cp314",
  "runtime_os": "macos",
  "runtime_architecture": "arm64",
  "opencc_upstream_tag": "ver.1.4.2",
  "opencc_upstream_commit": "...",
  "import_path_id": "macos-arm64-cp314",
  "wheel_filename": "opencc-1.4.2-cp314-cp314-macosx_11_0_arm64.whl",
  "wheel_sha256": "...",
  "payload_sha256": "...",
  "opencc_import_origin": "vendor/opencc/payloads/macos-arm64-cp314/opencc/__init__.py",
  "data_manifest_sha256": "...",
  "tofu_policy": "native_default_include",
  "attribution_method": "comparative_config_diff",
  "language_preset": "legacy",
  "checkpoint_notice_shown": true,
  "rules_hash": "...",
  "files_scanned": 37,
  "files_changed": 24,
  "changes": 4728,
  "high_risk_changes": 24,
  "warnings": 2,
  "status": "success"
}
```

## 19.6 日志位置

封装：

```python
storage.resolve_user_data_dir(bk)
```

优先：

1. Sigil 插件偏好目录：`<bk._w.usrsupdir>/plugins_prefs/OpenCCForSigil/`。这正是 `bk.savePrefs()` 写 JSON 的位置，Sigil 官方示例插件也用 `bk._w.usrsupdir` 定位；`_w` 是非正式 API，必须 `getattr` 探测，不可用时进入 2；
2. 用户 home 下 `.opencc-for-sigil/`；
3. OS temp（仅当前 session，并在 UI 与日志中警告“本次历史不会持久化”）。

`preferences.json` 之外的数据（rules、profiles、logs、history）不得塞进 `bk.savePrefs()` 的单一 JSON；后者只保存“最近使用的 profile id、UI 状态、数据目录路径”。

不得写入插件安装目录作为唯一持久存储方案（Sigil 更新插件会整目录覆盖）。

## 19.7 日志保留

默认：

```text
最近 50 次或 30 天
```

用户可配置。

支持：

```text
导出当前日志
打开日志目录
清空历史日志
```

---

# 20. 转换历史

插件维护：

```text
history/index.json
```

只记录摘要，不保存整本书。

UI：

```text
日期
书名/文件名
Profile
方向
变化数
OpenCC 版本
规则版本
状态
```

点击可打开 session report。

---

# 21. UI 规范

V1 使用 Tkinter/ttk；核心不得依赖 UI。

选择理由与边界：

- Sigil 的 Windows/macOS 打包版同时带 Tk 与 PySide6；Sigil 官方 `plugin_utils.py` 推荐新插件用 PySide6，但 Tk 依赖更少、启动更快，且本插件 UI 以表单与列表为主。
- `ui/` 必须只依赖 `app/controller.py` 暴露的 view-model（纯数据），不得 import `core/`、`document/`、`opencc_backend/` 或 `bk`。这样 V2 若切换 PySide6 只需替换 `ui/`。
- Preview 的变化列表可能有数万行，`ttk.Treeview` 必须分页或虚拟加载（每次插入不超过 2,000 行），不得一次性 insert 全部。
- 主题：优先 `bk.colorMode()`（`getattr` 探测），不存在时读 Sigil prefs 中的主题设置，再不行按系统默认。

若 Python 环境没有 Tk：

- 插件必须检测（`import tkinter` 失败）；
- 给出明确错误（stdout 一份；若 PySide6 可用则用它弹一个只含错误信息的对话框，不得因此引入第二套完整 UI）；
- 不得 crash stack trace 后结束；
- 返回非 0，书不修改。

## 21.1 主窗口

建议布局：

```text
┌ OpenCC for Sigil ─────────────────────────────┐
│ Profile [台湾技术书 ▼]      [管理 Profile]     │
│                                               │
│ 转换                                          │
│ 从 [简体 ▼] → [台湾繁体+地区词汇 ▼]           │
│                                               │
│ 范围                                          │
│ ● 全部 XHTML  ○ Spine  ○ Book Browser 选中   │
│ ☑ NAV  ☐ NCX  ☐ Metadata                     │
│                                               │
│ 文本                                          │
│ ☑ alt/title  ☐ code/pre ☐ SVG text            │
│ 引号 [保持] 标点 [保持]  lang [不修改]         │
│                                               │
│ 规则                                          │
│ 3 个用户规则 | 0 冲突 | [管理规则]             │
│                                               │
│ [扫描并预览]                                  │
└───────────────────────────────────────────────┘
```

不得直接提供一个醒目的“一键转换整本”绕过 preview。

## 21.2 Preview 窗口

三栏：

```text
左：文件
中：变化列表
右：上下文 / rule detail
```

底部：

```text
[导出报告] [取消] [应用 4,728 个变化]
```

存在 HIGH risk 时：

```text
应用 4,728 个变化（含 24 个高风险）
```

点击“应用”后先弹 §9.5 的 Checkpoint 提示，再进入 `APPLYING_TO_STAGE`。存在 BLOCKING 时按钮 disabled（§87）。

## 21.3 Rule Manager

字段：

```text
启用
方向
类型
Source
Target
Scope
Priority
来源
备注
```

按钮：

```text
新增
复制
编辑
禁用
删除
导入
导出
查冲突
测试
```

---

# 22. 核心目录结构

最终仓库建议：

```text
OpenCCForSigil/
├── README.md
├── LICENSE
├── CHANGELOG.md
├── THIRD_PARTY_NOTICES.md
├── pyproject.toml
├── requirements-dev.txt
├── Makefile
│
├── plugin/
│   └── OpenCCForSigil/
│       ├── plugin.xml
│       ├── plugin.py
│       ├── plugin.svg
│       │
│       ├── app/
│       │   ├── controller.py
│       │   ├── commands.py
│       │   ├── session.py
│       │   └── errors.py
│       │
│       ├── core/
│       │   ├── models.py
│       │   ├── pipeline.py
│       │   ├── converter.py           # 锁定片段 + OpenCC 调度
│       │   ├── classifier.py          # comparative_config_diff（§68）
│       │   ├── planner.py
│       │   ├── staging.py
│       │   ├── verifier.py
│       │   └── diagnostics.py
│       │
│       ├── document/
│       │   ├── tokenizer.py           # source-offset preserving tokenizer
│       │   ├── attribute_scanner.py   # quote-aware attribute value span
│       │   ├── xhtml_processor.py
│       │   ├── xml_processor.py       # NCX / metadata source-preserving patch
│       │   ├── text_targets.py
│       │   ├── protected_content.py
│       │   ├── ruby.py
│       │   ├── svg.py
│       │   └── metadata.py
│       │
│       ├── opencc_backend/
│       │   ├── interface.py           # core protocol, no third-party import
│       │   ├── backend.py             # official opencc.OpenCC adapter
│       │   ├── runtime_selector.py    # exact CPython/OS/arch/ABI selector
│       │   ├── manifest.py            # payload manifest and provenance
│       │   ├── configs.py             # allowlist + comparison configs
│       │   ├── provenance.py
│       │   ├── integrity.py           # payload/tree hash verification
│       │   └── errors.py
│       │
│       ├── rules/
│       │   ├── models.py
│       │   ├── engine.py
│       │   ├── precedence.py
│       │   ├── validators.py
│       │   ├── conflicts.py
│       │   ├── importers.py
│       │   └── exporters.py
│       │
│       ├── transforms/
│       │   ├── quotations.py
│       │   ├── punctuation.py
│       │   ├── language_tags.py
│       │   └── annotations.py
│       │
│       ├── sigil/
│       │   ├── adapter.py
│       │   ├── scope.py
│       │   ├── preferences.py
│       │   └── storage.py
│       │
│       ├── ui/
│       │   ├── main_window.py
│       │   ├── preview_window.py
│       │   ├── rules_window.py
│       │   ├── profile_window.py
│       │   ├── history_window.py
│       │   ├── widgets.py
│       │   └── theme.py
│       │
│       ├── logging_ext/
│       │   ├── logger.py
│       │   ├── jsonl.py
│       │   ├── report.py
│       │   └── retention.py
│       │
│       ├── resources/
│       │   ├── defaults/
│       │   ├── schemas/
│       │   ├── i18n/
│       │   └── third_party/
│       │
│       └── vendor/
│           └── opencc/
│               ├── manifest.json
│               └── payloads/           # extracted official OpenCC wheels
│                   ├── macos-arm64-cp314/
│                   ├── macos-x86_64-cp314/
│                   ├── windows-x86_64-cp314/
│                   ├── linux-x86_64-cp314/
│                   └── linux-aarch64-cp314/
│
├── tests/                        # 以 §73 为准
├── native_build/
│   ├── build_opencc.py           # pinned upstream source → platform artifacts
│   ├── verify_binary.py
│   └── README.md
│
├── tools/
│   ├── fetch_opencc_wheels.py
│   ├── vendor_opencc.py
│   ├── export_verified_payload.py
│   ├── merge_verified_payloads.py
│   ├── verify_vendor.py
│   ├── build_plugin.py
│   ├── validate_artifact.py
│   ├── generate_golden.py
│   ├── differential_test.py
│   ├── inspect_opencc_release.py
│   ├── update_opencc.py
│   ├── build_spec_bundle.py
│   └── inspect_log.py
│
└── docs/
    ├── architecture.md
    ├── native-backend.md
    ├── rule-format.md
    ├── testing.md
    ├── release.md
    ├── privacy.md
    └── deviations.md
```

`vendor/opencc/payloads/*` 是唯一允许运行的 OpenCC Python Binding 来源；每个 payload 必须来自 manifest 所列官方 wheel。不得把 payload 内的 extension 拆出来当作独立 library，也不得从系统路径加载 OpenCC。`resources/third_party/THIRD_PARTY_NOTICES.md` 与 wheel 内 license/authors notice 必须进入最终 ZIP。

# 23. Sigil Plugin 根入口

`plugin.py` 必须保持极薄。

原则：

```python
def run(bk):
    try:
        return Controller(bk).run()
    except UserCancelled:
        return 1
    except Exception:
        log_exception(...)
        return 2
```

`plugin.py` 不应包含：

- OpenCC 逻辑；
- XHTML parser；
- 规则解析；
- 巨型 UI；
- dictionary 内容。

---

# 24. plugin.xml

应为 `edit` plugin。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plugin>
  <name>OpenCCForSigil</name>
  <type>edit</type>
  <author>...</author>
  <description>Professional Chinese conversion for EPUB using the official OpenCC Python Binding</description>
  <engine>python3.4</engine>
  <version>0.1.0</version>
  <autostart>true</autostart>
  <autoclose>false</autoclose>
  <oslist>osx,unx,win</oslist>
</plugin>
```

注意：

- Sigil 的 `engine` 标识 `python3.4` 是 plugin engine 名称，不代表本项目只能使用 Python 3.4 语法；
- `<name>` 必须与 zip 内顶层目录名、`plugin.py` 所在目录名一致；
- V1 正式运行时必须是 **CPython 3.14.x / `cp314`**；当前 Sigil Bundled Python **3.14.2** 是生产基准，启动必须拒绝非 CPython 3.14.x；不得把 3.14.7 当作最低运行版本；
- 仓库开发/CI 工具链由 `.mise.toml` 精确固定为 Python **3.14.7**、uv **0.12.9**、Ruff **0.16.6**；patch 版本只记录 provenance，发布 payload 仍按 major/minor、ABI、OS、architecture 选择；
- `plugin.py` 只允许标准库 bootstrap + Controller 入口，不得直接加载 OpenCC library、解析 XHTML 或写业务逻辑；
- official OpenCC Python Binding 由 `opencc_backend.runtime_selector` 在 runtime 通过 manifest 验证后选择；只有在 exact payload 验证完成后才允许把该 payload root 插入 `sys.path`。

# 25. Core API

## 25.1 Converter

```python
class ChineseConverter(Protocol):
    def convert(
        self,
        text: str,
        request: ConvertRequest
    ) -> ConvertResult:
        ...
```

```python
@dataclass(frozen=True)
class ConvertRequest:
    config: str
    segmentation: str
    rules_snapshot: RuleSnapshot
```

```python
@dataclass
class ConvertResult:
    source: str
    target: str
    changes: list[TokenChange]
    diagnostics: list[Diagnostic]
```

## 25.2 OpenCC Backend

```python
class OpenCCBackend(Protocol):
    def __init__(self, config: str): ...
    def available_configs(self) -> tuple[str, ...]: ...
    def convert(self, text: str) -> str: ...
    def provenance(self) -> BackendProvenance: ...
    def self_test(self) -> SelfTestResult: ...
    def comparison_configs(self, config: str) -> tuple[str, ...]: ...
    def close(self) -> None: ...
```

V1 concrete implementation：

```text
OpenCCBackend
  ├─ RuntimeSelector       # exact runtime triple → payload
  ├─ VendorManifest        # wheel/payload/config provenance
  └─ opencc.OpenCC         # official public Python API
```

Backend 只做“字符串进、字符串出”和 native resource lifecycle。以下都**不属于 backend**：

- 用户 locked-span rules；
- diff；
- `variant/regional` 分类；
- XHTML/XML；
- UI；
- Sigil BookContainer。

`comparison_configs()` 只是 §68 的诊断元数据，例如：

```python
comparison_configs("s2twp") == ("s2t", "s2tw", "s2twp")
```

它**不表示 OpenCC 内部实际按这三个 config 顺序执行**。

UI 不得直接 `import opencc`、调用 RuntimeSelector 或持有 official converter object。

# 26. Staging 与内存

默认 staging：

```python
dict[file_id, ConvertedDocument]
```

若待转换 UTF-8 文本总量超过配置阈值，例如 64 MiB：

- SHOULD spill staging 到 temp directory；
- temp 文件名使用 session UUID；
- 退出时清理；
- 日志记录。

不允许因超大书直接逐文件永久写入 Sigil。

---

# 27. 验证器

每个文档 apply 后执行：

```python
VerificationResult
```

检查：

## 27.1 Structural invariants

转换前后以下集合必须一致：

```text
id
href
src
class（除 review annotation 模式）
epub:type
role
manifest relation
```

## 27.1.1 Planned-span invariant

这是写回验证的最高优先级不变量：

```text
allowed = ConversionPlan.allowed_spans
```

- 只有 `allowed` 中的 text/attribute spans 可以变化；
- before/after 中所有计划外 source slices 必须相同；
- 计划修改 start-tag attribute 时，只允许目标 attribute value span 变化，tag 其余 raw slice 不变；
- Review Annotation 是唯一允许显式新增结构的普通例外，并由独立 mode/verifier 管理。

## 27.2 Tag invariants

非 annotation 模式：

```text
element count
tag sequence
```

应保持。

## 27.3 Protected block invariants

`script/style/code/pre/math` 等按配置应完全一致。

## 27.4 Encoding

Sigil `readfile()` 返回文本时按 UTF-8 处理；写回必须是合法 Unicode 字符串。

不得自行改回 GBK / Big5。

---

# 28. 准确率测试体系

“准确率”不能只用十几个词证明。

测试必须分四层。

---

# 29. Layer A：Canonical Official Python Binding Compatibility

## 29.1 Oracle

Canonical oracle：

```text
official `opencc` CLI built from the same pinned BYVoid/OpenCC release
```

Golden 生成路径使用由同一 pinned upstream source 构建的官方 CLI `opencc`；插件生产路径使用 manifest 精确选择的 official Python Binding payload，并调用公开 `opencc.OpenCC` API。

因此测试的是：

```text
same upstream source/data
official CLI invocation
vs
vendored official Python Binding invocation
```

插件对相同：

```text
input
config
```

必须输出与 canonical CLI **逐 Unicode code point 相同**。

禁止把插件自己的当前输出当 oracle。

## 29.2 Config Matrix

V1 allowlist：

```text
s2t   t2s
s2tw  tw2s   s2twp  tw2sp
s2hk  hk2s   s2hkp  hk2sp
t2tw  tw2t   t2hk   hk2t
t2jp  jp2t
```

矩阵来源必须同时满足：

1. pinned upstream tag 的 `data/config/` 中相应文件存在；
2. selected official wheel payload 的 `opencc.CONFIGS` 暴露相应 config；
3. config/data provenance hash 在 `vendor/opencc/manifest.json` 中；
4. official Python Binding 可以用 `opencc.OpenCC(config)` 成功构造；
5. canonical CLI 可以加载同一 config snapshot。

多、少或 hash 不一致均视为 provenance failure。

## 29.3 Golden Corpus

必须纳入：

- OpenCC upstream 官方 golden/test fixtures；
- 本项目 §30 ambiguity corpus；
- §31 regional corpus；
- 一组较长连续文本 corpus；
- 每个 V1 config 至少有 plugin-owned smoke/golden coverage。

`tools/generate_golden.py` 只能调用 pinned canonical CLI 生成 candidate expected，然后输出 diff 供人工 review；不得直接用 Production Backend 自己刷新 expected。

# 30. Layer B：中文歧义回归集

建立：

```text
tests/golden/ambiguity/
```

类别至少：

### 干 / 乾 / 幹

覆盖：

```text
干燥
树干
干部
干活
乾隆
干净
自干五
```

### 发 / 發 / 髮

```text
发展
头发
发现
发型
发动
一发千钧
```

### 后 / 後

```text
皇后
以后
后天
后面
```

### 面 / 麵

```text
面孔
面条
面对
一碗面
表面
```

### 里 / 裏 / 里

```text
公里
里面
里程
邻里
```

### 只 / 隻

```text
只有
一只猫
只好
```

### 台 / 臺

```text
台湾
一台电脑
舞台
台风
```

### 周 / 週

```text
周朝
一周
周围
周年
```

### 复 / 復 / 複

```text
恢复
复杂
复习
复印
```

### 制 / 製

```text
制度
制造
制作
控制
```

### 征 / 徵

### 余 / 餘

### 于 / 於

### 准 / 準

### 松 / 鬆

### 游 / 遊

### 尽 / 儘 / 盡

### 别 / 彆 / 別

### 斗 / 鬥

### 卷 / 捲

### 系 / 係 / 繫

## 30.1 Expected 结果来源

这些 case 的 expected output **必须从 pinned OpenCC oracle 生成并人工 review 后冻结**。

不得由 AI 凭语言感觉批量生成 expected。

---

# 31. Layer C：地区词汇测试

台湾：

```text
软件
硬件
内存
内存条
服务器
鼠标
打印机
出租车
互联网
人工智能
数据库
视频
```

香港另建 corpus。

验证重点：

1. `s2t` 不应被错误当作 `s2twp`；
2. `s2tw` 与 `s2twp` 差异必须可见；
3. 普通模式不得偷偷做地区用词本地化；
4. 地区模式 diff 必须分类为 `regional`。

---

# 32. Layer D：EPUB/XHTML Structural Safety

必须构造专门 EPUB fixture。

## 32.1 Basic XHTML

输入：

```html
<p id="简体-id" class="简体-class" title="汉语">
  汉语发展
</p>
```

期望：

- visible text 转换；
- `title` 根据配置转换；
- id 不动；
- class 不动。

## 32.2 CSS

```html
<style>
.简体 { font-family: "汉语字体"; }
</style>
```

该 `<style>` planned span 为空，因此整个 style block source slice 必须 **byte-identical**；不接受“语义等价但字节不同”。

## 32.3 Script

```html
<script>
const text = "汉语";
</script>
```

必须 unchanged。

## 32.4 URL

```html
<a href="https://example.com/汉语?x=简体">汉语</a>
```

只转 link text。

## 32.5 Fragment

```html
<a href="#简体">汉语</a>
<div id="简体">...</div>
```

href/id 都不改。

## 32.6 Entity

```html
<p>汉语&nbsp;发展 &amp; 软件</p>
```

entity 结构不得损坏。

## 32.7 Ruby

## 32.8 SVG

## 32.9 MathML

## 32.10 Footnote

## 32.11 NAV

## 32.12 NCX

## 32.13 EPUB2

## 32.14 EPUB3

全部纳入 fixture。

---

# 33. 用户规则测试

必须测试：

```text
exact overrides OpenCC
protected overrides exact
book overrides global
disabled rule ignored
wrong direction ignored
duplicate detected
conflicting target rejected
import round-trip
export/import identity
```

---

# 34. Regex 安全测试

包含：

- invalid regex；
- empty regex；
- zero-width runaway；
- catastrophic patterns；
- very large replacement；
- max replacement count；
- post-opencc conflict。

---

# 35. 幂等性测试

对适用模式测试：

```text
convert(convert(text)) == convert(text)
```

仅用于理论上应幂等的同方向 normalization。

不允许用：

```text
t2s(s2t(text)) == text
```

作为正确性要求，因为简繁转换本质上可能有信息损失。

---

# 36. Determinism

相同：

```text
plugin version
official OpenCC Python Binding/wheel/config/data provenance
profile
rules
input
```

必须生成相同输出与相同 change classification（含 §68 的 comparative config diff 与 §11.8 的锁定切分）。

session UUID 和时间除外。

`difflib.SequenceMatcher` 必须以 `autojunk=False` 构造，且输入为字符序列，避免长文本触发启发式导致对齐不确定。

---

# 37. 性能测试

Corpus：

```text
10 KB
100 KB
1 MB
10 MB
```

EPUB：

```text
10 XHTML
100 XHTML
1000 XHTML
```

记录：

- scan；
- OpenCC；
- parsing；
- preview building；
- apply；
- verify。

性能不是第一优先级；不得为了快退回 regex 解析 XHTML。

基线必须分别记录 `convert`（selected config final target）与 `classify`（§68 comparison configs + diff）的耗时；comparative classification 使 Analyze 阶段的 official Python Binding 调用通常最多为片段数 × 3。若 10 MB corpus 的 classify 耗时超过 convert 的 3 倍，视为实现问题（例如 difflib 未按字符序列使用）。

---

# 38. Fail-safe 测试

模拟：

- 某 XHTML 无法解析；
- vendor dictionary 缺失；
- checksum 不匹配；
- rules JSON 损坏；
- log 目录不可写；
- temp 不可写；
- UI cancel；
- apply 中 exception；
- verify failure。

原则：

> 任何不确定状态都优先“不修改 EPUB”。

---

# 39. 日志测试

必须验证：

- 每 session 唯一 ID；
- success/error/cancel 状态；
- 不默认泄露整段正文；
- version provenance 存在；
- rule hash 存在；
- changed count 正确；
- 日志 rotation；
- JSONL 每行合法 JSON。

---

# 40. 验收阈值

V1 发布前必须满足：

## 转换兼容

```text
Official mmseg golden tests: 100% pass
```

## XHTML safety

```text
Structural fixture: 100% pass
```

## 用户规则

```text
Rule precedence tests: 100% pass
```

## Crash

已知测试 corpus：

```text
0 unhandled exception
```

## 数据完整

所有 bundled dictionary/config：

```text
checksum pass
```

## Preview / Apply

preview 生成的 planned target 与 apply 最终 target：

```text
100% identical
```

---

# 41. CI

CI 分成 Python/plugin、official wheel payload 与 canonical CLI 三类。

## 41.1 Plugin matrix

| 维度 | 取值 |
|---|---|
| Python | 当前 Sigil 稳定版打包版本 + 上一个稳定版打包版本 + 最新稳定 CPython |
| OS | ubuntu / windows / macos |

每次 PR 至少：

```text
lint
unit
ambiguity
regional
document source-preserving safety
rules
integration(fake BookContainer)
package metadata validation
```

## 41.2 Official wheel/payload matrix

release/nightly 必须对每个正式支持 runtime triple：

```text
resolve exact CPython implementation/minor/ABI/OS/architecture
fetch official OpenCC wheel metadata
verify official wheel SHA-256
extract payload without semantic modification
verify payload tree SHA-256 and manifest
import opencc from selected payload in a clean process
verify import origin and OpenCC version
load all 16 configs through opencc.OpenCC
run canonical Python/CLI smoke corpus
```

macOS 必须至少覆盖 arm64；Windows x64 必须覆盖非 ASCII temp/plugin path。没有对应 official wheel 的 runtime 不得伪装成正式支持。

## 41.3 Golden

- ordinary PR 可使用仓库中已冻结的 canonical golden；
- release CI MUST 至少在一个平台重新构建 pinned official CLI 并执行 §75 differential；
- OpenCC version update PR MUST 在全部正式支持 runtime triples 重新执行 wheel validation + golden。

`tests/performance/` 只在 nightly/release 执行。GUI smoke test只在支持环境执行。

# 42. Build / Package

Release 分为 official wheel vendor validation 与 plugin package 两步。

## 42.1 Official wheel payload build

`tools/fetch_opencc_wheels.py` / `tools/vendor_opencc.py` / `native_build/build_opencc.py`：

1. 读取 pinned BYVoid/OpenCC tag/commit 与 PyPI `opencc` 版本；
2. 查询官方 release/PyPI wheel metadata，按 exact CPython/OS/architecture 选择 wheel；
3. 下载官方 wheel 并校验 wheel SHA-256；
4. 解包到 `vendor/opencc/payloads/<runtime-triple>/`，不修改 package/config/data；
5. 计算 payload tree SHA-256，生成 wheel/payload/provenance manifest；
6. 在 clean process 中 import `opencc`，检查 origin、version、CONFIGS 与 smoke conversion；
7. 使用同一 upstream release 的官方 CLI 运行 canonical corpus；
8. 输出 payload artifact + metadata；跨平台无法在当前 host import 时，必须显式标记未运行 target self-test，并在目标 runtime 验证后才可 release。

## 42.2 Plugin build

`tools/build_plugin.py`：

1. 清理 build；
2. 收集已通过 CI 的 official wheel payloads；
3. 验证所有 payload 的 OpenCC version/upstream provenance 一致；
4. 验证每个 payload 的 exact runtime selector fields、wheel hash 和 payload hash；
5. 生成 `vendor/opencc/manifest.json`；
6. 运行 tests；
7. 检查 plugin.xml；
8. 校验 `THIRD_PARTY_NOTICES`、OpenCC license/authors notice、无 `.pyc`/`__pycache__`/开发文件；
9. 解包自检；
10. 构建：

```text
OpenCCForSigil_0.1.0.zip
```

zip 内必须只有一个顶层目录：

```text
OpenCCForSigil/
  plugin.xml
  plugin.py
  vendor/
  ...
```

正式 release 不允许在用户机器上下载、安装或编译 OpenCC；所有 payload 必须在 Build/Release 阶段进入 ZIP。

## 42.3 GitHub-hosted native matrix

当维护者没有 Windows/Linux/macOS 多平台设备时，GitHub Actions MUST 使用
native hosted runners 完成 payload 验证。每个 matrix job 只能上传自己在
目标 runner 上通过 self-test 与 official CLI differential 的 payload
artifact；汇总 job 才能合并 manifest 并构建 Fat Plugin。仅完成 extraction
或 `--skip-import-test` 的 payload 不得进入 release ZIP。

# 43. Dependency 供应链

发布包必须：

- vendored OpenCC payload 仅来自 pinned official wheel；
- 保存 OpenCC Apache-2.0 LICENSE 与 wheel 内/构建时纳入组件的第三方 notices；
- 每个 wheel 与 extracted payload 有 SHA-256；config/data provenance 也必须有 hash；
- 构建 provenance 可追溯到 upstream tag/commit、PyPI metadata 与 CI run；
- 不在 runtime 联网下载、安装或更新 OpenCC；
- 不执行系统中未验证的 OpenCC module/CLI；
- 不允许 payload 选择绕过 manifest 或 exact ABI 匹配。

OpenCC 升级必须独立 PR。

PR 至少附：

```text
OpenCC 1.4.2 → 1.4.3
upstream NEWS summary
wheel tag/ABI matrix check
binding/core/config/data provenance diff summary
golden diff summary
regional changes
ambiguity regression
platform/runtime payload results
manual review result
```

# 44. 更新 OpenCC 的标准流程

不得只复制新词典、只替换某个平台 payload 或只升级 Python package metadata。

必须：

```text
pin new upstream tag + commit and official Python Binding version
↓
review upstream NEWS / Python API / config schema / wheel matrix
↓
fetch official wheels and verify PyPI SHA-256
↓
↓
extract payload + regenerate manifest
↓
run clean-process import/origin/config self-tests
↓
build official CLI from the same upstream source
↓
generate candidate canonical golden using CLI
↓
run official Python Binding vs CLI differential
↓
ambiguity diff
↓
regional diff
↓
structural/integration full suite
↓
manual review
↓
regenerate vendor/opencc/manifest.json
↓
update provenance + THIRD_PARTY_NOTICES
↓
release note
```

若官方 Python API、wheel tags、ABI/payload layout 发生 breaking change，或 golden diff 超过人工阈值，升级 PR 不得自动合并。

# 45. Versioning

插件使用 SemVer：

```text
MAJOR.MINOR.PATCH
```

其中：

- core 行为 breaking → MAJOR；
- 新功能/config → MINOR；
- bugfix / dictionary sync → PATCH 或 MINOR，按影响判断。

日志必须始终记录 plugin + OpenCC data 双版本。

---

# 46. 错误模型

统一异常：

```python
PluginError
├── DependencyError
├── DataIntegrityError
├── ParseError
├── RuleValidationError
├── RuleConflictError
├── ConversionError
├── VerificationError
├── StorageError
└── UserCancelled
```

UI 不显示原始 Python traceback 作为唯一信息。

但 DEBUG log 必须保存 traceback。

---

# 47. 安全默认值

首次启动：

```text
Profile: 保守转换
Conversion: s2t 或由用户明确选择
Segmentation: OpenCC 标准 config / mmseg（固定，无 UI 选择）
Scope: XHTML + NAV
Metadata: off
NCX: off
alt/title: on
code/pre: off
SVG text: off
MathML: off
Quotation: keep
Punctuation: keep
lang: keep（preset: legacy）
Numeric CJK char refs: keep（不解码）
Tofu-risk dictionaries: native default include（固定，不可改）
Regex rules: off
Force pivot: off
Review annotations: off
Checkpoint notice: on
Preview: mandatory
```

本节是默认值的唯一权威来源；§13 的 Profile 示例字段必须与本节一致。

---

# 48. 专业模式

设置：

```text
□ 启用高级/专业选项
```

启用后展示：

- custom config；
- regex；
- force pivot；
- SVG；
- MathML annotation；
- dictionary inspection；
- exact rule source；
- full diff export；
- diagnostic mode；
- backend info；
- hash；
- golden self-test。

---

# 49. Self-Test

插件必须提供：

```text
工具 → OpenCC Self Test
```

输出：

```text
Platform triple: PASS
Vendor manifest schema/hash: PASS
Exact Python/OS/architecture/ABI payload: PASS
Official `opencc` import origin: PASS
OpenCC version/provenance: PASS
Config load (16/16): PASS
Dictionary/config checksum: PASS
Basic conversion: PASS
Comparative classification self-check: PASS
Locked-span self-check: PASS
Ambiguity smoke test: PASS
XHTML source-span safety smoke test: PASS
Storage: PASS
```

Self-Test 不得加载系统 OpenCC、user site-packages 或 CLI 代替 Python Binding；其 selected payload/hash/import origin 必须与当前 session backend 完全一致。

# 50. Conversion Report

支持导出 Markdown / JSON。

Markdown 示例：

```text
# OpenCC Conversion Report

Plugin: ...
OpenCC: ...
Profile: Taiwan Technical
Config: s2twp
Files: 37
Changes: 4728
High Risk: 24

## High Risk

Text/ch03.xhtml
软件 → 軟體
Rule: OpenCC:s2twp (regional, comparative_config_diff)

## User Overrides

服务器 → 伺服器
Rule: user:tech_terms.json
```

---

# 51. Book-local rules

用户可以选择：

```text
保存为：
● 全局规则
○ 当前 Profile
○ 当前书
```

“当前书”规则不建议直接写入 EPUB。

默认以：

```text
book fingerprint
```

关联。

fingerprint 可由：

```text
OPF unique identifier
+ title
```

稳定计算。

如果没有 identifier，再 fallback。

---

# 52. 不污染 EPUB 原文件

除用户主动启用以下功能外：

- Review Annotation；
- language metadata；
- OPF metadata；

插件不应添加：

- 私有 metadata；
- 自定义 manifest；
- conversion log；
- rules file；

到 EPUB 内。

日志存外部。

---

# 53. 与 tradsimp 的功能映射

| tradsimp 能力 | Sigil 版本处理 |
|---|---|
| OpenCC | 保留，换成标准化 backend |
| mmseg | 保留 |
| Jieba | 移出 V1.x（§4.4），V2 依前置条件评估 |
| 大陆/台湾/香港 | 保留 |
| 繁体地区互转 | 保留 |
| quotes | 保留，独立模块 |
| vertical punctuation | 保留，高级 |
| user dictionary | 保留并强化为 overlay rules |
| custom phrases | 保留 |
| bilingual | 改为 Review Annotation |
| mixed diagnostics | 保留 |
| force pivot | 保留，高风险 |
| Calibre library copy | 删除 |
| OCR | 删除 |
| remove fonts | 删除 |
| remove images | 删除 |
| Calibre custom columns | 删除 |
| online 繁化姬 | 默认删除 |
| online API | 不属于 V1 |

---

# 54. 为什么默认不做在线繁化姬

专业 EPUB 插件默认必须可离线、可复现。

联网服务存在：

- 隐私；
- 词库版本漂移；
- 无法长期复现；
- 网络失败；
- 商用条款；
- 结果差异。

如未来加入，应作为：

```text
External Compare
```

只允许短文本人工测试，不得上传整本 EPUB。

---

# 55. 源码开发顺序

必须按以下阶段推进，防止 AI 一次性生成巨大不可控项目。

V1.0 的功能范围保持完整（§58），但交付按四个可独立安装验证的里程碑串行进行；每个里程碑结束时产出一个可安装的 zip 与对应 tag：

| 里程碑 | 包含 Phase | 用户可见成果 |
|---|---|---|
| **M1 可用内核** | 0, 1, 2, 3, 4 | 全部 16 个 config、正文/NAV 安全转换、预览与 Apply、日志与事务 |
| **M2 元数据与语言** | 5 | NCX、OPF 元数据白名单、lang preset |
| **M3 规则与 Profile** | 6 | exact/protect 规则、导入导出、冲突检测、Profile |
| **M4 专业变换与历史** | 7 | 引号/标点、混合诊断、pivot、历史、Self-Test |

V1.0 release = M1–M4 全部通过 §93 退出条件。M1 结束即可对外发 `0.x` 预览版收集反馈，但不得称 1.0。

## Phase 0 — Skeleton

完成：

- plugin.xml；
- plugin.py；
- package；
- CI；
- version；
- storage；
- logging skeleton。

验收：Sigil 可以安装、运行、退出，不修改书。

## Phase 1 — OpenCC Core

完成：

- pinned official `opencc` Python Binding wheel payload、RuntimeSelector、manifest/hash verification（§4.1–4.5）；
- backend interface（§25.2，含 `comparison_configs`）；
- 全部 16 个 V1 allowlist config 可由 `opencc.OpenCC(config)` 构造并 smoke test；
- official binding tofu policy 固定与 provenance；
- official CLI canonical golden 与 Python Binding differential（§29、§75）；
- comparative config classification（§68）；
- §30 歧义集初版。

不接 UI。

## Phase 2 — XHTML Safe Processor

完成：

- tokenizer 输出层与 lxml 验证层（§7.4）；
- visible nodes（含 `<head><title>`）；
- script/style protection；
- attr policy；
- ruby/code/svg policy；
- 字符引用策略（§7.5）；
- `INLINE_BOUNDARY` 诊断（§7.6）；
- structural verification（§27，含“仅 planned span 可变化”的 source-slice invariant）。

## Phase 3 — Sigil Adapter

完成：

- text_iter；
- selected_iter；
- spine；
- staging；
- write transaction。

## Phase 4 — Preview

完成：

- scan；
- plan（含 RuleSnapshot 占位，规则为空）；
- diff 与分类筛选；
- statistics；
- Checkpoint 提示与 apply confirmation。

**M1 在此结束。**

## Phase 5 — NCX / OPF 元数据 / lang

增加：

- NCX XML-aware processor（§6.4）；
- OPF 元数据白名单（§6.3）；
- lang preset 与三处一致性（§15）；
- 地区词汇 corpus（§31）与 `variant`/`regional` 分类的 UI 解释（§5.2）。

**M2 在此结束。**

## Phase 6 — Rules 与 Profile

完成：

- 锁定片段模型（§11.8）；
- exact / protect；
- direction / scopes（global、profile、book）；
- conflict 检测与 BLOCKING；
- TSV / CSV / JSON / OpenCC TXT 导入导出；
- Profile 保存/加载/迁移（§13、§72）；
- Rule Test Sandbox（§82）。

**M3 在此结束。**

## Phase 7 — Professional Transforms 与历史

- quote；
- punctuation（横排标准；竖排兼容标点为 V1.1）；
- mixed 诊断；
- pivot；
- 转换历史（§20）；
- Self-Test（§49）；
- Conversion Report 导出（§50）。

**M4 在此结束，V1.0 release gate（§97）。**

## Phase 8 — Review Annotation（V1.1）

独立实现，不影响普通转换 pipeline。

## Phase 9 — regex 规则、SVG text、竖排标点、custom config（V1.1）

各自独立 test suite；regex 规则按 §11.5/§34 的安全要求。

## 已移出路线图

- Jieba：见 §4.4，V2 重新评估 native `opencc-jieba` 打包、签名与 regression 成本。

---

# 56. AI 实现约束

> 本节是 §98 不可妥协项的操作化展开；与 §98 冲突时以 §98 为准。

后续任何 AI Agent 接到本文实现时，必须遵守：

1. 不允许未经说明替换 backend；
2. 不允许自己实现简繁词典算法替代 OpenCC；
3. 不允许用 regex 作为 XHTML 主 parser；
4. 不允许先 write 再 preview；
5. 不允许修改 ID/path/class；
6. 不允许把地区词汇混进普通 s2t；
7. 不允许省略 tests；
8. 不允许以“后续补测试”为理由提交核心转换；
9. 不允许自动联网；
10. 不允许修改官方 OpenCC bundled dictionary；
11. 不允许用户规则无 direction；
12. 不允许 regex 规则默认开启；
13. 不允许 metadata 默认转换；
14. 不允许 force pivot 默认开启；
15. 不允许日志默认保存整段正文；
16. 不允许升级 OpenCC data 后直接刷新 expected outputs 而不 review diff；
17. 不允许把 OpenCC upstream golden test 改成迎合当前实现；
18. 不允许忽略 verifier 错误继续写入。

---

# 57. Definition of Done（分级）

模块分为两级，DoD 要求不同；一个 PR 涉及两级时按更严格的一级执行。

## 57.1 Tier A — 会改变 EPUB 内容或转换结果的代码

范围：`core/`、`document/`、`opencc_backend/`、`rules/engine.py`、`rules/precedence.py`、`transforms/`、`sigil/adapter.py` 的 commit 路径、`vendor/` 数据变更。

一个功能只有同时满足以下条件才算完成：

```text
Code
+ Unit Test
+ Integration Test（fake BookContainer）
+ Failure Test（§38 至少覆盖一种失败路径）
+ Golden / 结构不变量无回归
+ Logging（事件与 summary 字段）
+ Documentation（spec 章节号 + docs/）
+ Migration consideration（涉及持久化 schema 时）
```

## 57.2 Tier B — 不改变转换结果的代码

范围：`ui/`、`logging_ext/report.py`、导出格式、历史列表、Self-Test 展示、i18n 文案、`tools/`。

要求：

```text
Code
+ Unit Test（纯逻辑部分）
+ Smoke Test（可在无 GUI 环境下以 headless 方式执行的部分）
+ Documentation（用户可见变化写入 CHANGELOG）
```

Tier B 不得反向影响 Tier A：UI 代码不允许 import `opencc`，也不允许直接构造 `ConversionPlan`。

例如“增加 s2twp”（Tier A）不是：

```text
OpenCC("s2twp")
```

就算完成。

还必须：

- UI 有解释；
- HIGH risk 分类；
- preview 分类；
- report；
- golden；
-地区 corpus；
- history；
- profile serialization。

---

# 58. 第一版功能边界

V1.0 目标是**完整可用的专业版**，不是最小可用版；范围按 §55 的 M1–M4 交付。

## V1.0 必须（按里程碑）

**M1**

- 全部 16 个官方 config（含 `t2tw/t2hk/tw2t/hk2t` 地区互转，`t2jp/jp2t` 位于高级）；
- safe XHTML（§7，含 `<head><title>`、字符引用策略、`INLINE_BOUNDARY` 诊断）；
- NAV；
- selected / spine / all 三种范围；
- preview、diff、comparative config classification 与分类筛选；
- staging、verify、事务写入、Checkpoint 提示；
- JSONL 日志、session summary；
- canonical CLI golden、upstream official fixtures、ambiguity corpus 初版、EPUB fixture（EPUB2/EPUB3/ruby/footnote/script-style/entity）。

**M2**

- NCX；
- OPF 元数据白名单；
- lang（Legacy / BCP47 preset，三处一致）；
- 地区词汇 corpus（TW、HK）。

**M3**

- exact / protect 规则（锁定片段模型）；
- direction、global/profile/book scope；
- 冲突检测与 BLOCKING；
- TSV / CSV / JSON / OpenCC TXT 导入导出；
- Profile；
- Rule Test Sandbox；
- Dictionary Inspector（只读，展示 comparative config classification；不得伪造词典命中）。

**M4**

- 引号转换；
- 横排标准标点；
- 混合简繁诊断；
- force pivot（高级、HIGH）；
- 转换历史；
- Self-Test；
- Conversion Report（Markdown / JSON）。

## V1.1

- Review Annotation；
- regex rules（pre/post phase）；
- SVG text；
- MathML annotation 选项；
- 竖排兼容标点；
- custom config（专业模式）；
- `decode_numeric_cjk_refs`；
- selector scope 规则。

## V2 候选

- Jieba（§4.4 前置条件）；
- 跨行内标签整词（§7.6，需后端 segment 信息）；
- External Compare（§54）。

如果开发资源足够，V1.0 的四个里程碑可以连续完成；但代码仍必须按 §55 的 Phase 分提交，每个里程碑打 tag。

---

# 59. Release 前人工检查清单

```text
[ ] macOS Sigil 安装
[ ] Windows Sigil 安装
[ ] Linux Sigil 安装
[ ] EPUB2
[ ] EPUB3
[ ] 中文小说
[ ] 技术书
[ ] 台湾文本
[ ] 香港文本
[ ] 混合简繁
[ ] ruby
[ ] footnote
[ ] nav
[ ] script/style
[ ] MathML
[ ] SVG
[ ] custom rules
[ ] conflict
[ ] cancel
[ ] Checkpoint 提示出现，且用 Sigil Checkpoint 可完整回滚一次转换
[ ] report
[ ] logs
[ ] OpenCC version displayed
[ ] dictionary checksums
```

---

# 60. 推荐仓库说明

README 第一段应明确：

> OpenCCForSigil converts Chinese text in EPUB files opened in Sigil using a pinned OpenCC conversion pipeline. It is designed for publishing workflows: conversion is previewed before application, structural EPUB identifiers are protected, regional terminology is explicitly separated from character conversion, and every run can be audited through deterministic reports and versioned rule sets.

中文：

> OpenCCForSigil 是面向 EPUB 制作与校对的 Sigil 中文转换插件。插件基于锁定版本的 OpenCC 转换规则，在应用修改前提供完整预览，并保护 EPUB 的 ID、链接、样式和脚本结构；普通简繁、台湾/香港地区词汇转换严格区分，同时支持用户规则、版本记录、转换日志与可复现测试。

---

# 61. 数据与兼容策略总结

最终正确架构应是：

```text
                    ┌──────────────────────┐
                    │      Sigil UI        │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │     Controller       │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
       ┌──────▼──────┐  ┌─────▼──────┐  ┌─────▼─────┐
       │ Sigil Scope │  │ Rule Engine│  │ Profiles  │
       └──────┬──────┘  └─────┬──────┘  └───────────┘
              │                │
       ┌──────▼────────────────▼───────┐
       │       Document Processor      │
       │  XHTML/XML → Text Targets     │
       └──────────────┬────────────────┘
                      │
             ┌────────▼─────────┐
             │ Conversion Plan  │
             └────────┬─────────┘
                      │
             ┌────────▼─────────┐
             │ OpenCC Backend   │
             │ official Python │
             │ Binding + config│
             └────────┬─────────┘
                      │
             ┌────────▼─────────┐
             │ Diff + Preview   │
             └────────┬─────────┘
                      │ confirm
             ┌────────▼─────────┐
             │ Staging + Verify │
             └────────┬─────────┘
                      │
             ┌────────▼─────────┐
             │ bk.writefile()   │
             └────────┬─────────┘
                      │
         ┌────────────▼────────────┐
         │ Log / Report / History  │
         └─────────────────────────┘
```

这里唯一可以直接修改 EPUB 的层应是：

```text
Sigil Adapter / Commit stage
```

OpenCC backend、Rule Engine、Document Processor、Preview 都不得直接调用 `bk.writefile()`。

---

# 62. 关键技术结论

1. **不要 fork `epub_tool` 做基础。**
2. **不要继承 `epub_tool_rust` 自行模拟 OpenCC 的匹配器。**
3. **不要直接 fork `tradsimp` 再大规模删除 Calibre 代码。**
4. **参考 `tradsimp` 的文本节点、安全边界、用户词典、Jieba、地区模式与诊断思想。**
5. **核心重新设计为 Sigil-independent conversion core。**
6. **Sigil 仅作为 adapter。**
7. **使用 pinned BYVoid/OpenCC official Python Binding；它继续运行官方 C++ Core，但插件不自行绑定 C ABI、不使用 `ctypes`，也不实现 Python 重写算法。**
8. **普通简繁与地区词汇严格分开。**
9. **专业插件的核心卖点不是“转换”，而是“安全、可预览、可追溯、可复现”。**

---

# 63. 参考资料

## OpenCC

- https://github.com/BYVoid/OpenCC
- https://opencc.byvoid.com/
- https://github.com/BYVoid/OpenCC/blob/master/src/opencc.h
- https://github.com/BYVoid/OpenCC/blob/master/src/README.md
- https://github.com/BYVoid/OpenCC/tree/master/data/config
- https://github.com/BYVoid/OpenCC/tree/master/plugins/jieba

本文生产 backend 只基于 **BYVoid/OpenCC official Python Binding**（PyPI normalized distribution `opencc`）。OpenCC CLI 只作为 canonical golden/oracle invocation 与开发诊断工具，不作为普通 TextTarget 的 runtime 转换路径。

## tradsimp

- https://github.com/sheldonrrr/tradsimp

重点参考：

- `main.py`
- `resources/opencc_python/opencc.py`（只参考 config/分词思路，不作为 backend）
- `resources/user_dicts.py`
- `resources/bilingual.py`
- `resources/script_detect.py`
- `resources/jieba_loader.py`

## Sigil

- https://github.com/Sigil-Ebook/Sigil
- https://github.com/Sigil-Ebook/plugin-api-guide

重点 API：

- `BookContainer.readfile`
- `BookContainer.writefile`
- `BookContainer.text_iter`
- `BookContainer.spine_iter`
- `BookContainer.selected_iter`
- `BookContainer.getPrefs`
- `BookContainer.savePrefs`

# 64. 实施时的最终判断标准

如果后续实现出现两个方案，应按照以下问题选择：

> 哪个方案更容易证明“没有误改 EPUB 结构”？

然后：

> 哪个方案更接近 pinned OpenCC 官方行为？

然后：

> 哪个方案更容易通过 golden tests 与重复执行得到相同结果？

最后才考虑：

> 哪个代码更短、运行更快。

这应成为整个项目长期不变的技术决策顺序。


---

# 65. 运行状态机（实现必须遵守）

Controller 必须显式维护状态，不允许 UI 直接跨阶段调用。

```text
IDLE
  │
  ├── start
  ▼
SCANNING
  │
  ├── success
  ▼
ANALYZING
  │
  ├── success
  ▼
PLANNED
  │
  ├── show preview
  ▼
PREVIEWING
  │
  ├── cancel ───────────────→ CANCELLED
  │
  ├── confirm
  ▼
APPLYING_TO_STAGE
  │
  ├── success
  ▼
VERIFYING
  │
  ├── failure ──────────────→ FAILED
  │
  ├── success
  ▼
COMMITTING
  │
  ├── failure ──────────────→ FAILED
  │
  ├── success
  ▼
COMPLETED
```

约束：

- `PREVIEWING` 之前 `bk.writefile()` 调用次数必须为 0。
- `VERIFYING` 失败后 `COMMITTING` 不得执行。
- `FAILED` / `CANCELLED` 返回 Sigil 非成功状态，不允许部分提交。
- `COMPLETED` 才允许写入成功 history。
- 每一次状态切换都写一条 session event。

建议接口：

```python
class SessionState(Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    ANALYZING = "analyzing"
    PLANNED = "planned"
    PREVIEWING = "previewing"
    APPLYING_TO_STAGE = "applying_to_stage"
    VERIFYING = "verifying"
    COMMITTING = "committing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
```

不得使用散落的 boolean，例如：

```python
is_preview = True
did_apply = False
...
```

来代替完整状态机。

---

# 66. EPUB 文件修改白名单

普通转换模式下，插件只允许写入以下对象：

| 对象 | 默认 | 条件 |
|---|---:|---|
| XHTML | YES | 用户选中范围内 |
| EPUB3 NAV XHTML | YES | 默认勾选 |
| NCX | NO | 用户显式开启 |
| OPF metadata | NO | 用户显式开启 |
| CSS | NO | 仅 Review Annotation 可能插入受控 CSS |
| JS | NEVER | 禁止 |
| Image | NEVER | 禁止 |
| Font | NEVER | 禁止 |
| Audio/Video | NEVER | 禁止 |
| SMIL | NO | V1 不处理 |
| Encryption.xml | NEVER | 禁止 |
| container.xml | NEVER | 禁止 |

若实现模型发现“修改 CSS 更方便”，仍不得越过该白名单。

---

# 67. 属性修改白名单

默认可转换属性：

```text
title
alt
```

可选：

```text
aria-label
```

仅语言模式可修改：

```text
lang
xml:lang
```

除 Review Annotation 所需受控 class 外，禁止修改：

```text
id
class
href
src
srcset
style
name
content
property
rel
epub:type
role
data-*
aria-controls
aria-describedby
aria-labelledby
```

任何新增属性必须先加入本文白名单并增加 structural regression test。

---

# 68. Change 分类来源必须可解释

`rule_source` 不得只有 `OpenCC`，也不得伪造实际命中词典。

V1 允许：

```text
OpenCC:<selected config>   例：OpenCC:s2twp
OpenCC:diagnostic-normalization   # 只有受控 diagnostic config 明确证明时
UserRule:<uuid>
RegexRule:<uuid>
QuotationTransform
PunctuationTransform
LanguageTransform
PivotChain:<config>→<config>
```

对 OpenCC change，`rule_source` **始终记录真正用于生成最终 target 的 selected config**。例如用户执行 `s2twp`，即使比较结果把某 span 分类为 `variant`，仍然：

```text
rule_source = OpenCC:s2twp
```

而不是 `OpenCC:s2tw`。

V1 不拥有 dictionary-hit trace，`variant/regional` 只是通过多个官方 config 的输出做**比较配置差分**分类：

```json
"attribution_method": "comparative_config_diff"
```

它是 explanatory heuristic，不代表 OpenCC 内部真实 pipeline trace。

## 68.1 Comparison Configs

定义在 `opencc_backend/configs.py`，与 golden 一起冻结：

| selected config | comparison_configs（全部独立作用于同一原始 segment） |
|---|---|
| `s2t` | `s2t` |
| `s2tw` | `s2t`, `s2tw` |
| `s2twp` | `s2t`, `s2tw`, `s2twp` |
| `s2hk` | `s2t`, `s2hk` |
| `s2hkp` | `s2t`, `s2hk`, `s2hkp` |
| `t2s` | `t2s` |
| `tw2s` | `tw2t`, `tw2s` |
| `tw2sp` | `tw2t`, `tw2s`, `tw2sp` |
| `hk2s` | `hk2t`, `hk2s` |
| `hk2sp` | `hk2t`, `hk2s`, `hk2sp` |
| `t2tw`, `t2hk`, `tw2t`, `hk2t`, `t2jp`, `jp2t` | selected config only |

**禁止把上一 config 的 output 作为下一 config 的 input。** 每个 comparison config 都直接转换同一个原始 `seg`。

## 68.2 算法

1. `final = native.convert(seg, selected_config)`；它是唯一可以进入 Apply 的 target。
2. 对需要分类的 config，分别计算 `compare[c] = native.convert(seg, c)`；这些结果只用于诊断。
3. 使用确定性的字符级 alignment（`difflib.SequenceMatcher(autojunk=False)` 或等价、经 golden 固定的算法）对原文、final 与 comparison outputs 做 span 对齐。
4. 例 `s2twp`：
   - final span 与 `s2tw` 在相应位置存在稳定差异，而 `s2twp` 独有 → `regional`；
   - `s2tw` 相对 `s2t` 出现且 final 保留 → `variant`；
   - 已在 `s2t` 出现 → 长度 1 可记 `character`，否则 `phrase`。
5. alignment 不唯一、长度变化导致无法稳定投影、不同 comparison 给出冲突证据时：
   - 不得强行归类；
   - category 退化为 `phrase` 或 `opencc_change`；
   - `attribution_confidence = low`；
   - Preview MAY 标记 `REVIEW`。

## 68.3 日志字段

```json
{
  "rule_source": "OpenCC:s2twp",
  "attribution_method": "comparative_config_diff",
  "comparison_stage": "s2twp-vs-s2tw",
  "attribution_confidence": "high"
}
```

`comparison_stage` 是解释字段，不是规则来源。

## 68.4 成本与开关

- Preview 默认执行 comparative classification；
- 对超大书可缓存相同 TextTarget + config 的结果；
- Apply **永远使用 Plan 中已冻结的 final target**，不得为分类重新生成 target；
- 关闭详细分类只能减少诊断计算，不能改变 conversion output。

## 68.5 禁止

- 不得把 comparison config 当作真实 OpenCC 内部 layer；
- 不得输出 `OpenCC:TWPhrases` 等未经证实的词典名；
- 不得调用 OpenCC C++ internal/private symbols 或从 private implementation 推断 dictionary hit；
- 不得让分类逻辑参与生成最终转换结果。

# 69. Rule Snapshot

点击“扫描并预览”后必须冻结规则。

```python
@dataclass(frozen=True)
class RuleSnapshot:
    schema_version: int
    rules: tuple[Rule, ...]
    sha256: str
```

用户在 Preview 窗口打开期间修改 Rule Manager：

- 当前 Preview 不得自动变化；
- UI 应提示“规则已发生变化，需要重新扫描”；
- Apply 按钮应失效，要求重新 Plan。

防止 preview 与实际 apply 使用不同规则。

---

# 70. OpenCC Provenance Snapshot

同一 Session 必须冻结：

```python
@dataclass(frozen=True)
class BackendProvenance:
    backend_name: str                 # "BYVoid/OpenCC official Python Binding"
    opencc_version: str               # "1.4.2"
    python_implementation: str        # "CPython"
    python_version: str                # full provenance, e.g. "3.14.2"
    python_abi: str                    # "cp314"
    runtime_os: str                    # "macos"
    runtime_architecture: str          # "arm64"
    upstream_tag: str
    upstream_commit: str
    import_path_id: str                # manifest payload logical id，不记录用户绝对路径到公开报告
    wheel_filename: str
    wheel_sha256: str
    payload_sha256: str
    import_origin: str                 # selected payload-relative path
    data_manifest_sha256: str
    config_name: str
    config_sha256: str
    tofu_policy: str                  # "native_default_include"
```

Preview 后不得：

- 更换 selected Python Binding payload；
- 修改/热更新 config/dictionary；
- 切换 runtime/ABI artifact；
- 使用系统 OpenCC fallback。

`ConversionPlan` 保存 provenance hash；Apply 前再次验证。

# 71. 用户数据目录建议结构

```text
OpenCCForSigil/
├── preferences.json
├── profiles/
│   ├── default.json
│   └── *.json
├── rules/
│   ├── global.json
│   ├── profiles/
│   └── books/
├── logs/
│   └── 2026-09/
│       ├── <session>.jsonl
│       └── <session>.summary.json
├── history/
│   └── index.json
├── exports/
└── cache/
```

`cache/` 可安全删除。

`rules/`、`profiles/`、`history/` 不可作为 cache 清理。

所有 JSON 必须带：

```json
"schema_version": 1
```

未来 schema migration 由：

```text
storage/migrations/
```

管理；禁止发现旧格式后静默重置用户数据。

---

# 72. 配置迁移规则

读取配置顺序：

```text
load
→ detect schema version
→ migrate in memory
→ validate
→ backup old
→ write new
```

如果 migration 失败：

- 不覆盖原文件；
- UI 显示错误；
- 插件仍可在“无自定义规则的安全模式”启动，前提是用户明确确认；
- 日志记录。

---

# 73. 测试目录必须固定

建议最终测试树：

```text
tests/
├── unit/
│   ├── test_models.py
│   ├── test_rule_precedence.py
│   ├── test_rule_conflicts.py
│   ├── test_import_tsv.py
│   ├── test_import_csv.py
│   ├── test_import_json.py
│   ├── test_logging_schema.py
│   ├── test_storage_migration.py
│   └── test_profiles.py
│
├── opencc/
│   ├── test_upstream_golden.py
│   ├── test_all_configs_load.py
│   ├── test_backend_provenance.py
│   ├── test_data_checksum.py
│   └── test_determinism.py
│
├── ambiguity/
│   ├── s2t.json
│   ├── t2s.json
│   ├── s2tw.json
│   ├── s2twp.json
│   ├── s2hk.json
│   └── ...
│
├── document/
│   ├── test_visible_text.py
│   ├── test_attributes.py
│   ├── test_script_style.py
│   ├── test_entities.py
│   ├── test_comments.py
│   ├── test_ruby.py
│   ├── test_svg.py
│   ├── test_mathml.py
│   ├── test_nav.py
│   ├── test_ncx.py
│   └── test_structural_invariants.py
│
├── integration/
│   ├── test_plan_preview_apply.py
│   ├── test_cancel_no_write.py
│   ├── test_failure_no_commit.py
│   ├── test_selected_scope.py
│   ├── test_spine_scope.py
│   └── test_all_xhtml_scope.py
│
├── fixtures/
│   ├── epub2_minimal/
│   ├── epub3_minimal/
│   ├── complex_xhtml/
│   ├── ruby/
│   ├── svg_math/
│   ├── footnotes/
│   ├── mixed_script/
│   └── malformed/
│
└── performance/
    └── test_large_books.py
```

后续 AI 不得为了减少文件数量，把所有测试塞入 `test_plugin.py`。

---

# 74. Golden 文件格式

建议 ambiguity fixture：

```json
{
  "schema_version": 1,
  "oracle": {
    "backend": "BYVoid/OpenCC canonical CLI",
    "version": "1.4.2",
    "upstream_tag": "ver.1.4.2",
    "upstream_commit": "...",
    "config": "s2t",
    "tofu_policy": "native_default_include"
  },
  "cases": [
    {
      "id": "s2t-gan-001",
      "input": "干燥",
      "expected": "...",
      "category": "干/乾/幹",
      "source": "canonical-cli+manual-reviewed"
    }
  ]
}
```

expected 必须由 pinned canonical CLI 生成，再人工 review 后冻结；不得使用 plugin backend 当前输出刷新。

若 OpenCC 升级后 expected 改变，更新工具必须产生：

```text
old
new
upstream version/tag/commit
affected case ids
```

供 reviewer 审核。

# 75. Canonical CLI vs Plugin Official Python Binding Differential Test

release CI 必须执行：

```text
official `opencc` CLI built from pinned upstream source
vs
plugin `OpenCCBackend` using the selected official `opencc.OpenCC` payload
```

两侧必须使用：

- 同一 upstream tag/commit；
- 同一 config snapshot；
- 同一 dictionary snapshot；
- 同一 native default tofu policy。

覆盖：

- upstream/golden corpus；
- ambiguity；
- regional；
- 随机抽样；
- 长文本。

允许差异数量：

```text
0
```

如果出现差异，只允许分类为：

```text
BINDING_PACKAGE_MISMATCH
PACKAGE_DATA_MISMATCH
PLATFORM_WHEEL_DIVERGENCE
UPSTREAM_BUILD_DIVERGENCE
```

不得以 `EXPECTED_BACKEND_LIMITATION` 把 official Python Binding 与同源 CLI 的差异长期 xfail。

# 76. Fuzz / Property Test

对 XHTML processor 建议加入 property-based test。

随机生成：

- tags；
- nesting；
- attributes；
- 中文 text；
- entities；
- comments；
- script/style。

必须满足：

```text
protected attributes unchanged
parse before == parse after structurally
only allowed text targets changed
```

可使用 Hypothesis 作为 dev dependency；不得 vendor 到发布插件。

---

# 77. 文件位置标识策略

Preview 必须能稳定定位 Change。

推荐：

```text
book_href
+
DOM-like path
+
text-node ordinal
```

例如：

```text
Text/ch03.xhtml
/html/body/section[2]/p[4]/text()[1]
```

不要使用纯字符 offset 作为唯一位置，因为前面的规则替换可能改变长度。

---

# 78. Context 生成

Preview context 必须基于原始 TextTarget，而不是重新搜索全文。

```python
context_before = source[max(0, start-N):start]
context_after  = source[end:end+N]
```

若 source/target 长度不同，也不得靠 target 中全文搜索反推位置。

---

# 79. Apply 一致性检查

Apply 前重新读取 Sigil 文件并计算 source hash。

Plan 中保存：

```text
source_sha256
```

如果用户在 Preview 期间返回 Sigil 修改了书，导致 hash 不一致：

```text
禁止 Apply
提示：文件已变化，请重新扫描。
```

这是专业编辑工作流必须有的 optimistic concurrency guard。

---

# 80. Commit Manifest

应用前形成：

```json
{
  "session_id": "...",
  "files": [
    {
      "id": "...",
      "href": "...",
      "before_sha256": "...",
      "after_sha256": "...",
      "change_count": 123
    }
  ]
}
```

commit 后写入 summary log。

不保存完整 before/after 到 history，除非用户主动导出 full diff。

---

# 81. Cancel 行为

用户在任意阶段 Cancel：

### SCANNING / ANALYZING

立即停止，不写书。

### PREVIEW

关闭，无修改。

### APPLYING_TO_STAGE

停止 staging，不 commit。

### VERIFYING

停止并视为 cancel。

### COMMITTING

不得在单个文件写入中间允许普通 Cancel；commit 必须尽量作为短临界区一次完成。

---

# 82. Rule Test Sandbox

Rule Manager 的“测试”必须纯文本执行，不修改 EPUB。

输入：

```text
测试文本
```

输出显示：

```text
Original
After user pre-rules
After OpenCC
After post-rules
Final
```

并显示每一步命中规则。

这对专业用户非常重要。

---

# 83. Rule Conflict UI

冲突不只显示“有 2 个”。

必须展示：

```text
服务器
  global/s2twp → 伺服器
  profile/s2twp → 服務器
Winner: profile rule (priority 200)
```

如果同 scope + same priority + same source + different target：

```text
BLOCKING CONFLICT
```

禁止开始转换，直到用户解决。

---

# 84. Profile 与 Rules 分离

Profile 只保存“引用哪些 rulesets”，不复制规则正文。

这样修改术语库后多个 Profile 可以共享。

Plan 阶段展开并冻结 RuleSnapshot。

---

# 85. 默认内置规则

原则上不应维护大量“开发者个人纠错词库”。

内置规则仅允许：

1. OpenCC upstream；
2. EPUB 安全保护规则；
3. 明确的插件结构性规则。

对于“我认为 OpenCC 这里转错”，正确流程是：

```text
新增 regression
→ 验证 upstream
→ 优先向 OpenCC upstream 提 issue/PR
→ 在用户 overlay 中临时修正
```

不要形成不可审计的私有魔改词典。

---

# 86. Dictionary Inspector

专业模式 SHOULD 提供只读 Dictionary Inspector：

输入：

```text
软件
```

按 §68 的 comparison configs 独立展示，并显示锁定片段命中：

```text
Input:        软件
Config:       s2twp   (comparison: s2t / s2tw / s2twp; each runs on the same input)
User rules:   none matched
s2t:          軟件
s2tw:         軟件     (same as s2t for this input)
s2twp:        軟體     ← regional
Final:        軟體
Attribution:  OpenCC:s2twp / regional / comparative_config_diff
```

不显示词典文件名。若某 comparison config 的结果相同，直接标注结果相同；若差分对齐置信度低（§68.2 第 4 条），显示 `attribution_confidence: low`。禁止猜测。

---

# 87. 转换结果警告分类

```text
INFO
REVIEW
HIGH
BLOCKING
```

### INFO

普通字符映射。

### REVIEW

地区词汇、用户覆盖。

### HIGH

regex、pivot、metadata、SVG。

### BLOCKING

规则冲突、数据 checksum 错误、解析失败、source hash changed。

存在 BLOCKING 时 Apply 必须 disabled。

---

# 88. UI 可访问性

- 键盘可操作；
- Tab 顺序合理；
- 不仅靠颜色表达 HIGH/ERROR；
- dark/light 根据 `bk.colorMode()` 适配；
- UI 文本允许简体/繁体/英文；
- 路径、词条可以复制；
- 长 diff 支持横向滚动或 wrap；
- progress 不阻塞整个界面。

---

# 89. 国际化

资源：

```text
resources/i18n/
  en.json
  zh_CN.json
  zh_TW.json
```

用户规则数据不得被 UI 翻译。

Config ID 永远使用：

```text
s2twp
```

显示名称才本地化。

---

# 90. 线程规则

如果使用 worker thread：

- BookContainer API 调用集中在 controller/adapter；
- UI thread 只负责 UI；
- worker 不直接更新 Tk widget；
- 通过 queue/message 传递 progress；
- commit 阶段避免多线程写 BookContainer。

OpenCC converter 是否可跨线程共享必须根据当前 backend 保守处理；默认每 worker 独立实例。

---

# 91. 大书 Progress

进度阶段必须明确：

```text
扫描 12 / 120
分析 12 / 120
构建预览
验证 12 / 37
写入 12 / 37
```

不得用虚假的百分比模拟进度。

---

# 92. CLI Core Harness

虽然产品是 Sigil plugin，但开发仓库 SHOULD 提供测试用 CLI：

```text
python -m occs_cli convert input.xhtml --config s2twp
python -m occs_cli inspect "软件" --config s2twp
python -m occs_cli test
```

CLI 只用于：

- core 开发；
- CI；
- regression；
- debug。

它不能自己成为另一套逻辑。

Sigil 和 CLI 必须调用同一 core。

---

# 93. 每个 Phase 的退出条件

## Phase 0

```text
pytest unit storage/logging = PASS
plugin zip installs
run() returns success without modification
```

## Phase 1

```text
all selected OpenCC configs load
canonical CLI vs official Python Binding differential = 100%
all 16 official binding configs load = PASS
wheel/payload/data provenance checksum = PASS
```

## Phase 2

```text
document test suite = 100%
script/style/id/href safety = 100%
```

## Phase 3

```text
fake BookContainer integration = PASS
selected/spine/all scope = PASS
cancel = zero writes
```

## Phase 4

```text
plan → preview → apply identity = 100%
source hash guard = PASS
```

## Phase 5

```text
NCX/OPF whitelist fixtures = PASS
lang preset (legacy/bcp47) 三处一致性 = PASS
TW/HK/regional matrix = PASS
variant/regional 分类 = 与 comparison_configs + frozen classifier golden 一致
```

**M2 gate = Phase 0–5 全部 PASS。**

## Phase 6

```text
locked-span model: 11.8.2 三个样例 + 边界样例 = PASS
rule precedence/conflict/import/export = 100%
profile load/save/migrate = PASS
```

**M3 gate = Phase 0–6 全部 PASS。**

## Phase 7

```text
quote/punctuation transforms = PASS，且默认 keep 时零变化
mixed diagnostics = PASS
pivot chain logged = PASS
history/self-test/report = PASS
```

**M4 gate = Phase 0–7 全部 PASS → V1.0 release job（§97）。**

## Phase 8+

对应功能必须单独 test suite 通过后才能合并。

补充说明：Phase 1 的“all selected OpenCC configs load”在 1.2 版起指**全部 16 个** config；Phase 4 增加 `checkpoint notice shown = PASS`。

---

# 94. Pull Request 模板要求

每个 PR 必须回答：

```text
What changed?
Why?
Which spec section?
What files can now be modified?
Does conversion output change?
Does OpenCC data change?
Does rule precedence change?
Tests added?
Golden diff?
Backward compatibility?
```

若转换输出发生变化但没有 golden diff，CI 应失败。

---

# 95. 禁止的“快捷实现”

> 本节是 §98 的反例集合，用于 PR review；与 §98 冲突时以 §98 为准。

以下 PR 即使看起来能工作也应拒绝：

### A

```python
html = re.sub(...)
html = opencc.convert(html)
```

### B

直接调用 shell：

```text
opencc -c s2t.json
```

并要求用户系统先安装 OpenCC，作为唯一 backend。

### C

用户点击“转换”立即逐文件 write。

### D

把所有设置和逻辑写进 `plugin.py`。

### E

复制 `tradsimp/main.py` 后替换 Calibre API。

### F

把 `epub_tool_rust` 的两字典最长匹配移植过来。

### G

为了测试通过，直接把当前错误输出覆盖 golden expected。

### H

升级 OpenCC 后不记录 provenance。

---

# 96. AI Agent 单阶段工作模板

以后把本规范交给 AI 时，建议每次只下达：

```text
实现 Phase N。
严格遵守 OpenCCForSigil_Engineering_Spec.md。
不得实现 Phase N+1。
先阅读本阶段相关章节和已有代码。
修改前运行当前测试。
完成后运行本阶段全部测试与全量 regression。
如果规范与当前 Sigil/OpenCC API 冲突，写 docs/deviations.md，不得自行改变产品语义。
输出：
1. 修改文件
2. 架构决定
3. 测试结果
4. 未完成项
5. 是否存在 spec deviation
```

这样可以显著降低模型一次生成过多代码导致架构漂移的概率。

---

# 97. 最终发布闸门

正式 release job 必须按顺序：

```text
lint
→ unit
→ OpenCC golden
→ ambiguity
→ XHTML structural
→ integration
→ differential
→ package
→ unpack package
→ validate plugin.xml
→ verify vendor hashes
→ generate SBOM/third-party notice
→ release artifact
```

任何一步失败都不得产出正式 release。

---

# 98. 最终不可妥协项（唯一权威版本，同步维护于 `INVARIANTS.md`）

项目即使做到 V2/V3，以下原则不允许被“优化掉”：

1. **Preview before write**：`PREVIEWING` 之前 `bk.writefile()` 调用次数为 0。
2. **Official OpenCC Binding only**：生产转换只允许 pinned BYVoid/OpenCC official Python Binding；不得用 `opencc-py`、自写 Python 算法或系统 OpenCC fallback。
3. **OpenCC provenance**：upstream tag/commit、binding version、Python implementation/minor/ABI、OS/architecture、wheel/payload hash、data/config hash、tofu policy 一起冻结记录。
4. **Canonical golden compatibility**：官方 Python Binding output 与同源 pinned official CLI oracle 逐 Unicode code point 一致。
5. **Planned-span structural invariant**：只有 `ConversionPlan` 明确列出的 text/attribute span 可以变化；所有未计划 source slice 必须原样保持；id/href/src/class 等 protected semantics 不变。
6. **User rule direction**：无方向的规则不存在。
7. **Overlay，不魔改 upstream dictionary**：用户 exact/protect 规则以锁定片段实现，官方 config/dictionary snapshot 只读。
8. **Region conversion explicit**：`s2t` 永不偷偷地区化；`variant/regional` 只是 comparative classification，并明确标注 confidence。
9. **Logs + history**：每次运行有 session id、summary、JSONL；日志默认不含整段正文。
10. **Failure means no partial EPUB mutation**：任何 verify/backend/payload/hash 错误 → 返回非 0，Sigil 丢弃全部修改。
11. **Core/Sigil/UI separation**：只有 adapter commit stage 写书；UI 不持有 official converter object；backend 不 import UI/Sigil。
12. **Official public API only**：生产代码只能通过官方 `opencc.OpenCC` public API；不得绑定 C++ private symbol 获取词典命中，`rule_source` 不写未经证实的词典文件名。
13. **Verified payload selector**：只从 `vendor/opencc/manifest.json` 精确选择并 hash 验证 payload；禁止 runtime pip、网络、user site-packages、PATH/Homebrew/system fallback。
14. **Comparative attribution is not trace**：`comparative_config_diff` 只用于解释分类，不得声称是 OpenCC 内部真实 layer，也不得影响最终 target。

如果未来某个功能与这些原则冲突，应优先放弃该功能，而不是破坏这些边界。
