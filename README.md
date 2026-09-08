# OpenCCForSigil

`OpenCCForSigil` is a Sigil `edit` plugin for source-preserving Chinese
simplified/traditional and regional conversion. The implementation follows
the stable engineering specification in `docs/OpenCCForSigil_Spec_v1.4/`. The
documentation entry point is [`docs/README.md`](docs/README.md). The
project-authored source is licensed under [Apache-2.0](LICENSE); bundled
dependencies retain the notices described in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Current implementation status

The repository now contains the installable plugin skeleton plus one verified
official OpenCC wheel payload for the current build host:

- a thin `plugin.py` entry point and `plugin.xml` metadata;
- explicit application/session states;
- user-data storage and JSONL logging boundaries;
- the official OpenCC Python Binding and exact runtime-selector boundary;
- a verified OpenCC 1.4.2 macOS arm64 / CPython 3.14 / `cp314` payload;
- the official upstream native `opencc-jieba` plugin, its seven plugin configs,
  and its Jieba resources in the macOS payload;
- build-time wheel fetch, SHA-256, payload, config/data, and import checks;
- an offset-preserving XHTML tokenizer and TextTarget/ConversionPlan pipeline;
- Preview decisions with Accept this, Skip this, Accept all, and Skip all;
- staging, structural verification, source-SHA256 concurrency checks, and a
  single adapter commit boundary for `bk.writefile()`;
- three-language UI catalogs (简体中文, English, 繁體中文), remembered in
  plugin preferences;
- an explicit XHTML target picker for one file, Book Browser-selected files,
  or all XHTML resources, followed by file-level preview and cancellable
  analysis progress;
- tests and a mise-pinned development toolchain.

The first interactive conversion slice lets the user explicitly choose a
pinned standard OpenCC config before planning (`s2t` is the initial default;
regional choices such as `tw2s` and `tw2sp` are available). When the selected
payload has passed the native-plugin checks, an advanced checkbox maps a
standard direction to its official `*_jieba` config. It previews every
planned change before any EPUB write. Script/style/code/pre content and
protected attributes remain unchanged. Runtime must not fall back to a system
OpenCC/plugin installation or invoke pip.

The target picker uses manifest IDs and keeps the selection frozen for the
whole run. Sigil's `selected_iter()` is the Book Browser selection; it is not
treated as the active editor tab. If a host does not expose that iterator, the
same picker opens with no initial checks so the user must choose the targets
explicitly. The plugin reads XHTML bodies only after the user confirms the
target set.

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
```

GitHub Actions builds the native payload matrix on hosted Ubuntu, macOS, and
Windows runners, then assembles the verified Fat Plugin artifact. See
[`docs/release.md`](docs/release.md) for the matrix and artifact workflow; a
local Windows/Linux installation is not required.

The official wheel set is pinned in `native_build/payload-lock.json`. Push and
manual CI runs reuse previously target-tested payloads from a verified cache;
when the cache is absent, the locked wheels and native build are reproduced on
the matching hosted runners. The release job requires all four supported
runtime payloads and rechecks their hashes from the final ZIP.

For future workflow runs, the CI job uploads one Actions artifact named
`OpenCCForSigil-fat-plugin-${{ github.sha }}` containing
`OpenCCForSigil_${{ github.sha }}.zip`. On a tagged run, the publish job verifies
that artifact, renames the product ZIP to `OpenCCForSigil_<version>.zip`, and
uploads that version-named file as the release's one product asset. GitHub may
also expose its automatically generated source archives for the tag; those are
source snapshots rather than installable plugin assets.

The generated ZIP has exactly one top-level directory, `OpenCCForSigil/`, as
required by the Sigil plugin packaging contract. Normative and maintainer
documentation stays in the repository under `docs/`; it is not copied into
`dist/` or generated as a documentation ZIP.

## Reference repositories

The external design references live beside this repository:

```text
../OpenCCForSigil-References/OpenCC            # ver.1.4.2
../OpenCCForSigil-References/tradsimp
../OpenCCForSigil-References/plugin-api-guide
```

They are for inspection only and are not runtime dependencies.
