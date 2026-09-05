# OpenCCForSigil — 不可妥协项（v1.4）

> 与主规范 §98 同步维护。任何 Phase 的实现任务都必须把本文件一并载入。与本文件冲突的功能应放弃，不得“优化掉”边界。

## Backend 与供应链

1. **Official Python Binding only** — Production Backend MUST be the pinned BYVoid/OpenCC official Python Binding distribution `opencc`; it MUST run the official OpenCC C++ Core.
2. **No custom converter** — 不得使用 `opencc-py`、纯 Python 重实现或自行实现简繁算法。
3. **No direct FFI production path** — OpenCCForSigil MUST NOT use `ctypes.CDLL`、手工 C ABI wrapper、`opencc_open`/`opencc_close`/`opencc_convert_utf8*`、系统 `libopencc` 或自行维护 shared-library loader 作为 Production Backend。
4. **No runtime installation** — Runtime MUST NOT invoke `pip`、`python -m pip`、系统 package manager、网络下载或联网更新依赖。
5. **Vendored payload only** — Runtime MUST load only a manifest-approved extracted official wheel payload shipped inside the plugin ZIP; it MUST NOT mutate that payload with Python bytecode caches.
6. **V1 Python compatibility** — 正式运行时只支持 CPython 3.14.x，wheel ABI 统一为 `cp314`；当前 Sigil bundled Python 3.14.2 是生产基准，3.14.7 仅为开发/CI 环境，且不得作为最低运行版本。
7. **Exact payload match** — Python implementation、major/minor、ABI、OS、architecture 必须与 manifest payload exact match；`cp314` 不等于 `cp313` 或 `cp315`；3.14.x 的 patch 版本不参与 payload 选择。
8. **Import origin** — `opencc.__file__` 或等效 module origin 必须位于当前选中的 vendored payload；user site-packages、Homebrew、Conda、pyenv、system Python 和 PATH 都不可作为 fallback。
9. **Provenance freeze** — Plan/Session 必须冻结 upstream tag/commit、binding version、Python full version（含 patch）、Python ABI、OS/architecture、wheel filename/hash、payload hash、config/data hash、tofu policy 与 import path id。
10. **Version coherence** — Python Binding、OpenCC Core、configs、dictionaries 必须来自同一 pinned release；不允许混用版本。
11. **Canonical differential** — official Python Binding 与同一 pinned upstream release 的 official CLI 对相同 input/config 必须逐 Unicode code point 一致；差异为 blocking error。
12. **Config reality** — V1 config allowlist 必须来自 pinned upstream 与 selected wheel 实际可用的 `opencc.CONFIGS`，不能只写在文档中。
13. **Tofu policy** — V1 固定官方 Python API 默认 `include_tofu_risk_dictionaries=True`，记录为 `native_default_include`，不提供 UI 开关。
14. **Official data read-only** — 官方 OpenCC configs/dictionaries 只读；用户规则只能作为 overlay。
15. **Official native Jieba only** — V1 可以提供高级 Jieba 选项，但仅当当前 manifest-approved payload 同时验证了同一 OpenCC upstream release 的官方 `opencc-jieba` native plugin、7 个官方 plugin configs、native library hash 与 Jieba resource hashes 时才可显示/使用；不得使用 Python Jieba、参考项目自写实现、`opencc-py`、system plugin 或静默 fallback。V1 不提供任意 segmentation dropdown；UI 只提供按标准 config 映射的可检测高级开关。

## EPUB 结构与事务

16. **Planned-span structural invariant** — 只有 `ConversionPlan.allowed_spans` 明确列出的 text/attribute span 可以变化；所有未计划 source slice 必须原样保留，UTF-8 bytes 因而 byte-identical；`id/href/src/class` 等 protected semantics 不变。
17. **Source-preserving mutation** — XHTML/NCX/OPF 使用 source-offset tokenizer + source slicing patch；`HTMLParser` 只能辅助事件/状态识别，不提供绝对 offset；不得全文 serializer 重建普通文件。
18. **Preview before write** — `PREVIEWING` 之前 `bk.writefile()` 调用次数必须为 0。
19. **Transaction boundary** — SCAN → ANALYZE → PLAN → PREVIEW → APPLY TO STAGE → VERIFY → COMMIT/WRITE → REPORT；staging、structural verifier、source SHA-256 guard 和 atomic commit 缺一不可。
20. **Failure is non-zero** — 任何 parse/backend/payload/hash/verify 错误或未捕获异常 → `run()` 返回非 0；不得部分提交 EPUB。
21. **Commit boundary** — 只有 Sigil adapter commit stage 可以调用 `bk.writefile()`；UI、core、document processor、backend 不得写书。

## Rules、地域、可审计性

22. **Directional rules** — 无 direction 的规则不存在；exact/protected/regex 必须经过 precedence、scope、snapshot 和 conflict validation。
23. **RuleSnapshot freeze** — Preview 后规则、profile、config、scope、options 或 provenance 改变必须使 Plan 失效并要求重新扫描。
24. **Regex safe default** — regex 默认关闭并标记高风险；不得通过 regex 绕过 planned-span 和 protected-content 约束。
25. **Regional explicitness** — `s2t` 不得偷偷地区化；`s2tw/s2twp` 与 `s2hk/s2hkp` 必须显式选择；`s2t` 不自动等同 `zh-TW`，通用繁体建议 `zh-Hant`。
26. **Comparative attribution is not trace** — `comparative_config_diff` 只用于结果分类；comparison configs 独立作用于同一原始 segment，不得串联，不得伪造 dictionary hit。
27. **Logs + history** — 每次运行有 session UUID、summary、persistent JSONL、history；默认日志不得保存整段正文，full diff 必须 opt-in。
28. **Report/self-test** — Conversion Report、Self-Test、golden、ambiguity/regional/structural/fuzz/property tests 和 CI 必须按规范执行；升级输出不得未经 review 自动刷新 expected。

## Official Python Binding backend 固定边界

```text
Sigil Plugin
    ↓
OpenCCForSigil Core
    ↓
OpenCCBackend abstraction
    ↓
RuntimeSelector → vendor/opencc/manifest.json
    ↓
exact vendored official `opencc` Python Binding payload
    ↓
official OpenCC C++ Core
```

`opencc.OpenCC(config).convert(text)` 是唯一最终转换值来源。UI、DocumentProcessor、Rules、Preview、Verifier 不得直接 import `opencc`；所有转换必须经过 `OpenCCBackend`。

## 禁止的快捷实现

- `re.sub(r"<[^>]+>", …)` 作为 XHTML/XML parser；
- `lxml parse → modify → serialize` 作为普通 XHTML、NCX 或 OPF 写回路径；
- 用户点击转换后逐文件立即 `writefile()`；
- 用户 exact/protect target 再送入 OpenCC 二次转换；
- 把用户词典直接叠加到官方 multi-stage config 并假设优先级永远有效；
- `import opencc` 在 runtime payload 选择前执行；
- `opencc-py`、系统 OpenCC、PATH CLI、runtime pip 或 network fallback；
- 把 payload 内官方 extension 拆成另一套 C ABI runtime；
- 把 comparison config 当作 OpenCC 真实内部 execution layer；
- 升级 OpenCC 后直接刷新 golden expected 而不 review diff；
- V1 UI 暴露任意 segmentation dropdown，或在缺少经过校验的官方 payload 时显示/启用 Jieba；官方 native `opencc-jieba` 高级开关必须 fail closed。
