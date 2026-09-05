# Testing

The initial exit condition is:

```text
pytest unit storage/logging = PASS
plugin package metadata = PASS
official vendored payload manifest/hash = PASS
official CLI/Python Binding differential smoke = 100% equality
no-op run = success with zero BookContainer writes
```

Run locally with the pinned environment:

```sh
mise install
mise exec -- uv sync --locked
make check
```

The test tree follows the specification's fixed separation. The current
backend phase also validates the checked-in official wheel payload, import
origin, all V1 configs, and the independent CLI smoke corpus. Later phases add
document, structural, integration, golden, and performance suites; they should
not be collapsed into one plugin smoke test.
