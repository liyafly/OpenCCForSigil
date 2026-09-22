# OpenCCForSigil

`OpenCCForSigil` is a Sigil `edit` plugin for source-preserving Chinese
simplified/traditional and regional conversion. The implementation follows
the stable engineering specification in `docs/OpenCCForSigil_Spec_v1.4/`. The
documentation entry point is [`docs/README.md`](docs/README.md). The
project-authored source is licensed under [Apache-2.0](LICENSE); bundled
dependencies retain the notices described in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Current implementation status

The V1 conversion workflow is connected end to end:

- all 16 official configs, plus seven optional native Jieba configs when the
  verified payload can load them;
- explicit single/selected/spine/all XHTML scope, with a frozen manifest-ID
  selection and opt-in NCX, whitelisted metadata, and Chinese language tags;
- source-preserving exact/protect rules, profile and book scopes, import/export,
  a text sandbox, and independent official-config inspection;
- saved profiles, optional quotation/horizontal-punctuation changes, mixed
  script diagnostics, and explicit high-risk pivot chains;
- preview decisions by item, file, category, and risk, grouped language changes,
  return-to-settings analysis, and a Checkpoint reminder before applying;
- worker-owned conversion, cooperative cancellation, in-memory staging, XML
  syntax/structure verification, and source/rule/profile snapshot checks;
- conversion history and Markdown/JSON reports; document text is excluded from
  persisted history, and full-diff export requires explicit opt-in;
- English, 简体中文, and 繁體中文 UI.

See [document conversion](docs/extended-document-conversion.md),
[rules and profiles](docs/rules-and-profiles.md), and
[current validation boundaries](docs/deviations.md). Rules, preferences, logs,
profiles, and history live outside the plugin installation and the EPUB.

The checked-in payload is macOS arm64/cp314. CI assembles the four-platform Fat
Plugin and inspects actual native OS/ABI requirements: macOS deployment target
13.0 or earlier, and Linux GLIBC/GLIBCXX at most 2.35/3.4.30. This does not
replace installing, applying, saving, and reopening an EPUB in each real Sigil
host. Windows and Linux ARM, and other Python minor versions, are not declared
supported payloads.

Standard preflight is independent of optional Jieba loading. An optional load
failure disables Jieba with its reason; corruption/provenance failures block
execution. Runtime never downloads dependencies, invokes pip, imports a system
OpenCC, or silently changes the selected algorithm.

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
