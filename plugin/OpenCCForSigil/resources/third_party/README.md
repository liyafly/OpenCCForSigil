# Bundled third-party resources

The plugin vendors the official BYVoid/OpenCC Python Binding wheel payloads
under `vendor/opencc/payloads/`. The selected manifest records each exact wheel
URL/SHA-256, payload tree hash, runtime triple, and config/data hash.

The upstream OpenCC license and authors notice are retained inside each wheel
payload at:

```text
vendor/opencc/payloads/*/opencc-*.dist-info/licenses/LICENSE
vendor/opencc/payloads/*/opencc-*.dist-info/licenses/AUTHORS
```

Runtime does not download, install, or import OpenCC from outside these
manifest-approved payloads.
