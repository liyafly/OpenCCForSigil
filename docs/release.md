# Release notes for the skeleton

Release packaging is intentionally split into two future steps:

1. build and verify exact official OpenCC wheel payloads;
2. validate and package the shared Python plugin and manifest.

`tools/build_plugin.py` currently performs step 2 for source-only Phase 0
artifacts. It validates `plugin.xml`, the code version, and the one-top-level-
directory ZIP shape. No unverified wheel payload is synthesized or copied.
