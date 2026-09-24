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
| **v0.1.1**（补丁版） | HEAD 已有的修复，包括 v0.1.0 Windows Jieba 数据错误（P-00）、第二轮 R-xx 修复；外加 `01-fix-spec.md` 批次 1 | 批次 1 完成；E-01、E-02 完成；第 4 节第 1-4 项在 macOS 和 Windows 上通过 |
| **v0.2.0** | 批次 2 至 6：转换正确性（词组拆分、命名空间、CDATA、保护规则、verifier）、大书性能、UI 体验；第一次同时发布平台包和 Fat 包 | 批次 1 至 6 完成；E-01 至 E-05 完成；第 4 节全部通过（macOS arm64、Windows x64、Linux x86_64） |
| **v1.0.0**（成熟版） | 不再加功能，只修 v0.2.0 实际使用中发现的问题 | 满足第 5 节的全部条件 |

**为什么先发 v0.1.1**：v0.1.0 的 Windows 包里 Jieba 数据是错的（走了文本回退路径，数据是 CRLF，见 `docs/reviews/2026-09-23/03-packaging-plan.md` 的 P-00）。HEAD 已经修好，但用户手里仍是有问题的版本。另外，批次 1 修的是"会卡死 / 会让整次转换作废"一类问题，不应该等到 v0.2.0。

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
| P-07 打包 job 与 5 平台冒烟 | 代码已完成 | **没有运行记录** → E-01 |
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

**为什么**：ARM64 job、打包 job、5 个平台的冒烟测试都只写了代码，还没运行过。

**步骤**：
1. 在 GitHub 的 Actions 页面，对 `main` 手动触发（workflow_dispatch）`.github/workflows/ci.yml`。
2. 逐项确认并记录：
   - `ubuntu-22.04-arm` runner 可用，job 通过；
   - Windows job 生成了 merged Jieba 数据，哈希与 `native_build/payload-lock.json` 的 `jieba_resources` 一致；
   - 5 个平台的包级冒烟全部通过；
   - 每个平台包和 Fat 包的实际大小（与 7 / 30 / 12 MB 上限比较）；
   - `SHA256SUMS` 生成且内容与产物一致。
3. 先把运行链接、测试 SHA、包大小和校验结果写在本节的运行记录中；E-02 获准后再复制到 `docs/releases/v0.1.1.md`。

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
- `tests/unit/test_release_assets.py` 约第 29、34、40 行写死了 `"0.1.0"`

**步骤**：
1. 在 `CHANGELOG.md` 顶部加 `## Unreleased`，按下面的分组列出 v0.1.0（b2f674b）之后的变更。用 `git log --oneline v0.1.0..HEAD` 逐条对照，每条一行，写用户能理解的描述，不要照抄提交信息：
   - **Fixed**：Windows Jieba 数据（P-00）、R-01 至 R-26 中用户可感知的修复、批次 1 各项。
   - **Changed**：平台包与 Fat 包、运行时子集、体积上限。
   - **Added**：Linux aarch64。
2. 发布时把 `## Unreleased` 改成 `## 0.1.1 - <日期>`。
3. 改四处版本号和测试里的版本号。**建议**把 `test_release_assets.py` 改成从 `version.py` 读取期望值，只断言四处一致，这样以后升版本不用改测试。
4. 复制 `docs/releases/TEMPLATE.md` 为 `docs/releases/v0.1.1.md` 并填写，包括 E-01 的运行链接和包大小。
5. 运行 `make check`。

---

### E-03 在 Sigil 里验收（P0，需要人来做）

按第 4 节执行，把结果填进第 4 节的表格，提交到仓库。

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

**为什么**：Linux 包的 native 模块是 cp314。官方包元数据显示，Ubuntu 22.04、Ubuntu 24.04、Debian 12、Fedora 45 和 Flathub Sigil 分别使用 Python 3.10、3.12、3.11、3.15 和 Flatpak 隔离运行时的 3.13；只有本次检查的 Arch Linux 包是 3.14。当前 Linux ZIP 不适用于大多数这些发行版 Sigil 包。

**步骤**：
1. 查 Ubuntu 22.04 / 24.04、Debian 12、Fedora 最新版、Arch、Flatpak（`com.sigil_ebook.Sigil`）上 Sigil 包的 Python 依赖版本，记录来源链接。
2. 写进 `docs/native-backend.md` 的新小节"Linux 上的 Python 版本"。
3. 因多数不是 3.14，已在 README 的下载表下注明"Linux ZIP 需要 CPython 3.14"，并记录来源。

---

### E-06 小的发布卫生问题（P2）

1. `native_build/verify_binary.py` 最后一行 `main()` 改成 `raise SystemExit(main())`。
2. `.github/workflows/ci.yml` 的 `name: CI and Fat Plugin build` 改成 `name: CI and plugin packages`（现在不止 Fat 包）。检查 README、`docs/release.md` 里是否引用了旧名字，一起改。
3. 在 `docs/release.md` 末尾加"发版步骤清单"，按顺序列出：跑 E-01 → 核对大小 → E-02 → 打 tag → 等 release job → 下载资产核对 SHA256SUMS → 更新 README 下载表。每一步写要运行的命令或要点击的页面。

---

### E-07 供应链加固（P3，可放到 v1.0.0 之后）

1. `ci.yml` 里所有 `uses: <action>@vN` 改成钉到 commit SHA，后面注释版本号（例如 `actions/checkout@<sha> # v7`）。
2. 考虑为 `SHA256SUMS` 生成签名（GitHub artifact attestation 或 minisign），并在 README 说明如何校验。
3. macOS 代码签名和公证：插件是 Python 加 `.so`，Sigil 加载时通常不需要。先在第 4 节确认 macOS 上有没有 Gatekeeper 提示，**没有提示就不做**。

---

## 4. Sigil 宿主验收（人工，E-03）

每个平台都要做。准备两本书：
- **小书**：3 至 5 章，含 ruby、表格、图片 alt、NCX；
- **大书**：约 100 万字、200 个文件（可以用 `docs/reviews/2026-09-24/scripts/perf/book.py` 生成内容后导入 Sigil）。

| # | 步骤 | 期望结果 | macOS arm64 | Windows x64 | Linux x86_64 |
| --- | --- | --- | --- | --- | --- |
| 1 | 安装平台包，打开小书，运行插件，选全部文件 → s2t → 预览 → 全部接受 → 应用 | 文件被转换；保存、关闭、重开后内容仍是转换后的 | | | |
| 2 | 同上，选单个文件 | 只改了这一个文件 | | | |
| 3 | 在预览里点"应用"之前，用任务管理器让磁盘只读或拔掉 U 盘（书在 U 盘上）；或者按 `01-fix-spec.md` A-04 的方式在代码里临时注入写失败 | 结果框文案与 Sigil 实际行为一致：书是否保持原样（用来确认 A-04 第 5 步的文案） | | | |
| 4 | 勾选 Jieba 运行一次；再次打开插件，取消 Jieba 勾选 | 第二次能取消勾选（B-01）；Windows 与 macOS 对同一段文字的 Jieba 结果相同（P-00） | | | |
| 5 | Sigil 切到深色主题后打开插件 | 插件窗口也是深色（C-02） | | | |
| 6 | 插件界面语言选简体中文，触发任意 `QMessageBox`（例如在规则窗口删除规则集） | 按钮文字是中文（C-02 / C-05） | | | |
| 7 | 转换设置对话框 | 按钮顺序是"上一步 … 取消 / 分析并预览"（C-06）；工具按钮只有一个下拉箭头（UI 审查 U17） | | | |
| 8 | 大书：全部文件 → s2twp → 预览，连续按 A 20 次 | 规划时间与第 6 节 D 的目标同级；每次按 A 没有可感知的卡顿（D-02） | | | |
| 9 | 在 macOS 上安装 Windows 平台包 | 显示"这个包不适用于当前平台"的提示（P-06），不是崩溃 | | | |
| 10 | 先装 Fat 包，再装平台包覆盖；反过来再做一次 | 两种顺序都能正常运行 | | | |
| 11 | 进度框显示时按 Esc、点关闭按钮 | 取消能生效，或者按钮已禁用；不会出现关不掉的窗口 | | | |
| 12 | 在 150% 缩放的 Windows 上打开预览窗口、规则窗口 | 窗口不超出屏幕（C-01、C-08） | | | |
| 13 | Windows on ARM（如有设备）：安装 Windows x64 包 | 能在模拟下运行（`03-packaging-plan.md` 第 7 节路线 A） | | | |

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
| 1 | NCX 里的 CDATA 要不要转换？现在正文 CDATA 不转换、NCX CDATA 转换（A-12） | 统一不转换 / 统一转换 / 保持现状 | 统一不转换（与正文一致，风险更低） |
| 2 | 非中文 `lang`（如 `lang="ja"`）内的文字是否跳过（A-11） | 默认跳过 / 默认转换但给诊断 / 保持现状 | 默认跳过；日文书里的汉字被转成繁体是数据损坏 |
| 3 | P-11 Fat 包共享平台无关数据 | 实施 / 不实施 | 平台包发布后再看 Fat 包下载量决定 |
| 4 | Windows ARM64 路线 B2（原生 ARM64 payload） | 实施 / 只支持 x64 模拟 | 先按第 4 节第 13 项确认模拟可用；可用就不做 B2 |
| 5 | 是否为 Linux 另建 `cp312` payload | 做 / 不做 | 做可支持 Ubuntu 24.04 官方 Sigil 包；仍无法覆盖 Jammy 3.10、Bookworm 3.11、Flathub 3.13 和 Fedora 45 的 3.15，需评估维护成本及其他 minor 的路线 |
| 6 | A-02 的合并规则会把"被单个相同字符隔开"的两处变更合成一条（例如"软件的内存"），用户不能只接受其中一处 | 接受这个粒度 / 改用更复杂的词组边界 | 接受；正确性优先于粒度 |
