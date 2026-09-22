# Implementation status and acceptance boundaries

The V1 document, rule/profile, transform, preview, and report services are
connected to the Sigil controller. The former skeleton-only status is obsolete.
Regex rules, vertical punctuation, SVG/MathML enhancement, and review
annotations remain V1.1 scope and are not silently enabled by a V1 profile.

## Deliberate implementation choices

- Source-span patching takes precedence over the older metadata-serialization
  wording. XML processing uses the standard-library Expat parser. XHTML syntax
  verification uses a validation copy with declarations excluded and named
  references represented without expansion; it does not validate a remote DTD.
  Original entity spellings and bytes outside planned patches are preserved.
- Language proposals update existing Chinese values. Missing language values
  are not synthesized; non-Chinese and explicit non-Han scripts are preserved.
- A loaded profile never widens the target set already confirmed in the scope
  picker. Scope selection remains explicit on every invocation.
- Native conversion cannot be forcibly interrupted mid-call. Worker cancellation
  is cooperative at target boundaries and never writes a partial plan.
- Completed conversions enter history; cancelled/failed sessions remain in their
  JSONL log and summary. Reports persist full diff only on explicit export.

## Evidence is not interchangeable

Local automated tests and Sigil's bundled macOS Qt construction/action smoke
checks cover the new workflow. CI separately builds/tests four CPython 3.14
payloads and validates the final Fat Plugin's hashes and native baselines.
Neither proves old-host compatibility or install/apply/save/reopen acceptance
in Windows, Linux, macOS Intel, and macOS arm64 Sigil.

The user's previous acceptance covers the previous tested artifact. The newly
built package needs its own real-host acceptance; previously noted minor UI
polish remains deferred. Release notes record these boundaries for each tagged
package. A local package contains only the checked-in host payload; use the
published release Fat Plugin or commit-named CI Fat Plugin for cross-platform
installation.
