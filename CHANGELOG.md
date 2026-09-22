# Changelog

## Unreleased

- Bound long-text preview alignment work without splitting OpenCC conversion
  input. Ambiguous large regions are shown as one exact replacement; accepting
  all changes still reproduces the official result exactly.

- Separate standard conversion preflight from optional native Jieba probing.
  A verified Jieba library that cannot load on the host disables the advanced
  option and reports its reason without blocking standard conversion. A
  selected Jieba configuration never falls back to another algorithm, and
  payload/hash/provenance failures remain blocking (spec §4.4.1, §4.5.5).
