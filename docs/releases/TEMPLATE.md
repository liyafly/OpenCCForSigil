# OpenCCForSigil `<version>`

## Install

Choose a ZIP below and install it through Sigil's plugin manager. The Fat
Plugin contains the five CPython 3.14/cp314 runtimes and is the recommended
choice for those runtimes. Linux x86_64 CPython 3.12 has a separate package.
GitHub source archives are not installable plugin packages. Each package
requires its listed CPython ABI.

| Asset | Runtime coverage | Real Sigil host acceptance |
| --- | --- | --- |
| `OpenCCForSigil_<version>.zip` | Linux aarch64 and x86_64; macOS arm64 and x86_64; Windows x86_64 | Not verified |
| `OpenCCForSigil_<version>_macos-arm64.zip` | macOS Apple Silicon | Not verified |
| `OpenCCForSigil_<version>_macos-x86_64.zip` | macOS Intel, including Rosetta | Not verified |
| `OpenCCForSigil_<version>_windows-x86_64.zip` | Windows x64 | Not verified |
| `OpenCCForSigil_<version>_linux-x86_64.zip` | Linux x86_64 | Not verified |
| `OpenCCForSigil_<version>_linux-x86_64-cp312.zip` | Linux x86_64, CPython 3.12/cp312 | Not verified |
| `OpenCCForSigil_<version>_linux-aarch64.zip` | Linux aarch64 | Not verified |
| `SHA256SUMS.txt` | Digests for all seven ZIP assets | — |

Record real host acceptance only after installing the package in Sigil,
converting a fixture EPUB, saving it, and reopening it. Include the Sigil
version, OS version, and process architecture. Static checks and native CI
smoke tests do not count as host acceptance.

Windows on Arm is not native support. The x64 package is only a candidate for
Windows 11 on Arm with x64 Sigil and x64 plugin Python; mark it **Not verified**
until tested on a physical device. Windows 10 on Arm cannot run x64 Sigil.

## Changes

- <Release changes>

## Automated validation

- <CI run link and package-smoke result>
- <Native compatibility checks>
- GitHub artifact attestations cover each ZIP and `SHA256SUMS.txt`; verify them
  with `gh attestation verify <asset> --repo liyafly/OpenCCForSigil
  --signer-workflow liyafly/OpenCCForSigil/.github/workflows/ci.yml`.

## Remaining acceptance

- Platforms not tested in a real Sigil host: **Not verified**.
