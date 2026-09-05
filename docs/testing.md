# Testing

The initial exit condition is:

```text
pytest unit storage/logging = PASS
plugin package metadata = PASS
no-op run = success with zero BookContainer writes
```

Run locally with the pinned environment:

```sh
mise install
mise exec -- uv sync --locked
make check
```

The test tree follows the specification's fixed separation. Later phases add
native, document, structural, integration, golden, and performance suites;
they should not be collapsed into one plugin smoke test.
