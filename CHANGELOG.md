# Changelog

## Unreleased

- Separate standard conversion preflight from optional native Jieba probing.
  A verified Jieba library that cannot load on the host disables the advanced
  option and reports its reason without blocking standard conversion. A
  selected Jieba configuration never falls back to another algorithm, and
  payload/hash/provenance failures remain blocking (spec §4.4.1, §4.5.5).
