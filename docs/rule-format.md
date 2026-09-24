# Rule format

Rules are implemented as directional exact/protect overlays; bundled official
OpenCC dictionaries remain read-only. See [rules and profiles](rules-and-profiles.md)
for precedence, scopes, immutable snapshots, and the manager/sandbox/inspector.

A rule carries `id`, `enabled`, `type`, `direction`, `source`, `target`, `scope`,
`priority`, and optional profile/book ownership. Missing directions, malformed
text, invalid IDs, unsupported schemas, and V1.1 regex rules are rejected.
A `protect` target equals its source. An exact replacement can change length,
and is escaped appropriately when patched into XML text or an attribute.
Protect rules take precedence over any overlapping conversion rule, regardless
of which rule starts first.

JSON preserves every field. Delimited import/export and OpenCC TXT are useful
for exchanging terms; TXT requires the direction to be selected explicitly.
Imports report duplicates, invalid records, and blocking conflicts before save.
