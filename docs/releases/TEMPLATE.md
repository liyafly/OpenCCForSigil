# OpenCCForSigil `<version>`

## Install

Choose a ZIP below and install it through Sigil's plugin manager. The Fat
Plugin works across all five listed runtimes and is the recommended choice if
you are unsure which architecture Sigil is using. GitHub source archives are
not installable plugin packages. All packages require CPython 3.14.x/cp314.

| Asset | Runtime coverage | Real Sigil host acceptance |
| --- | --- | --- |
| `OpenCCForSigil_<version>.zip` | Linux aarch64 and x86_64; macOS arm64 and x86_64; Windows x86_64 | Not verified |
| `OpenCCForSigil_<version>_macos-arm64.zip` | macOS Apple Silicon | Not verified |
| `OpenCCForSigil_<version>_macos-x86_64.zip` | macOS Intel, including Rosetta | Not verified |
| `OpenCCForSigil_<version>_windows-x86_64.zip` | Windows x64 | Not verified |
| `OpenCCForSigil_<version>_linux-x86_64.zip` | Linux x86_64 | Not verified |
| `OpenCCForSigil_<version>_linux-aarch64.zip` | Linux aarch64 | Not verified |
| `SHA256SUMS.txt` | Digests for all six ZIP assets | — |

Record real host acceptance only after installing the package in Sigil,
converting a fixture EPUB, saving it, and reopening it. Include the Sigil
version, OS version, and process architecture. Static checks and native CI
smoke tests do not count as host acceptance.

## Changes

- <Release changes>

## Automated validation

- <CI run link and package-smoke result>
- <Native compatibility checks>

## Remaining acceptance

- Platforms not tested in a real Sigil host: **Not verified**.
