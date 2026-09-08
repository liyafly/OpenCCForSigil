# Third-party notices

Project-authored OpenCCForSigil source and documentation are licensed under
the Apache License, Version 2.0; see [`LICENSE`](LICENSE). This file does not
relicense any bundled dependency.

The checked-in payload is the BYVoid/OpenCC official Python Binding
distribution `opencc` `1.4.2`, imported only from the manifest-selected macOS
arm64 / CPython 3.14 (`cp314`) wheel payload. Runtime never downloads or
installs the dependency. The manifest records the exact wheel URL, wheel
SHA-256, extracted payload tree hash, config/data hashes, and the optional
official `opencc-jieba` native plugin/resource hashes. Wheel contents, the
OpenCC license, and third-party notices remain in the final plugin artifact.
Additional Fat Plugin payloads require the same exact metadata and target
runtime verification.

Design references are cloned outside this repository under
`../OpenCCForSigil-References/` and are not packaged or imported at runtime.

The advanced Jieba option uses only the official BYVoid/OpenCC native
`plugins/jieba` payload built from the pinned upstream commit. It is not a
Python Jieba implementation and is not copied from the reference project.
The complete package notice index is preserved at
`plugin/OpenCCForSigil/resources/third_party/THIRD_PARTY_NOTICES.md`.

The pinned OpenCC source commit also supplies the native dependency inputs
listed below. Their complete notices are in the package resource directory and
are required by `tools/validate_artifact.py`:

| Component | Pinned input and shipped use | Notice |
| --- | --- | --- |
| marisa-trie 0.3.1 | `BYVoid/OpenCC@025f371dc76b598d77384fbdab90c937471844d8`, `deps/marisa-0.3.1`; shipped core/static tools | `MARISA_COPYING.md` (BSD-2-Clause OR LGPL-2.1-or-later) |
| darts-clone 0.32h | `BYVoid/OpenCC@025f371dc76b598d77384fbdab90c937471844d8`, `deps/darts-clone-0.32h`; shipped core/static tools | `DARTS_CLONE_COPYING.md` (BSD-2-Clause) |
| rapidjson 1.1.0 | `BYVoid/OpenCC@025f371dc76b598d77384fbdab90c937471844d8`, `deps/rapidjson-1.1.0`; shipped native components | `RAPIDJSON_LICENSE.txt` |
| tclap 1.2.5 | `BYVoid/OpenCC@025f371dc76b598d77384fbdab90c937471844d8`, `deps/tclap-1.2.5`; shipped CLI tools | `TCLAP_COPYING` (MIT) |
| pybind11 2.13.1 | `BYVoid/OpenCC@025f371dc76b598d77384fbdab90c937471844d8`, `deps/pybind11-2.13.1`; shipped `opencc_clib` extension | `PYBIND11_LICENSE` (BSD-3-Clause) |
| cppjieba | `BYVoid/OpenCC@025f371dc76b598d77384fbdab90c937471844d8`, `plugins/jieba/deps/cppjieba`; optional shipped Jieba plugin | `CPPJIEBA_LICENSE` (MIT) |

Google Test and Google Benchmark are present only as pinned OpenCC build/test
dependencies and are not present in the shipped payloads, so they are not
runtime dependencies or required package notices.
