# Third-party notices

The Phase 0 skeleton does not ship native OpenCC binaries or dictionary data.

The planned runtime dependency is the BYVoid/OpenCC official Python Binding
distribution `opencc` `1.4.2`, imported only from a checked-in official wheel
payload listed in `plugin/OpenCCForSigil/vendor/opencc/manifest.json` after
wheel/payload hash verification. Wheel contents, OpenCC license, and any
third-party notices will be added together in Phase 1 after the runtime matrix
is established.

Design references are cloned outside this repository under
`../OpenCCForSigil-References/` and are not packaged or imported at runtime.
