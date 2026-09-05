# OpenCCForSigil — 不可妥协项（一页版，v1.2）

> 与主规范 §98 同步维护。任何 Phase 的实现任务都必须把本文件一并载入。与本文件冲突的功能应放弃，不得“优化掉”边界。

1. **Preview before write** — `PREVIEWING` 之前 `bk.writefile()` 调用次数必须为 0。
2. **Native OpenCC only** — 生产转换只允许 pinned `BYVoid/OpenCC` native library 的稳定 C ABI；不得用 pure-Python 重实现、PyPI Python extension、系统 OpenCC 或 PATH fallback。
3. **OpenCC provenance** — upstream tag/commit、platform triple、native library SHA-256、data/config hash、tofu policy 必须在 Plan/Session 中冻结并记录。
4. **Canonical golden compatibility** — plugin `NativeOpenCCBackend` 的 output 必须与同一 pinned upstream source/data 构建的官方 `opencc` CLI oracle 逐 Unicode code point 一致。
5. **Planned-span structural invariant** — 只有 `ConversionPlan` 明确列出的 text/attribute span 可以变化；所有未计划 source slice 必须原样保留；`id/href/src/class` 等 protected semantics 不变。
6. **User rule direction** — 无方向的规则不存在；规则只在明确 direction / `*` 下生效。
7. **Overlay，不魔改 upstream dictionary** — 用户 exact/protect 规则采用锁定片段模型；官方 config/dictionary snapshot 只读。
8. **Region conversion explicit** — `s2t` 不得偷偷做台湾/香港地区词汇本地化；`variant/regional` 只由 comparative config diff 做解释性分类。
9. **Logs + history** — 每次运行必须有 session id、summary、JSONL；默认日志不得保存整段正文。
10. **Failure means no partial EPUB mutation** — 任何 parse/verify/native/FFI/hash 错误或未捕获异常 → `run()` 返回非 0，由 Sigil 丢弃整次修改。
11. **Core / Sigil / UI separation** — 只有 adapter commit stage 调用 `bk.writefile()`；UI 不持有 native handle；backend 不 import UI/Sigil。
12. **只用 OpenCC 稳定 C ABI** — 只绑定 `opencc.h` 公开 C ABI；不得绑定 C++ private/internal symbol 获取 segment/dictionary hit；`rule_source` 不写未经证实的词典文件名。
13. **Verified native loader** — 只能从 `vendor/MANIFEST.json` 指定的绝对路径加载当前平台 library；先 SHA-256 验证，再 `ctypes.CDLL`；禁止 `ctypes.util.find_library()`、Homebrew/MacPorts/Conda/system fallback。
14. **Comparative attribution is not trace** — `comparative_config_diff` 只用于 Preview/日志分类；所有 comparison config 都独立作用于同一原始 segment，不得串联；分类不得参与生成最终 target。

## Native backend 固定边界

```text
Python / core
    ↓
NativeOpenCCBackend
    ↓
ctypes stable C ABI
    ↓
pinned bundled libopencc
    ↓
pinned bundled official config + .ocd2
```

**唯一最终转换值：**

```text
native.convert(original_unlocked_segment, selected_config)
```

Comparison configs、diff、Dictionary Inspector、分类标签都不得改变这个值。

## XHTML/XML 写回固定边界

```text
parse / tokenize
→ absolute source spans
→ ConversionPlan.allowed_spans
→ source slicing patch
→ lxml verify only
```

`HTMLParser` MAY 用于事件/状态识别，但它本身不提供绝对 `[start,end)`；实现必须自己维护 source-position mapping。不得通过 serializer 重新生成普通 XHTML/NCX/OPF 内容。

## 禁止的快捷实现

- `re.sub(r"<[^>]+>", …)` 作为 XHTML/XML parser。
- `lxml parse → modify → serialize` 作为普通 XHTML、NCX 或 OPF metadata 写回路径。
- 用户点击转换后逐文件立即 `writefile()`。
- 用户 exact/protect target 再送入 OpenCC 二次转换。
- 把用户词典直接叠加到官方 multi-stage config 并假设优先级永远有效。
- `import opencc` / `opencc-py` / 系统 `opencc` 作为 production backend。
- `ctypes.util.find_library("opencc")`。
- bundled native hash 不匹配后 fallback 到系统 library。
- 为了归因绑定 OpenCC C++ internal/private symbol。
- 把 comparison config 当作 OpenCC 真实内部执行 layer。
- 升级 OpenCC 后直接刷新 golden expected 而不 review diff。
- V1 UI 暴露 Jieba/分词策略下拉；Jieba 不属于 V1.x。
