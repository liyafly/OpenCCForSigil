# Third-party notices

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

The optional advanced Jieba capability is the official BYVoid/OpenCC native
`plugins/jieba` C++ plugin from the same pinned upstream tag and commit. It is
built at release time against the same-release official OpenCC static core and
is vendored with its plugin configs and dictionary resources. The plugin uses
the upstream `cppjieba` dependency; its MIT notice is preserved in
`CPPJIEBA_LICENSE`. The native library SHA-256, resource hashes, compiler
profile, and upstream provenance are recorded in the payload manifest.
