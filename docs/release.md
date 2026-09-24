# Release and artifact validation

Release packaging is split into two steps:

1. build and verify exact official OpenCC wheel payloads;
2. validate and package the shared Python plugin and manifest.

The exact official wheel inputs are recorded in
[`native_build/payload-lock.json`](../native_build/payload-lock.json). The lock
contains one CPython 3.14/cp314 wheel for each supported runtime and is checked
against the live PyPI metadata before extraction. A changed wheel URL, size, or
SHA-256 is a blocking error; the build never silently selects another release.

`tools/vendor_opencc.py` performs step 1. `tools/build_plugin.py` performs step
2 and invokes manifest/payload verification before packaging. It validates
`plugin.xml`, the code version, and the one-top-level-directory ZIP shape. No
unverified wheel payload is synthesized or copied.

The release job must also run `tools/differential_test.py` against an
independent official CLI from the same pinned OpenCC release. Any Python
Binding/CLI difference is blocking; golden candidates are review-only and are
never used to auto-accept changed conversion output.

When the advanced native Jieba payload is enabled, the release job must also
run `tools/differential_jieba_test.py`. Its plugin library, seven plugin config
files, Jieba resources, and manifest hashes are target-specific. No macOS
`.dylib` is copied into a Windows/Linux payload; each native runner builds its
own official plugin.

## GitHub Actions without local Windows/Linux environments

`.github/workflows/ci.yml` uses GitHub-hosted runners as the native build
matrix:

```text
ubuntu-22.04-arm → linux-aarch64-cp314
ubuntu-22.04   → linux-x86_64-cp314
macos-15       → macos-arm64-cp314
macos-15-intel → macos-x86_64-cp314
windows-2022  → windows-x86_64-cp314
```

Each matrix job runs `tools/vendor_opencc.py`, manifest/payload verification,
`tools/build_opencc_jieba.py`, native plugin verification, Python Binding smoke
tests, and the independent official CLI plus native Jieba differential corpora
on its own native runner against the complete wheel tree. Only after those
checks pass does `tools/export_verified_payload.py` derive the runtime subset
and upload it as a workflow artifact. The subset uses the reviewed
`runtime-subset-v1` allowlist, preserves every retained byte and the original
wheel `RECORD`, and records source wheel/tree hashes plus hashes and sizes for
all removed files. Unknown wheel files block export pending review.

Native compatibility is an additional release gate, not implied by an ABI
wheel tag or a successful modern runner. `tools/native_compatibility.py`
inspects the actual Jieba library bytes without loading them: macOS minimum
deployment target must be at most 13.0; Linux GLIBC and GLIBCXX requirements
must be at most 2.35 and 3.4.30 respectively. ELF/Mach-O/PE architecture must
match the payload. Missing or malformed required version metadata is rejected.
Both `verify_vendor.py` and the final ZIP validator run this gate, including
on cached payloads. macOS builds pass `CMAKE_OSX_DEPLOYMENT_TARGET=13.0` and
Linux builds explicitly select GCC 11 on Ubuntu 22.04. These static checks
do not replace actual Sigil testing on the supported host systems.

Successful push and manual runs cache the complete, target-tested wheel tree
under a key derived from the wheel lock, manifest, and native build recipes.
The cache is an acceleration layer: a hit is hash-verified and then reruns the
full-tree tests and CLI differences before the runtime subset is re-exported.
Pull requests do not restore this cache, so untrusted workflow input cannot
supply a native binary.

The dependent `build-packages` job downloads all five artifacts, merges them
with `tools/merge_verified_payloads.py --require-runtimes`, and verifies every
payload and provenance hash. Native jobs already ran the official CLI
differentials on those exact payload bytes. The job builds and validates one
Fat Plugin ZIP and five platform ZIPs, then smoke-tests the Fat Plugin's Linux
x86_64 payload. It writes `SHA256SUMS.txt` and uploads all seven release assets
in one Actions artifact. A payload marked `skipped-cross-platform` cannot enter
any package.

The dependent `package-smoke` matrix downloads that artifact on all five native
runners. Each job extracts its platform ZIP and the Fat Plugin, confirms runtime
selection, runs the complete standard/Jieba self-test, checks one expected
conversion for each of the 16 standard and 7 Jieba configurations, and rejects
any Python bytecode cache in either extracted package. The tagged publication
job runs only after all five smoke jobs pass.

## Release asset contract

`build-packages` uploads one Actions artifact named
`OpenCCForSigil-packages-${{ github.sha }}` containing six installable ZIPs and
`SHA256SUMS.txt`:

- `OpenCCForSigil_<version>.zip`: the five-runtime Fat Plugin;
- `OpenCCForSigil_<version>_macos-arm64.zip`;
- `OpenCCForSigil_<version>_macos-x86_64.zip`;
- `OpenCCForSigil_<version>_windows-x86_64.zip`;
- `OpenCCForSigil_<version>_linux-x86_64.zip`;
- `OpenCCForSigil_<version>_linux-aarch64.zip`;
- `SHA256SUMS.txt`: SHA-256 digests for the six ZIP files above.

Every ZIP has the single top-level `OpenCCForSigil/` directory required by
Sigil. Platform packages contain exactly one verified runtime and generate the
matching `plugin.xml` `oslist` inside the archive; the source tree's `plugin.xml`
is unchanged. The Fat Plugin contains all five runtimes.

The tagged `publish-release` job downloads that exact commit's package
artifact, verifies all six embedded plugin versions against the tag, checks the
package manifests and checksum file, and publishes all seven files. The
`package-smoke` matrix must pass on Linux aarch64, Linux x86_64, macOS arm64,
macOS x86_64, and Windows x86_64 before publication is eligible.

GitHub may also expose automatically generated source archives for a tag. Those
source snapshots are generated by GitHub and are not product assets managed by
this workflow. Previously published releases may retain assets from their
historical workflow; this contract describes future runs.

The engineering specification, testing guidance, and release notes are
source-controlled documentation. They are linked from [`docs/README.md`](README.md)
and are deliberately not generated into a documentation ZIP or uploaded by this
workflow. This preserves the full maintainer record in the repository.

The first-stage artifact size budgets are 7,000,000 bytes for a platform ZIP
and 30,000,000 bytes for the Fat ZIP. The future shared-data Fat target of
12,000,000 bytes is not enforced until that separately reviewed design is
implemented. Changing an enforced budget requires human review of the measured
contents and expected release impact.

Tags without a prerelease suffix (for example, `v0.1.0`) publish a regular
GitHub release and mark it latest. Tags with a suffix (for example,
`v0.1.1-beta`) publish a prerelease without replacing the latest stable release.
The publish job uses `docs/releases/<tag>.md` when present, otherwise GitHub's
generated notes. Notes must distinguish automated validation from real Sigil
host acceptance; a regular release does not imply that untested hosts were tested.

Release mode requires exactly these five runtime identities, with no missing
or extra payload: Linux aarch64, Linux x86_64, macOS arm64, macOS x86_64, and
Windows x86_64, all on CPython 3.14/cp314. Linux aarch64 uses GitHub's
`ubuntu-22.04-arm` hosted runner. `tools/build_plugin.py --require-runtimes` writes a
deterministic ZIP with fixed member order, timestamps, and permissions. The
same ZIP is then passed through `tools/validate_artifact.py --require-runtimes`,
which recomputes every payload tree and data hash from the archive itself.

To use it, push the branch or select **Actions → CI and plugin packages → Run
workflow**. Download the artifact named
`OpenCCForSigil-packages-<commit>` from the successful run. It contains all
seven release assets after package validation. No local
Windows/Linux installation is required; GitHub-hosted runner availability and
repository Actions-minute limits still apply.

## Windows on Arm status

Reviewed on 2026-09-24. The official [Sigil download page](https://sigil-ebook.com/sigil/download/)
currently offers a Windows x64 installer. Microsoft documents x64 emulation on
Windows 11 on Arm; Windows 10 on Arm emulates x86 apps but not x64 apps. PyPI's
[OpenCC release files](https://pypi.org/project/OpenCC/) currently top out at
1.4.2, whose CPython 3.14 Windows wheel is `win_amd64`. A check of the
[PyPI JSON release index](https://pypi.org/pypi/OpenCC/json) across all listed
versions found no `win_arm64` wheel.

There is no native Windows ARM64 payload. On Windows 11 on Arm, the x64 route
is only a candidate when both the running Sigil process and its plugin Python
are x86_64 and CPython 3.14; physical-device acceptance remains **Not verified**.
Before making a support claim, record the Sigil version and the plugin runtime's
`platform.machine()` and `sys.version`, then install the x64 package and verify
conversion, save, and reopen on that device. Windows 10 on Arm cannot use this
x64 route.

If a native ARM64 Sigil becomes available, request an official `win_arm64`
OpenCC wheel from the upstream project and add that verified wheel following
the existing native payload workflow. Building a production wheel from the
sdist remains outside the current provenance invariant and requires a separate
specification decision.

## 发版步骤清单

1. **运行 E-01。** 在 `main` 最新提交上手动运行完整 CI：
   **Actions → CI and plugin packages → Run workflow → Branch: `main`**。
   或运行 `gh workflow run ci.yml --ref main`。用下面的命令等待运行结束，
   并记录运行链接、head SHA 和结论；所有 payload、Jieba 一致性、打包及
   五个平台 smoke job 都必须通过：

   ```sh
   gh run list --workflow ci.yml --branch main --limit 1
   gh run watch <run-id> --exit-status
   gh run view <run-id> --json url,headSha,status,conclusion
   ```

2. **核对包大小。** 从该次运行下载名为
   `OpenCCForSigil-packages-<head-sha>` 的 artifact，解压后检查六个 ZIP
   的字节数：平台 ZIP 不超过 7,000,000 字节，Fat ZIP 不超过 30,000,000
   字节。也要确认六个 ZIP 和 `SHA256SUMS.txt` 都存在。

   ```sh
   gh run download <run-id> \
     --name OpenCCForSigil-packages-<head-sha> \
     --dir /tmp/openccforsigil-packages
   for asset in /tmp/openccforsigil-packages/*.zip; do
     printf '%s ' "$(basename "$asset")"
     wc -c < "$asset"
   done
   ```

3. **完成 E-02。** 核对 `main` 自上一版以来的变更，更新插件版本、
   `CHANGELOG.md` 和 `docs/releases/v<version>.md`。发布说明应记录 E-01
   的运行链接、head SHA 和包大小，并清楚区分 CI 结果与真实 Sigil 主机
   验收。

4. **打标签并推送。** 确认版本更新已提交到 `main`，再创建并推送对应标签：

   ```sh
   git tag v<version>
   git push origin v<version>
   ```

5. **等待发布工作流。** 在 GitHub 的 **Actions → CI and plugin packages**
   打开这个 tag 对应的运行。只有五个平台的 `package-smoke` 和
   `publish-release` 都成功，发布才完成。

6. **下载并验证 Release 资产。** 从该 tag 的 Release 页面下载全部附件，
   包含六个 ZIP 和 `SHA256SUMS.txt`。在仓库 checkout 中运行：

   ```sh
   mise exec -- uv run python tools/release_assets.py \
     --asset-dir /path/to/downloaded-assets \
     --version <version>
   ```

   工具会验证 ZIP 内的版本和 runtime 清单，并核对 `SHA256SUMS.txt` 与
   六个 ZIP 的 SHA-256。

7. **更新 README 下载表。** 将表格中的版本和链接指向刚验证的 Release
   资产；记录每个 ZIP 的大小和校验文件名，并确认自动生成的源码压缩包
   没有被列作可安装插件。
