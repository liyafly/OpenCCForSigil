# OpenCCForSigil

`OpenCCForSigil` is a Sigil `edit` plugin for source-preserving Chinese
simplified/traditional and regional conversion. The implementation follows
the stable engineering specification in `docs/OpenCCForSigil_Spec_v1.3/`.

## Current implementation status

The repository now contains the installable plugin skeleton plus one verified
official OpenCC wheel payload for the current build host:

- a thin `plugin.py` entry point and `plugin.xml` metadata;
- explicit application/session states;
- user-data storage and JSONL logging boundaries;
- the official OpenCC Python Binding and exact runtime-selector boundary;
- a verified OpenCC 1.4.2 macOS arm64 / CPython 3.14 / `cp314` payload;
- build-time wheel fetch, SHA-256, payload, config/data, and import checks;
- package validation and a no-op run path that never calls `bk.writefile()`;
- tests and a mise-pinned development toolchain.

Document tokenization and UI behavior remain reserved for later phases. The
entry point still does not mutate an EPUB; runtime must not fall back to a
system OpenCC installation or invoke pip.

V1 formally supports CPython 3.14.x with wheel ABI `cp314`; the current Sigil
bundled Python 3.14.2 is the production baseline. The reproducible development
and CI baseline is Python 3.14.7, uv 0.12.9, and Ruff 0.16.6. Patch versions
are recorded in provenance but do not participate in payload selection.

## Development

Install the pinned tools and locked Python dependencies:

```sh
mise install
mise exec -- uv sync --locked
```

Run checks:

```sh
make check
make package
make spec-bundle
```

The generated ZIP has exactly one top-level directory, `OpenCCForSigil/`, as
required by the Sigil plugin packaging contract. `make spec-bundle` generates
the versioned v1.3 specification files and
`dist/OpenCCForSigil_Spec_v1.3_bundle.zip`.

## Reference repositories

The external design references live beside this repository:

```text
../OpenCCForSigil-References/OpenCC            # ver.1.4.2
../OpenCCForSigil-References/tradsimp
../OpenCCForSigil-References/plugin-api-guide
```

They are for inspection only and are not runtime dependencies.
