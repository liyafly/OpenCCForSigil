# OpenCCForSigil

`OpenCCForSigil` is a Sigil `edit` plugin for source-preserving Chinese
simplified/traditional and regional conversion. The implementation follows
the stable engineering specification in `docs/OpenCCForSigil_Spec_v1.4/`. The
documentation entry point is [`docs/README.md`](docs/README.md). The
project-authored source is licensed under [Apache-2.0](LICENSE); bundled
dependencies retain the notices described in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Current implementation status

The V1 conversion workflow is connected end to end:

- all 16 official configs, plus seven optional native Jieba configs when the
  verified payload can load them;
- explicit single/selected/spine/all XHTML scope, with a frozen manifest-ID
  selection and opt-in NCX, whitelisted metadata, and Chinese language tags;
- source-preserving exact/protect rules, profile and book scopes, import/export,
  a text sandbox, and independent official-config inspection;
- saved profiles, optional quotation/horizontal-punctuation changes, mixed
  script diagnostics, and explicit high-risk pivot chains;
- preview decisions by item, file, category, and risk, grouped language changes,
  return-to-settings analysis, and a Checkpoint reminder before applying;
- worker-owned conversion, cooperative cancellation, in-memory staging, XML
  syntax/structure verification, and source/rule/profile snapshot checks;
- conversion history and Markdown/JSON reports; document text is excluded from
  persisted history, and full-diff export requires explicit opt-in;
- English, 简体中文, and 繁體中文 UI.

See [document conversion](docs/extended-document-conversion.md),
[rules and profiles](docs/rules-and-profiles.md), and
[current validation boundaries](docs/deviations.md). Rules, preferences, logs,
profiles, and history live outside the plugin installation and the EPUB.

The checked-in payload is macOS arm64/cp314. CI assembles a five-runtime Fat
Plugin and six platform packages, then inspects actual native OS/ABI
requirements: macOS deployment target 13.0 or earlier, and Linux
GLIBC/GLIBCXX at most 2.35/3.4.30. This does not replace installing, applying,
saving, and reopening an EPUB in each real Sigil host. Linux aarch64 is
supported through its native payload. Windows ARM and Python minor versions
other than 3.14 are not declared supported payloads, except for the separate
Linux x86_64/cp312 package described below.

On Windows 11 on Arm, the possible route is x64 Sigil under Windows x64
emulation with the `windows-x86_64` package, and only when the plugin's Python
runtime reports x86_64/CPython 3.14. That route has not been tested on a Windows
Arm device. Windows 10 on Arm does not provide x64 emulation. See the
[Windows on Arm status](docs/release.md#windows-on-arm-status).

Standard preflight is independent of optional Jieba loading. An optional load
failure disables Jieba with its reason; corruption/provenance failures block
execution. Runtime never downloads dependencies, invokes pip, imports a system
OpenCC, or silently changes the selected algorithm.

The primary runtime matrix supports CPython 3.14.x with wheel ABI `cp314`; the
current Sigil bundled Python 3.14.2 is the production baseline. A separate
Linux x86_64 package supports CPython 3.12/cp312. The reproducible development
and CI baseline is Python 3.14.7, uv 0.12.9, and Ruff 0.16.6. Patch versions
are recorded in provenance but do not participate in payload selection.

## Choose and install a package

Download a ZIP asset from the GitHub release and install it through Sigil's
plugin manager. GitHub's automatically generated source archives are not
installable plugins. Older releases may have fewer package assets; use the
assets actually attached to that release. Every package requires an exact
supported CPython runtime and ABI.

Current release: [v0.2.1](https://github.com/liyafly/OpenCCForSigil/releases/tag/v0.2.1).
Sizes below are rounded decimal MB; exact byte counts are in the release notes.

| Asset | Use it when |
| --- | --- |
| [OpenCCForSigil_0.2.1.zip · 27.28 MB](https://github.com/liyafly/OpenCCForSigil/releases/download/v0.2.1/OpenCCForSigil_0.2.1.zip) | Fat Plugin for the five CPython 3.14/cp314 runtimes. |
| [OpenCCForSigil_0.2.1_macos-arm64.zip · 5.43 MB](https://github.com/liyafly/OpenCCForSigil/releases/download/v0.2.1/OpenCCForSigil_0.2.1_macos-arm64.zip) | Sigil runs as Apple Silicon. |
| [OpenCCForSigil_0.2.1_macos-x86_64.zip · 5.48 MB](https://github.com/liyafly/OpenCCForSigil/releases/download/v0.2.1/OpenCCForSigil_0.2.1_macos-x86_64.zip) | Sigil runs as Intel, including under Rosetta. |
| [OpenCCForSigil_0.2.1_windows-x86_64.zip · 5.58 MB](https://github.com/liyafly/OpenCCForSigil/releases/download/v0.2.1/OpenCCForSigil_0.2.1_windows-x86_64.zip) | Sigil runs as Windows x64. |
| [OpenCCForSigil_0.2.1_linux-x86_64.zip · 5.86 MB](https://github.com/liyafly/OpenCCForSigil/releases/download/v0.2.1/OpenCCForSigil_0.2.1_linux-x86_64.zip) | Sigil runs CPython 3.14/cp314 and `uname -m` reports `x86_64`. |
| [OpenCCForSigil_0.2.1_linux-x86_64-cp312.zip · 5.86 MB](https://github.com/liyafly/OpenCCForSigil/releases/download/v0.2.1/OpenCCForSigil_0.2.1_linux-x86_64-cp312.zip) | Linux x86_64 Sigil runs CPython 3.12/cp312, including Ubuntu 24.04's packaged Sigil. |
| [OpenCCForSigil_0.2.1_linux-aarch64.zip · 5.81 MB](https://github.com/liyafly/OpenCCForSigil/releases/download/v0.2.1/OpenCCForSigil_0.2.1_linux-aarch64.zip) | Sigil runs CPython 3.14/cp314 and `uname -m` reports `aarch64`. |
| [SHA256SUMS.txt](https://github.com/liyafly/OpenCCForSigil/releases/download/v0.2.1/SHA256SUMS.txt) | SHA-256 digest list for all seven ZIPs. |

Choose the Linux ZIP whose CPython ABI matches Sigil's plugin process. The
standard Linux assets use CPython 3.14/cp314; the separate x86_64 asset uses
CPython 3.12/cp312. Ubuntu 22.04, Debian 12, Fedora, and Flathub use other
Python minor versions and are not covered by these assets; see [the Linux
Python compatibility notes](docs/native-backend.md#linux-上的-python-版本).
The CI package smoke is not a real Sigil host acceptance test.

To check Sigil's process architecture, use **Activity Monitor → Sigil → Kind**
on macOS (`Apple` or `Intel`), **Task Manager → Details → Platform** on
Windows, or `uname -m` on Linux. Choose the platform package that matches the
running Sigil process. Choose the Fat Plugin when you have confirmed that
Sigil's plugin process uses CPython 3.14/cp314; Linux x86_64 CPython 3.12 must
use the separate cp312 package.

## Development

Install the pinned tools and locked Python dependencies:

```sh
mise install
mise exec -- uv sync --locked
```

Run checks:

```sh
make check
make package
```

GitHub Actions builds the native payload matrix on hosted Ubuntu, macOS, and
Windows runners, then assembles and smoke-tests the Fat Plugin and all six
platform ZIPs. See
[`docs/release.md`](docs/release.md) for the matrix and artifact workflow; a
local Windows/Linux installation is not required.

The official wheel set is pinned in `native_build/payload-lock.json`. Push and
manual CI runs may restore complete target-tested payloads from a verified
cache, then rerun full-tree tests and CLI differences before deriving the
runtime subset. When the cache is absent, the locked wheels and native build
are reproduced on the matching hosted runners. The release job requires all
six source runtime payloads, includes the five CPython 3.14 runtimes in the
Fat Plugin, and rechecks hashes from each final ZIP.

For future workflow runs, the CI job uploads the seven package ZIPs and
`SHA256SUMS.txt` in one Actions artifact named
`OpenCCForSigil-packages-${{ github.sha }}`. A tagged run publishes those same
eight files after every package has passed its matching runtime smoke test and
GitHub has generated and verified artifact attestations for the ZIPs and
checksum manifest. After downloading the files, verify their provenance with:

```sh
for asset in OpenCCForSigil_*.zip SHA256SUMS.txt; do
  gh attestation verify "$asset" \
    --repo liyafly/OpenCCForSigil \
    --signer-workflow liyafly/OpenCCForSigil/.github/workflows/ci.yml
done
```
GitHub may also expose its automatically generated source archives for the tag;
those are source snapshots rather than installable plugin assets.

The generated ZIP has exactly one top-level directory, `OpenCCForSigil/`, as
required by the Sigil plugin packaging contract. Normative and maintainer
documentation stays in the repository under `docs/`; it is not copied into
`dist/` or generated as a documentation ZIP.

## Reference repositories

The external design references live beside this repository:

```text
../OpenCCForSigil-References/OpenCC            # ver.1.4.2
../OpenCCForSigil-References/tradsimp
../OpenCCForSigil-References/plugin-api-guide
```

They are for inspection only and are not runtime dependencies.
