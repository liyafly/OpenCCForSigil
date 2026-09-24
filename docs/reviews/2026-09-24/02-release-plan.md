# 第三轮审查：发布计划与"成熟版本"验收标准

日期：2026-09-24。基线：`main` @ `4706a92`。

这份文档回答三个问题：
- 发什么版本；
- 每个版本发布前必须完成什么（E-xx 条目，写法与 `01-fix-spec.md` 相同）；
- 在 Sigil 里怎么验收（第 4 节，需要人来做）。

执行规则同 `01-fix-spec.md` 第 1 节。

---

## 1. 版本路线

| 版本 | 内容 | 前提 |
| --- | --- | --- |
| **v0.1.1**（原补丁路线） | v0.1.0 Windows Jieba 数据修复、第二轮修复和批次 1 | 本次按用户授权改为一次完成批次 1 至 9，跳过单独 v0.1.1 |
| **v0.2.0** | `01-fix-spec.md` 批次 1 至 9，Linux x86_64/cp312 平台包，以及发布流水线修复 | 自动化检查、完整发布 CI、版本记录、tag 与 Release 全部通过；本次真实 Sigil 宿主验收按用户授权跳过，并标为未测 |
| **v1.0.0**（成熟版） | 不再加功能，只修 v0.2.0 实际使用中发现的问题 | 满足第 5 节的全部条件 |

原方案先发 v0.1.1，是为了尽早修复 v0.1.0 Windows Jieba 数据问题和批次 1。用户现已授权把全部批次合并到一次 v0.2.0 发布；真实 Sigil 宿主验收不作为本次发布前置条件，发布说明必须明确标注未测。

---

## 2. 打包方案（P-00 至 P-08）当前状态

对照 `docs/reviews/2026-09-23/03-packaging-plan.md`，本机逐项核对过：

| 条目 | 状态 | 缺口 |
| --- | --- | --- |
| P-00 Windows Jieba 构建修复 | 已完成 | 缺跨平台 Jieba 逐条输出一致的 CI 断言 → E-04 |
| P-01 运行时子集 | 已完成 | — |
| P-02 体积上限 7 / 30 / 12 MB | 已完成 | — |
| P-03 linux-aarch64 身份 | 已完成 | — |
| P-04 CI 的 ARM64 job | 代码已完成 | **从未运行过** → E-01 |
| P-05 `--flavor` / `--runtime` | 已完成 | — |
| P-06 装错平台包的提示 | 已完成 | 需宿主实测（第 4 节第 9 项） |
| P-07 打包 job 与六个 runtime 冒烟 | 代码已完成 | v0.2.0 候选运行记录待 E-01 |
| P-08 发布前检查、资产、说明模板 | 已完成 | — |

本机结果：
- `mise exec -- ruff check .`：通过。注意 `.venv` 里没有 ruff，必须用 `mise exec --`。
- `build_plugin.py --check`：通过。
- macOS arm64 平台包：5,413,624 字节，两次构建 sha256 相同。
- `validate_artifact.py`：通过。
- `package_smoke.py`：23/23 通过。
- `differential_test.py`：28/28 一致；`differential_jieba_test.py`：10/10 一致。

---

## 3. 发布条目（E）

### E-01 在 CI 上完整跑一次打包流水线（P0，需要仓库所有者操作）

**为什么**：ARM64 job、cp312 job、打包 job 和六个 runtime 的冒烟测试需要在当前发布候选提交上完整运行。

**步骤**：
1. 在 GitHub 的 Actions 页面，对 `main` 手动触发（workflow_dispatch）`.github/workflows/ci.yml`。
2. 逐项确认并记录：
   - `ubuntu-22.04-arm` runner 可用，job 通过；
   - Windows job 生成了 merged Jieba 数据，哈希与 `native_build/payload-lock.json` 的 `jieba_resources` 一致；
   - 六个 runtime 的包级冒烟全部通过；
   - 每个平台包和 Fat 包的实际大小（与 7 / 30 / 12 MB 上限比较）；
   - `SHA256SUMS` 生成且内容与产物一致。
3. 当前 v0.1.0 的历史记录保留在下方。完成 E-02 和流水线修复后，对最终 v0.2.0 候选 SHA 重新运行，并把链接、SHA、包大小与校验结果记录在新小节。

**本次 E-01 运行结果（2026-09-24）**：
- [手动运行 #35996603837](https://github.com/liyafly/OpenCCForSigil/actions/runs/35996603837)（`workflow_dispatch`，`main`，SHA `600d9035e159a7ff2f0cc814869b7761126a0fad`）：5 个平台 payload、跨平台 Jieba 输出比较、包构建与校验、5 个平台包冒烟全部通过。
- Windows payload job 命中 target-tested payload 缓存，没有在这次运行中重新编译；job 的 `verify_vendor.py` 完整性校验通过，官方 Jieba CLI/Python Binding 差分 10/10 通过；跨平台输出比较通过。包构建阶段再次校验合并后的所有平台 payload。
- 下载本次 run 的 `OpenCCForSigil-packages-600d9035e159a7ff2f0cc814869b7761126a0fad` artifact。`tools/release_assets.py --version 0.1.0` 验证 7 个发布资产（6 个 ZIP 与 `SHA256SUMS.txt`）；`sha256sum -c SHA256SUMS.txt` 中 6 个 ZIP 均为 `OK`。
- ZIP 实际大小（十进制 MB）：

  | 资产 | 字节 | MB | 预算结果 |
  | --- | ---: | ---: | --- |
  | `OpenCCForSigil_0.1.0_linux-aarch64.zip` | 5,800,462 | 5.80 | 平台包 ≤ 7 MB，通过 |
  | `OpenCCForSigil_0.1.0_linux-x86_64.zip` | 5,851,890 | 5.85 | 平台包 ≤ 7 MB，通过 |
  | `OpenCCForSigil_0.1.0_macos-arm64.zip` | 5,426,017 | 5.43 | 平台包 ≤ 7 MB，通过 |
  | `OpenCCForSigil_0.1.0_macos-x86_64.zip` | 5,473,616 | 5.47 | 平台包 ≤ 7 MB，通过 |
  | `OpenCCForSigil_0.1.0_windows-x86_64.zip` | 5,573,003 | 5.57 | 平台包 ≤ 7 MB，通过 |
  | `OpenCCForSigil_0.1.0.zip` | 27,273,373 | 27.27 | 第一阶段 Fat 包 ≤ 30 MB，通过；第三阶段 ≤ 12 MB 目标尚未达到 |

**失败时**：记录失败的 job 名称和日志片段，作为新条目加到这份文档第 3 节末尾，不要为了让 CI 通过而放宽检查。

---

### E-02 升版本号、补 CHANGELOG 和发布说明（P0）

**位置**：版本号在四个地方，外加一个写死版本的测试：
- `plugin/OpenCCForSigil/plugin.xml`（`<version>`）
- `plugin/OpenCCForSigil/app/version.py`（`PLUGIN_VERSION`）
- `pyproject.toml`（`[project] version`）
- `uv.lock`（`opencc-for-sigil` 包的 `version`，用 `mise exec -- uv lock` 重新生成，不要手改）
- `tests/unit/test_release_assets.py` 从 `app.version.PLUGIN_VERSION` 读取期望值，并核对插件 XML、项目元数据和 lockfile 一致

**本次目标**：按用户授权将批次 1 至 9 与 Linux x86_64/cp312 包合并为 v0.2.0。v0.1.0 之后的变更需逐项阅读并用面向用户的内容归纳到 `CHANGELOG.md`；不得把尚未完成的宿主验收描述为通过。

**步骤**：
1. 将 `plugin.xml`、`app/version.py`、`pyproject.toml`、`uv.lock` 一致升至 `0.2.0`；测试从 `version.py` 读取当前期望值。
2. 将 CHANGELOG 的 Unreleased 内容整理为 `0.2.0 - <日期>`，覆盖已完成的修复、转换行为、界面与性能优化和 Linux cp312 支持。
3. 填写 `docs/releases/v0.2.0.md`：列出七个 ZIP 与校验清单、自动化验证记录，并明确所有真实 Sigil 宿主验收为“未测”。
4. 执行 `make check`，再在修复流水线后对最终候选 SHA 执行 E-01。

---

### E-03 在 Sigil 里验收（P0，需要人来做）

该项需要在真实 Sigil 宿主内人工操作。本次按用户明确授权跳过；第 4 节所有宿主格均标记为“未测”。自动化、发布 CI、attestation 和 package smoke 结果不得改写为宿主验收通过。

---

### E-04 跨平台 Jieba 输出一致性的 CI 断言（P1）

**为什么**：P-00 的根本问题是 Windows 上的 Jieba 数据和其他平台不同，但没有任何检查能发现。现在 `tools/differential_jieba_test.py` 只在同一平台内比较插件与官方 CLI。

**步骤**：
1. 给 `tools/differential_jieba_test.py` 加参数 `--output-json PATH`：把每条语料的 `(config, input, output)` 写成 JSON 数组，按输入排序。
2. 在 `ci.yml` 里，每个构建 native payload 的 job 运行一次，把 JSON 作为 artifact 上传，名称带平台。
3. 新增一个 job `jieba-consistency`，依赖所有平台 job，下载全部 JSON，逐条比较。有任何不同就失败，并打印第一处不同的平台、配置、输入和两个输出。
4. `tests/unit/` 加一个针对比较脚本的单元测试：两个相同的 JSON 通过，改一个字就失败。

---

### E-05 确认 Linux 上 Sigil 使用的 Python 版本（P1，调研）

**为什么**：Linux 包需要匹配运行 Sigil 插件的 CPython ABI。官方包元数据显示，Ubuntu 22.04、Ubuntu 24.04、Debian 12、Fedora 45 和 Flathub Sigil 分别使用 Python 3.10、3.12、3.11、3.15 和 Flatpak 隔离运行时的 3.13；只有本次检查的 Arch Linux 包是 3.14。Ubuntu 24.04 可由单独的 cp312 载荷覆盖。

**步骤**：
1. 查 Ubuntu 22.04 / 24.04、Debian 12、Fedora 最新版、Arch、Flatpak（`com.sigil_ebook.Sigil`）上 Sigil 包的 Python 依赖版本，记录来源链接。
2. 写进 `docs/native-backend.md` 的新小节"Linux 上的 Python 版本"。
3. 已在 README 下载表区分 cp314 载荷与单独的 Linux x86_64/cp312 包，并记录来源。

**实施结果**：已锁定官方 PyPI CPython 3.12 Linux x86_64 wheel，并加入独立构建、跨载荷 Jieba 一致性、发布资产和 CPython 3.12 package smoke。该自动化结果不等于真实 Sigil 宿主验收。

---

### E-06 小的发布卫生问题（P2）

1. `native_build/verify_binary.py` 最后一行 `main()` 改成 `raise SystemExit(main())`。
2. `.github/workflows/ci.yml` 的 `name: CI and Fat Plugin build` 改成 `name: CI and plugin packages`（现在不止 Fat 包）。检查 README、`docs/release.md` 里是否引用了旧名字，一起改。
3. 在 `docs/release.md` 末尾加"发版步骤清单"，按顺序列出：跑 E-01 → 核对大小 → E-02 → 打 tag → 等 release job → 下载资产核对 SHA256SUMS → 更新 README 下载表。每一步写要运行的命令或要点击的页面。

---

### E-07 供应链加固（P3）

1. 已授权并纳入 v0.2.0：将 `ci.yml` 每个 `uses:` action 固定到已解析的 commit SHA，并保留上游版本注释。
2. 已授权并纳入 v0.2.0：用 GitHub artifact attestations 为七个 ZIP 和 `SHA256SUMS.txt` 生成来源证明；README 与发布流程记录 `gh attestation verify` 用法。
3. macOS 代码签名和公证依赖真实 Sigil/Gatekeeper 验收。本次按用户授权跳过宿主验收，因此不做签名决策；该项继续待测，不能推断无需签名。

---

## 4. Sigil 宿主验收（人工，E-03）

每个平台都要做。准备两本书：
- **小书**：3 至 5 章，含 ruby、表格、图片 alt、NCX；
- **大书**：约 100 万字、200 个文件（可以用 `docs/reviews/2026-09-24/scripts/perf/book.py` 生成内容后导入 Sigil）。

| # | 步骤 | 期望结果 | macOS arm64 | Windows x64 | Linux x86_64 |
| --- | --- | --- | --- | --- | --- |
| 1 | 安装平台包，打开小书，运行插件，选全部文件 → s2t → 预览 → 全部接受 → 应用 | 文件被转换；保存、关闭、重开后内容仍是转换后的 | 未测 | 未测 | 未测 |
| 2 | 同上，选单个文件 | 只改了这一个文件 | 未测 | 未测 | 未测 |
| 3 | 在预览里点"应用"之前，用任务管理器让磁盘只读或拔掉 U 盘（书在 U 盘上）；或者按 `01-fix-spec.md` A-04 的方式在代码里临时注入写失败 | 结果框文案与 Sigil 实际行为一致：书是否保持原样（用来确认 A-04 第 5 步的文案） | 未测 | 未测 | 未测 |
| 4 | 勾选 Jieba 运行一次；再次打开插件，取消 Jieba 勾选 | 第二次能取消勾选（B-01）；Windows 与 macOS 对同一段文字的 Jieba 结果相同（P-00） | 未测 | 未测 | 未测 |
| 5 | Sigil 切到深色主题后打开插件 | 插件窗口也是深色（C-02） | 未测 | 未测 | 未测 |
| 6 | 插件界面语言选简体中文，触发任意 `QMessageBox`（例如在规则窗口删除规则集） | 按钮文字是中文（C-02 / C-05） | 未测 | 未测 | 未测 |
| 7 | 转换设置对话框 | 按钮顺序是"上一步 … 取消 / 分析并预览"（C-06）；工具按钮只有一个下拉箭头（UI 审查 U17） | 未测 | 未测 | 未测 |
| 8 | 大书：全部文件 → s2twp → 预览，连续按 A 20 次 | 规划时间与第 6 节 D 的目标同级；每次按 A 没有可感知的卡顿（D-02） | 未测 | 未测 | 未测 |
| 9 | 在 macOS 上安装 Windows 平台包 | 显示"这个包不适用于当前平台"的提示（P-06），不是崩溃 | 未测 | 未测 | 未测 |
| 10 | 先装 Fat 包，再装平台包覆盖；反过来再做一次 | 两种顺序都能正常运行 | 未测 | 未测 | 未测 |
| 11 | 进度框显示时按 Esc、点关闭按钮 | 取消能生效，或者按钮已禁用；不会出现关不掉的窗口 | 未测 | 未测 | 未测 |
| 12 | 在 150% 缩放的 Windows 上打开预览窗口、规则窗口 | 窗口不超出屏幕（C-01、C-08） | 未测 | 未测 | 未测 |
| 13 | Windows on ARM（如有设备）：安装 Windows x64 包 | 能在模拟下运行（`03-packaging-plan.md` 第 7 节路线 A） | 未测 | 未测 | 未测 |

每一格填"通过"、"失败：<现象>"或"未测"。失败项作为新条目加到 `01-fix-spec.md`。

---

## 5. "成熟版本"（v1.0.0）的判定条件

全部满足才能发 v1.0.0：

1. `01-fix-spec.md` 中所有 **P0、P1** 条目已完成，或者作者书面决定"不修"并写明原因。
2. P2 条目完成 80% 以上，剩下的都有明确的后续计划。
3. 第 4 节在 macOS arm64、Windows x64、Linux x86_64 三个平台上全部通过。
4. E-01 的 CI 流水线在 `main` 上连续 3 次全绿，E-04 的跨平台一致性检查通过。
5. 大书（100 万字）规划 ≤ 6 s（s2twp，UI 默认选项），预览单击 ≤ 30 ms，峰值内存 ≤ 800 MB。
6. v0.2.0 发布后至少两周内，没有新的"会丢改动 / 写错内容 / 卡死"类问题报告。
7. README 和 `docs/` 中的说明与实际行为一致：安装、平台包选择、Jieba、规则、方案、隐私、日志位置。

---

## 6. 需要作者决定的问题

| # | 问题 | 选项 | 建议 |
| --- | --- | --- | --- |
| 1 | NCX 里的 CDATA 要不要转换？现在正文 CDATA 不转换、NCX CDATA 转换（A-12） | 统一不转换 / 统一转换 / 保持现状 | 已采纳统一不转换，与正文一致 |
| 2 | 非中文 `lang`（如 `lang="ja"`）内的文字是否跳过（A-11） | 默认跳过 / 默认转换但给诊断 / 保持现状 | 默认跳过；日文书里的汉字被转成繁体是数据损坏 |
| 3 | P-11 Fat 包共享平台无关数据 | 实施 / 不实施 | 平台包发布后再看 Fat 包下载量决定 |
| 4 | Windows ARM64 路线 B2（原生 ARM64 payload） | 实施 / 只支持 x64 模拟 | 先按第 4 节第 13 项确认模拟可用；可用就不做 B2 |
| 5 | 是否为 Linux 另建 `cp312` payload | 做 / 不做 | 已采纳：单独发布 Linux x86_64/cp312 平台包，Fat 包保持五个 cp314 载荷 |
| 6 | A-02 的合并规则会把"被单个相同字符隔开"的两处变更合成一条（例如"软件的内存"），用户不能只接受其中一处 | 接受这个粒度 / 改用更复杂的词组边界 | 接受；正确性优先于粒度 |

本次按用户指示跳过 P-11 包体积优化。现有平台包与 Fat 包大小预算及发布资产体积检查继续执行。
