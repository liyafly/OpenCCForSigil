# Implementation status and acceptance boundaries

The V1 document, rule/profile, transform, preview, and report services are
connected to the Sigil controller. Guarded literal/regex rule actions and
pre/post replacement stages are implemented in v0.2.5. Numeric Han character
reference decoding is an opt-in run setting. MathML's low-level profile option
converts `mtext` only and leaves identifiers protected; broader SVG/MathML
support and review annotations remain deferred. The 2026-09-27 preview additions
and their limits are recorded in the [implementation results](reviews/2026-09-27/02-implementation-results.md).

## Deliberate implementation choices

- Source-span patching takes precedence over the older metadata-serialization
  wording. XML processing uses the standard-library Expat parser. XHTML syntax
  verification uses a validation copy with declarations excluded and named
  references represented without expansion; it does not validate a remote DTD.
  Original entity spellings and bytes outside planned patches are preserved.
- Language proposals update existing Chinese values. Missing language values
  are not synthesized; non-Chinese and explicit non-Han scripts are preserved.
- CDATA content is excluded from conversion targets in both XHTML and NCX.
- A loaded profile never widens the target set already confirmed in the scope
  picker. Scope selection remains explicit on every invocation.
- The read-only Dictionary Inspector (spec §86, SHOULD) is shown inline in the
  rule test output instead of a separate dialog.
- Rule sets created since v0.2.5 (semantic version 2) accept any non-empty source;
  the whitespace/punctuation-only source rejection of spec §11.8.3 applies to
  version 1 rules only. Scope precedence follows spec §11.2 (book > global >
  profile) for every rule.
- Native conversion cannot be forcibly interrupted mid-call. Worker cancellation
  is cooperative at target boundaries and never writes a partial plan.
- The optional Jieba probe constructs and exercises only `s2t_jieba`; all
  advertised Jieba configs share its verified native data, while the selected
  config is checked when its worker backend is constructed.
- Completed conversions enter history; cancelled/failed sessions remain in their
  JSONL log and summary. Reports persist full diff only on explicit export.

## Evidence is not interchangeable

Local automated tests and Sigil's bundled macOS Qt construction/action smoke
checks cover the new workflow. CI separately builds/tests six runtime payloads
(five CPython 3.14/cp314 targets and Linux x86_64/cp312) and validates the Fat
Plugin and platform package hashes and native baselines.
Neither proves old-host compatibility or install/apply/save/reopen acceptance
in Windows, Linux, macOS Intel, and macOS arm64 Sigil.

The user's previous acceptance covers the previous tested artifact. The newly
built package needs its own real-host acceptance; previously noted minor UI
polish remains deferred. Release notes record these boundaries for each tagged
package. A local package contains only the checked-in host payload; use the
published release Fat Plugin or commit-named CI Fat Plugin for cross-platform
installation.
