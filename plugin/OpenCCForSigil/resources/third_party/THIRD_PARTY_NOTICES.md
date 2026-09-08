# Third-party notices

OpenCCForSigil's own plugin source is licensed under the Apache License,
Version 2.0; see `../../LICENSE`. The components below retain their original
licenses and notices.

OpenCCForSigil vendors the official BYVoid/OpenCC Python Binding distribution
`opencc` from the pinned upstream release recorded in
`vendor/opencc/manifest.json`.

For every payload, the upstream license and authors notice are preserved from
the official wheel at:

```text
vendor/opencc/payloads/*/opencc-*.dist-info/licenses/LICENSE
vendor/opencc/payloads/*/opencc-*.dist-info/licenses/AUTHORS
```

The manifest records the source URL, wheel SHA-256, extracted payload SHA-256,
and config/data hashes. The plugin does not invoke pip, use user
site-packages, or download runtime dependencies.

## Dependency index

The following components are identified from the pinned OpenCC source and the
payload contents. Each notice is copied into this directory and is required by
the final ZIP validator.

| Component | Pinned input and shipped use | Notice |
| --- | --- | --- |
| marisa-trie 0.3.1 | `BYVoid/OpenCC@025f371dc76b598d77384fbdab90c937471844d8`, `deps/marisa-0.3.1`; compiled into the shipped OpenCC core/static tools | [MARISA_COPYING.md](MARISA_COPYING.md) (BSD-2-Clause OR LGPL-2.1-or-later) |
| darts-clone 0.32h | `BYVoid/OpenCC@025f371dc76b598d77384fbdab90c937471844d8`, `deps/darts-clone-0.32h`; compiled into the shipped OpenCC core/static tools | [DARTS_CLONE_COPYING.md](DARTS_CLONE_COPYING.md) (BSD-2-Clause) |
| rapidjson 1.1.0 | `BYVoid/OpenCC@025f371dc76b598d77384fbdab90c937471844d8`, `deps/rapidjson-1.1.0`; header code compiled into shipped native components | [RAPIDJSON_LICENSE.txt](RAPIDJSON_LICENSE.txt) |
| tclap 1.2.5 | `BYVoid/OpenCC@025f371dc76b598d77384fbdab90c937471844d8`, `deps/tclap-1.2.5`; header code compiled into shipped CLI tools | [TCLAP_COPYING](TCLAP_COPYING) (MIT) |
| pybind11 2.13.1 | `BYVoid/OpenCC@025f371dc76b598d77384fbdab90c937471844d8`, `deps/pybind11-2.13.1`; compiled into the shipped `opencc_clib` Python extension (headers are not shipped) | [PYBIND11_LICENSE](PYBIND11_LICENSE) (BSD-3-Clause) |
| cppjieba | `BYVoid/OpenCC@025f371dc76b598d77384fbdab90c937471844d8`, `plugins/jieba/deps/cppjieba`; compiled into the optional shipped native Jieba plugin | [CPPJIEBA_LICENSE](CPPJIEBA_LICENSE) (MIT) |

The marisa notice preserves its upstream dual-license wording; distribution
does not require applying both licenses. The RapidJSON notice preserves its
upstream subcomponent exceptions. RapidJSON's `license.txt` and TCLAP's
`COPYING` are taken from their pinned 1.1.0 and 1.2.5 upstream releases because
those dependency directories in the pinned OpenCC source do not carry a copy
of the license file.

The pinned OpenCC source also contains Google Test and Google Benchmark for
build/test use. They are not present in the shipped payloads and are therefore
not listed as runtime dependencies or required artifact notices.

The optional advanced Jieba capability is the official BYVoid/OpenCC native
`plugins/jieba` C++ plugin from the same pinned upstream tag and commit. It is
built at release time against the same-release official OpenCC static core and
is vendored with its plugin configs and dictionary resources. The native
library SHA-256, resource hashes, compiler profile, and upstream provenance
are recorded in the payload manifest.
