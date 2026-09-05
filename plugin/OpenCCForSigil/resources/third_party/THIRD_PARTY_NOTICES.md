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
