# Deviations

No architecture deviation from the v1.4 engineering specification is recorded.
The current implementation has completed the official-binding runtime boundary
and checked in one verified macOS arm64/cp314 payload.

The deliberate remaining scope is the complete multi-platform Fat Plugin
payload set plus the document processor, UI, and conversion pipeline. The
manifest and CI build each target platform from exact official wheels and the
same-release official native plugin; no unverified platform payload is declared
as released.
