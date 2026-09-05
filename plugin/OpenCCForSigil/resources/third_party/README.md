# Bundled third-party resources

The plugin vendors the official BYVoid/OpenCC Python Binding wheel payloads
under `vendor/opencc/payloads/`. The selected manifest records each exact wheel
URL/SHA-256, payload tree hash, runtime triple, config/data hash, and (when
present) official native plugin hashes.

The upstream OpenCC license and authors notice are retained inside each wheel
payload at:

```text
vendor/opencc/payloads/*/opencc-*.dist-info/licenses/LICENSE
vendor/opencc/payloads/*/opencc-*.dist-info/licenses/AUTHORS
```

Runtime does not download, install, or import OpenCC from outside these
manifest-approved payloads.

The optional advanced Jieba payload is built from the pinned official
`BYVoid/OpenCC/plugins/jieba` source and includes the `cppjieba` MIT notice in
`CPPJIEBA_LICENSE`. It is not a Python Jieba implementation.
