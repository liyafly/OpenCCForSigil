# Third-party notices

The checked-in payload is the BYVoid/OpenCC official Python Binding
distribution `opencc` `1.4.2`, imported only from the manifest-selected macOS
arm64 / CPython 3.14 (`cp314`) wheel payload. Runtime never downloads or
installs the dependency. The manifest records the exact wheel URL, wheel
SHA-256, extracted payload tree hash, and config/data hashes. Wheel contents,
the OpenCC license, and any third-party notices remain in the final plugin
artifact. Additional Fat Plugin payloads require the same exact metadata and
runtime verification.

Design references are cloned outside this repository under
`../OpenCCForSigil-References/` and are not packaged or imported at runtime.

The advanced Jieba option uses only the official BYVoid/OpenCC native
`plugins/jieba` payload built from the pinned upstream commit. It is not a
Python Jieba implementation and is not copied from the reference project.
The plugin's `cppjieba` MIT notice is preserved at
`plugin/OpenCCForSigil/resources/third_party/CPPJIEBA_LICENSE`.
