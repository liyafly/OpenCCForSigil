# Official native `opencc-jieba` evaluation

Status: `BUILD-TIME VERIFIED` on macOS arm64 with OpenCC upstream `ver.1.4.2`
(commit `025f371dc76b598d77384fbdab90c937471844d8`). v1.4 exposes this
capability only as a manifest-detected advanced option; the production backend
is still the official Python Binding and the option remains fail-closed.

## What was verified

The upstream `plugins/jieba` component supplies a native segmentation plugin
and these plugin-backed configs in the 1.4.2 source tree:

```text
s2t_jieba
s2tw_jieba
s2twp_jieba
s2hk_jieba
s2hkp_jieba
tw2sp_jieba
hk2sp_jieba
```

The PyPI `opencc` 1.4.2 wheel used by the current production payload does not
contain that plugin, its Jieba configs, or its `jieba_merged.ocd2` resource.
The Python Binding has no public segmentation toggle; the plugin is selected by
the OpenCC config chain.

The official native plugin was built from the pinned upstream source against
the vendored wheel's official OpenCC static library, then placed beside the
wheel payload in an isolated temporary tree. The Python Binding loaded the
plugin without importing any alternative converter or using runtime pip/network
access:

```text
opencc.OpenCC("s2twp_jieba").convert("城堡的士兵已经出发")
→ 城堡的士兵已經出發

opencc.OpenCC("s2twp_jieba").convert("拥有一百年历史")
→ 擁有一百年歷史

opencc.OpenCC("tw2sp_jieba").convert("奶茶店慰藉著旅者的味蕾")
→ 奶茶店慰藉着旅者的味蕾
```

The corresponding standard `s2twp` cases produced `城堡計程車兵` and
`擁有一百年曆史`, demonstrating that Jieba can materially change phrase
selection. This is a segmentation effect from the official OpenCC plugin, not
a custom conversion algorithm.

The pinned upstream comparison corpus was also exercised through the isolated
Python Binding payload: 20 cases and 43 config assertions. With the V1
`include_tofu_risk_dictionaries=True` policy, the Python Binding and the
independently built official CLI matched on all 43 assertions. The corpus has
two review notes rather than silent fixes: its tofu case expects the CLI's
default skip-tofu behavior, while V1 deliberately enables that dictionary; and
one older standard `tw2sp` expected value says `慰借`, whereas both official
1.4.2 executables produce `慰藉`. That corpus value must be reviewed and
explicitly updated only as part of a visible golden-data change.

## Packaging finding

Building the plugin as a normal standalone OpenCC shared-library plugin also
worked, but its dynamic library required a separately discoverable shared
`libopencc` and did not load from the current Python wheel payload by itself.
That layout is not suitable for direct runtime reuse.

Building the official plugin against the same-release static `libopencc.a`
inside the vendored wheel produced a self-contained plugin with an
`@loader_path` runtime path on macOS. The future release pipeline therefore
must build and validate the official plugin per supported OS/architecture,
record its source/build provenance and hashes, and package the plugin configs,
native library, and Jieba dictionary resources together. It must not download
or compile anything at plugin runtime.

The payload manifest extension will also need to record at least:

- OpenCC upstream version/tag/commit and the wheel identity it was built against;
- plugin library filename, SHA-256, and native platform/architecture;
- every Jieba config and resource hash, including `jieba_merged.ocd2`;
- compiler/build profile and loader-path policy;
- OpenCC and cppjieba license/notice provenance.

## Current enablement gate

The checked-in macOS arm64 payload is enabled because its official native
library, configs, dictionary resources, manifest hashes, Python Binding smoke
tests, and official CLI differential corpus all pass. Windows, Linux, and
macOS x86_64 must each be built and tested by the GitHub Actions matrix before
their payloads can enter the Fat Plugin. A payload that has not passed its own
target-runner tests cannot expose `*_jieba` configs.

For the current user-facing workflow:

- use `tw2sp` for Taiwan Traditional → Simplified with Taiwan phrase conversion;
- use `s2twp` for Simplified → Taiwan Traditional with Taiwan phrase conversion;
- use `s2t`/`t2s` when only generic conversion is wanted.

The advanced option is a concrete config mapping, not a hidden global toggle;
for example `s2t` maps to `s2t_jieba`. This does not weaken the official Python
Binding, preview, source-span, transaction, or provenance invariants.

## Fat Plugin release gate

The GitHub release matrix must build the official upstream plugin against every
target payload and verify, in clean processes:

1. exact plugin/config/resource manifest selection;
2. native loader origin and integrity;
3. official Python Binding versus the matching official CLI at 100% equality;
4. the upstream Jieba comparison corpus and regional/EPUB structural suites;
5. artifact licenses, code-signing compatibility, and no runtime network/pip;
6. human review of all changed ambiguity and golden outputs.

Until then, an absent or unsupported Jieba payload is a feature boundary, not
a reason to fall back to `opencc-py`, system OpenCC, or a Python Jieba rewrite.
