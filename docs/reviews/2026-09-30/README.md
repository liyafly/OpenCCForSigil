# 2026-09-30 复核：2026-09-29 方案的落实情况，以及 v0.2.11 发布后的剩余工作

基线：`main` @ `3107f27`，版本 0.2.11。`v0.2.11` 标签和 GitHub Release 已于 2026-09-30 08:35（+08:00）发布。本轮只写了评审文档、复现脚本和证据，没有改动产品代码。

基线检查（`3107f27`）：
- `make check` 全部通过：Ruff 通过；pytest **861 passed、1 skipped**；vendor manifest、OpenCC 差分 28/28、Jieba 差分 10/10、插件元数据（0.2.11）都通过。
- 真实 Qt 验收 `check_ui_acceptance.py --verify --width 960 --height 640`：13/13 PASS。
- GitHub Actions 标签构建 [`36649657631`](https://github.com/liyafly/OpenCCForSigil/actions/runs/36649657631)：success。
- Sigil 宿主验收：**Not verified**。

本机：macOS 26.6，Apple M4 Pro。

**决定状态：** 2026-09-30，D16–D22 已由用户确认，全部按本文的推荐执行，见下文“已拍板的决定”。执行模型不需要再等待任何决定。下文“用户负责的事项”U1–U4 由用户本人完成，或由用户另行指派；执行模型不做。

## 结论

**总体符合预期，没有方向性偏移。** 2026-09-29 方案批准的 FIX-01 至 FIX-18（FIX-16 不做）和 SIMP-01 至 SIMP-30（SIMP-17 不做），产品代码都按规格落地了。
- 3 个 P1（FIX-01、02、03）都已修复。关键测试放到各自的父提交上跑，确认修复前会失败。
- 全局约束里最重要的几条都守住了：
  - `evidence/` 目录没有被改动；
  - 2026-09-28 的执行记录只在末尾追加；
  - `docs/deviations.md` 补了 5 条，spec 和 INVARIANTS 没动；
  - 标为“不做”的条目都没做；
  - 三份 i18n 的键集合一致，各 671 个。

**偏移集中在下面 3 类，详见 [01](01-acceptance-audit.md)：**

1. **产品：2 个 P2、2 个 P3 缺陷，现有测试都没覆盖。** 两个 P2 的根因都是 2026-09-29 规格本身写错了，执行模型是照规格做的。
   - FU-01（P2）：一条已有的 `*`（任意方向）规则，连续“更新”两次后会被静默改成 s2t。原因是 FIX-06 第 3 步要求在 `_update_selected()` 末尾重置方向框。
   - FU-02（P2）：把 `default` 重命名为 X 后再删除 X，删除操作抛出 `StopIteration`，窗口停在不一致的状态。SIMP-05 以为“删空后重建 default”这段代码走不到，但通过重命名是能走到的。
   - FU-03（P3）：数字字符引用（`&#x4E2D;`）里的零宽跳过不再产生诊断。原因是 FIX-09 漏做了第 2 步。
   - FU-04（P3）：规则测试输出里“最终结果”出现两次，两行的分隔符还不一样。SIMP-21 追加字段时多抄了这一行。
2. **验证工具：** 后续的 SIMP 提交弄坏了 8 个探针或脚本的入口，其中包括 FIX-12 刚修好的 UXS-02 探针，以及 FIX-10 用的预览基准。另有 7 处断言被删或被削弱，违反全局约束 13，其中几处提交说明也漏写了 D15。
3. **记录与发布：**
   - `04-implementation-results.md` 有 11 处与实测不符，例如列出的测试名不存在、“修复前失败”的测试其实修复前就能通过。
   - 批次中间真实 Qt 验收和 Ruff 都红过，没有遵守“上一批没过不进下一批”。
   - v0.2.11 的发布说明漏写了 12 项用户能看到的功能删除（SIMP-11 至 SIMP-30 中的 12 条），D9 和 SIMP-29 的行为变化也没写清楚；SIMP-29 还被写成“保留旧行为”，与事实不符。

**发布判断：**
- **v0.2.11 不需要撤回。** 所有自动门禁都是绿的，也没有会丢数据的问题。FU-01 和 FU-02 都要特定的操作顺序才会触发。
- **建议修完本方案后再发 0.2.12。** 发不发版、何时发由用户决定（U4）；本方案不改版本号。
- 发布说明要补（FU-05）。GitHub Release 页面由用户更新（D22、U2）。
- 仍然缺少在真实 Sigil 里的冒烟测试：安装、转换、预览并接受、保存规则、打开历史。

**待用户确认：** `3107f27 release: prepare v0.2.11` 不在 2026-09-29 的执行清单里，而 2026-09-28 全局约束第 6 条规定“不修改版本号，不打标签，不发布”。这次发布是否经过授权，由用户确认（U1）。执行模型不回退、不改动这次发布。

## 文档

| 文件 | 内容 |
| --- | --- |
| [01-acceptance-audit.md](01-acceptance-audit.md) | 2026-09-29 方案逐条验收（FIX 18 条、SIMP 32 条、计划外提交 3 个），以及自报与实际不符、过程问题、只记录不改的项 |
| [02-fixes.md](02-fixes.md) | 剩余工作 FU-01 至 FU-09，每条都可以直接执行 |
| `scripts/rules/` | FU-01 至 FU-04 的复现脚本 |
| `scripts/tools/check_entrypoints.sh` | FU-06：一次跑完 8 个坏掉的工具入口，每个输出一行状态 |
| `evidence/` | 在 `3107f27` 上跑这些脚本得到的输出，也就是修复前的状态。**不要覆盖** |

## 已拍板的决定（2026-09-30，用户确认，全部按推荐）

| 编号 | 问题 | 结论 | 执行条目 |
| --- | --- | --- | --- |
| D16 | FU-02 怎么修 | **恢复 SIMP-05 删掉的两行兜底**：删到一个不剩时，重建一个空的 `default`，也就是 0.2.10 的行为。不禁止重命名 `default`，因为那需要新文案和新行为 | FU-02 |
| D17 | SIMP-23 第 4 步（每条正则只编译一次）没做 | **本轮不做。** 每条正则现在编译 3 次，最多 128 条，开销可以忽略；在记录里如实写明 | FU-09 |
| D18 | SIMP-07 新增了 `LiteralPrefixIndex.single_char_buckets`，并重写了 `source_matches` 的循环，与“删掉没测出收益的快路径”的原意不符 | **保留。** 13,440 段模糊测试 0 处不一致，300 组独立参照全部一致，实测快 5–8%。记为偏离原意 | FU-09 |
| D19 | `746771f`、`6ff11aa` 两个计划外的性能提交 | **保留。** 两个都带修复前失败的测试，没有改阈值，随机对照 0 处不一致。在记录里补一节单独说明 | FU-09 |
| D20 | 2026-09-23 round2 的 `s1`、`s2`、`s3`、`s4`、`s6`、`l07_eq` 依赖的功能，已被 SIMP-01、03、16 删除 | **标为“已退役”，不改脚本。** 它们不在任何现行验收流程里 | FU-09 |
| D21 | SIMP-03 删掉旧引擎后，“backend 返回非字符串”的显式检查没有了。`test_non_string_backend_output_is_rejected` 现在靠 `core/diff.py:49` 的 `len(None)` 偶然通过 | **本轮不补。** 官方 backend 总是返回 `str`。在记录里写明 | FU-09 |
| D22 | 谁来更新 GitHub Release 页面、谁来做 Sigil 宿主验收 | **用户本人执行，或由用户另行指派。** 执行模型只改仓库里的 Markdown，不运行 `gh release edit`，也不打标签 | FU-05、U2、U3 |

## 用户负责的事项（执行模型不做）

这 4 项由用户本人完成，或由用户另行指派给其他 agent。执行模型只需在 `04-implementation-results.md` 末尾列出它们，并标为“待用户”。

| 编号 | 事项 | 做法 | 前置 |
| --- | --- | --- | --- |
| U1 | 确认 `3107f27` 的改版本号、打标签、发布是否经过授权 | 确认后，在 `04-implementation-results.md` 里把“待用户”改成结论（已授权 / 未授权）。无论结论如何，都不回退 `v0.2.11` | 无 |
| U2 | 更新 GitHub Release 页面正文 | `gh release edit v0.2.11 --notes-file docs/releases/v0.2.11.md` | FU-05 已合入 `main` |
| U3 | Sigil 宿主冒烟测试 | 在真实 Sigil 里安装发布页的 ZIP；用一本测试 EPUB 转换、预览并接受、保存一条规则、打开历史，然后保存并重新打开这本书。记录 Sigil 版本、操作系统版本和进程架构（`docs/releases/TEMPLATE.md` 的要求）。没做之前，一律写 `Not verified` | 最好在 FU-01 至 FU-04 合入之后，用新构建的包测 |
| U4 | 决定是否、何时发 0.2.12 | 改版本号、打标签、发布，都由用户执行，或由用户另行明确授权 | 批次 1–5 全部完成 |

## 执行顺序（给执行模型）

- 每条单独提交，提交主题用括号里的写法。
- 每批做完都要运行下文的“每批通用验证”，全部通过后才能进入下一批。**上一批没过，不要开始下一批。** 上一轮就是在这一点上出的问题。

| 批次 | 条目 | 依赖 | 建议提交主题 |
| --- | --- | --- | --- |
| 1 | FU-01 → FU-02 → FU-04 | 无。三条都改 `ui/rules_window.py`，按顺序做 | `fix: keep wildcard direction when updating a rule`；`fix: recreate default after deleting the last rule set`；`fix: list the rule test final result once` |
| 2 | FU-03 | 无 | `fix: report zero-width skips inside numeric references` |
| 3 | FU-06 → FU-07 | 批次 1、2 | `test: repair review tool entry points`；`test: restore weakened review checks` |
| 4 | FU-08 | 无 | `docs: align rule guide with the test page` |
| 5 | FU-05 → FU-09 | 批次 1–4 | `docs: complete v0.2.11 release notes`；`docs: record 2026-09-30 corrections` |

P2 条目：FU-01、FU-02、FU-05。其余为 P3。

## 全局约束（每一条都适用）

沿用 [2026-09-28 README](../2026-09-28/README.md#全局约束每一条都适用) 的第 1–8 条，以及 [2026-09-29 README](../2026-09-29/README.md#全局约束每一条都适用) 的第 9–14 条。特别提醒：
- 第 6 条：不修改版本号，不打标签，不发布。
- 第 11 条：每条修复先写一个会失败的测试。
- 第 13 条：D15 改写旧探针只允许两种改法，而且要在提交说明里写明。

另外补充 4 条：

15. **不要改签入的证据。** 本目录的 `evidence/` 以及前几轮的 `evidence/` 都不能改。修复后重跑脚本，输出写到 `/tmp/`，再与 `evidence/` 对照。
16. **提交说明必须写全，缺一不可：**
    - 产品修复（FU-01 至 FU-04）写“修复前失败的测试：<完整测试名>”，而且这个测试名必须真的存在于提交里。写之前用 `grep -n "def <测试名>" tests -r` 确认。
    - 工具修复（FU-06、FU-07）写“修复前的输出：见 `evidence/tools/check_entrypoints.out`”，或写 D15 改写说明。
17. **每批结束时，把两条验证命令的原始结论贴进本目录的 `04-implementation-results.md`（新建）。** 包括 passed/failed 数、`acceptance.json` 里的 FAIL 数，以及复现脚本修复后的输出。不能只写文字概括，也不能写“通过”却不贴数字。
18. **不要为了让测试通过而修改测试的期望值。** 如果照本文步骤做完，某个现有测试失败了，停下来，把失败输出写进 `04-implementation-results.md`，然后结束本批，不要自行放宽断言。

新增或修改的文案必须同时改 `plugin/OpenCCForSigil/resources/i18n/{en,zh-Hans,zh-Hant}.json` 三份，并遵守 2026-09-28 和 2026-09-29 的术语表。本方案没有新增 i18n 键。

## 每批通用验证

```sh
mise exec -- make check
QT_QPA_PLATFORM=offscreen mise exec -- uv run --with PySide6==6.11.2 python \
  docs/reviews/2026-09-27/ui-workflow/scripts/check_ui_acceptance.py --verify \
  --width 960 --height 640 --output /tmp/opencc-ui-acceptance
# 从批次 3 起再加这一条：
sh docs/reviews/2026-09-30/scripts/tools/check_entrypoints.sh
```

- 前两条命令都必须退出 0，第二条的 `acceptance.json` 里不能有 FAIL。
- 从批次 3 起，第三条输出的每一行都必须是 `exit=0`，行尾也不能带错误信息。
- 基线数字：`make check` 为 861 passed、1 skipped。本方案共新增 7 个测试函数（FU-01 一个、FU-02 两个、FU-03 一个、FU-04 一个、FU-08 两个），全部做完后应为 **868 passed、1 skipped**。

## 复现脚本用法

所有命令都在仓库根目录执行。脚本不写文件，也不读用户目录。

```sh
for s in fu01_wildcard_update fu02_rename_default_delete fu03_numeric_ref_zero_width fu04_rule_test_final_once; do
  echo "== $s"
  QT_QPA_PLATFORM=offscreen mise exec -- uv run python docs/reviews/2026-09-30/scripts/rules/$s.py
done
sh docs/reviews/2026-09-30/scripts/tools/check_entrypoints.sh
```

注意：退出码 0 只说明脚本跑完了，不说明问题已修复。每条 FU 的“验收标准”写明了应当看到的输出。

## 已复查、没有问题的部分（不必重复）

- **P1 修复：** FIX-01、02、03 的新测试都在各自的父提交上失败，在 HEAD 上通过。复现脚本（fake Qt 与真实 Qt）的输出符合验收标准。
- **FIX-17 的 oracle 修正是合理的，没有降低断言。** 旧 oracle 期望 exact 规则覆盖受保护的文字，这违反 A-08 的“两遍扫描、保护优先”（`docs/reviews/2026-09-24/01-fix-spec.md:382-409`）。按 A-08 独立写的 oracle 跑 3000 个种子，与生产代码 0 处差异。
- **`6ff11aa` 批量决定：** 150 个随机种子覆盖 5 种决定混合、各种筛选和范围。计数、可见缓存、撤销/重做全部一致；阈值 `accept_all_seconds < 1.0` 没有改。
- **`746771f`：** 3000 例随机对照中，快路径与通用路径的 BatchDecisionPlan 完全一致。
- **旧配置兼容：** 带别名字段、已删面板键、`zhTW`、`scope`、未知键的旧方案都能加载，不会崩溃，其他字段也不会丢；规则集的 `default_direction`/`default_scope` 读写时都会保留。
- **正则安全边界：** 单次 50 ms 超时仍然生效，`fix17_regex_timeout.py` 在 0.050 s 报错。`d8_regex_run_cap` 输出 `ok 120000`；D9 不再翻转。
- **修复方案已试做：** 本文 02 的产品修复和工具修复，都在 `3107f27` 的临时工作树里完整做过一遍。结果：
  - `make check` 865 passed、1 skipped。当时只加了 FU-01 至 FU-04 的 4 个测试函数；FU-02 的守卫测试是单独跑的，也通过了。加上 FU-08 的 2 个测试，全部做完应为 868。
  - 真实 Qt 验收 13/13 PASS。
  - `check_entrypoints.sh` 8 行全部 `exit=0`。
