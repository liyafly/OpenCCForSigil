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

## Example: protect an author-credit marker

The built-in `tw2sp` protections cover `◎【著】`, `◎著`, and the common
spaced forms `◎ 著` and `◎　著`, including when Jieba segmentation is selected.
If the text has no distinguishing marker and contains only `著`, it cannot be
protected safely in every context: ordinary text such as `慰藉著` should
convert to `慰藉着`. Use a longer, book-specific literal only when that full
text uniquely identifies the credit, and test nearby prose in the sandbox.

To protect a different literal expression, open **Rules / sandbox** and add a
protect rule. For example, to keep `【编者】` only in one EPUB, use:

| Field | Value |
| --- | --- |
| Type | `protect` |
| Direction | The conversion direction, such as `tw2sp` |
| Source | `【编者】` |
| Target | Leave blank; protect rules use the source as their target |
| Scope | `book` / Current book |

Use `global` / Global for every book, or `profile` / Current profile to limit
the rule to a named profile. Then enter representative text in the sandbox,
select **Test**, and confirm both the protected phrase and neighboring text
before saving. The detailed guide is also shipped at
`OpenCCForSigil/resources/rule-guide.md` inside the installable ZIP.
