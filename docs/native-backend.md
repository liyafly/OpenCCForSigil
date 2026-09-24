# Official Python Binding backend plan

The only production backend is the BYVoid/OpenCC official Python Binding
distribution `opencc` version `1.4.2`. The source reference is checked out at:

```text
../OpenCCForSigil-References/OpenCC
```

The primary runtime matrix supports CPython 3.14.x with wheel ABI `cp314`.
There is also a standalone Linux x86_64 payload for CPython 3.12 / `cp312`,
matching Ubuntu 24.04's packaged Sigil. The current Sigil bundled Python
3.14.2 is the production baseline; Python 3.14.7 is used for mise development
and CI. Patch versions are recorded in provenance and do not participate in
payload selection.

Standard startup preflight checks standard conversions and the selected
configuration. Optional Jieba load tests are performed once per backend when
enumerating available configurations. If the verified optional library cannot
load, standard conversion remains available and the UI/log reports the cause;
an explicitly selected Jieba configuration still fails rather than changing
its algorithm. Payload hash and provenance errors remain blocking. The full
`self_test()` continues to include the optional capability for diagnostics;
startup uses `self_test(include_optional=False)` (spec §4.4.1 and §4.5.5).

The current implementation provides the allowlist, provenance model,
wheel/payload manifest, deterministic tree hash, exact runtime selector,
import-origin boundary, and a verified macOS arm64 / cp314 payload. A missing
payload entry is an error, not a reason to use a system OpenCC or to run pip.

Within one process, the runtime selector caches a verified payload-tree digest
by absolute root and the sorted `(relative path, size, mtime_ns)` signature of
its files. The first check hashes the full tree; loader checks reuse that digest
while the signature is unchanged, and a size or modification-time change causes
a fresh hash. This saves repeated reads of the 24 MB payload. It assumes payload
files do not change bytes while preserving both size and modification time.
Manifest-listed native plugin files still receive their individual SHA-256
checks on each backend selection.

Additional Fat Plugin payloads must be added only after official wheel hash
validation, clean-process import/origin checks on the target runtime,
config-load smoke tests, and canonical CLI differential tests have passed. The
package's native extension remains an official wheel payload; OpenCCForSigil
does not load it with ctypes or manage its C/C++ lifetime directly.

The official upstream native `opencc-jieba` plugin is now a detectable advanced
payload. See [`jieba-native-evaluation.md`](jieba-native-evaluation.md). The
macOS arm64 payload includes the verified plugin; Windows, Linux, and macOS
x86_64 are built independently by the GitHub Actions native matrix before
entering the Fat Plugin. The UI never offers a generic segmentation selector.

The plugin is the official BYVoid/OpenCC C++ plugin, not a Python Jieba
rewrite. It is selected by official plugin-backed configs such as
`s2twp_jieba`, and its library/resources are loaded only from the exact
manifest-approved payload.

## Linux 上的 Python 版本

Reviewed on 2026-09-24. Linux packages use the Python interpreter that runs
Sigil's plugins; the OpenCC native extension ABI must match that interpreter.
The Linux x86_64 packages provide CPython 3.14 / `cp314` and CPython 3.12 /
`cp312` payloads (see
[`payload-lock.json`](../native_build/payload-lock.json)). Official distro
package metadata and package contents show these versions:

| Sigil package | Python ABI evidence |
| --- | --- |
| Ubuntu 22.04 (Jammy), Sigil 1.9.2 | Depends on `libpython3.10`; CPython 3.10. ([Ubuntu package](https://packages.ubuntu.com/jammy/sigil)) |
| Ubuntu 24.04 (Noble), Sigil 2.0.1 | Depends on `libpython3.12t64`; CPython 3.12. ([Ubuntu package](https://packages.ubuntu.com/noble/sigil)) |
| Debian 12 (Bookworm), Sigil 1.9.20 | Depends on `libpython3.11`; CPython 3.11. ([Debian package](https://packages.debian.org/bookworm/sigil)) |
| Fedora 45, Sigil 2.8.1 | Depends on `python3-libs`; the package contains `.cpython-315.pyc` files, indicating CPython 3.15. ([Fedora package](https://packages.fedoraproject.org/pkgs/sigil/sigil/fedora-45.html)) |
| Arch Linux, Sigil 2.8.1 | The package contains `.cpython-314.pyc` files, indicating CPython 3.14. ([Arch package file list](https://archlinux.org/packages/extra/x86_64/sigil/files/)) |
| Flathub `com.sigil_ebook.Sigil` | The current manifest uses `org.kde.Platform` and `io.qt.PySide.BaseApp` 6.10 and sets `USE_SYSTEM_PYTHON=1`; its Python comes from the isolated Flatpak runtime, not the host distribution. The KDE 6.10 runtime's Python module path is `python3.13`, so this package uses CPython 3.13. ([Sigil manifest](https://github.com/flathub/com.sigil_ebook.Sigil/blob/master/com.sigil_ebook.Sigil.yml), [KDE 6.10 runtime Python path](https://github.com/flathub/org.qgis.qgis/blob/master/org.qgis.qgis.json)) |

Ubuntu 24.04's package uses CPython 3.12 and has a matching standalone Linux
x86_64 package. Jammy 3.10, Bookworm 3.11, Fedora 3.15, and the inspected
Flathub runtime 3.13 remain unsupported. A successful native build or package
smoke on CI does not establish real Sigil host acceptance. The Flatpak
comparison is specific to its pinned runtime branch and can change when its
manifest or runtime is updated. No distro package or real Sigil host was
installed as part of this metadata review.

The release plan's recommendation to add a separate Linux `cp312` payload has
been adopted. PyPI publishes the exact CPython 3.12 Linux x86_64 wheel used by
the locked build; the package targets Ubuntu 24.04's packaged Sigil. ([OpenCC
1.4.2 on PyPI](https://pypi.org/project/OpenCC/1.4.2/), [Ubuntu Noble Sigil
package](https://packages.ubuntu.com/noble/sigil))
