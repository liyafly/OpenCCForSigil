# Rule format

Rules are directional overlays; bundled official OpenCC dictionaries remain
read-only. See [rules and profiles](rules-and-profiles.md) for stages,
precedence, scopes, immutable snapshots, and the manager/sandbox/inspector.

A rule carries `id`, `enabled`, `type`, `direction`, `source`, `target`, `scope`,
`priority`, and optional profile/book ownership. V2 rules also carry `action`,
`match_type`, and `stage`. Missing directions, malformed text, invalid IDs,
unsupported schemas, invalid regex syntax/templates, and zero-length regex
matches are rejected. Existing V1 `exact` rules remain final wording and V1
`protect` rules remain source-preserving.

`action` is `protect`, `override`, or `replace`; `match_type` is `literal` or
`regex`; `stage` is `source`, `pre`, or `post`. Protect and override rules are
source-stage locks. Replace rules use the pre or post stage. Final patches are
mapped back to the original text and escaped for their XML text or attribute
context by the source-preserving planner.

Regex patterns use the bundled `regex` VERSION1 dialect. They match only one
extracted text fragment or an explicitly allowed attribute value. The
runtime rejects zero-length matches and enforces a 512-character pattern cap,
512 hits per rule, 4096 hits per analysis, a 2,000,000-character replacement
output cap, 50 ms per regex call, and a 3 s total regex budget. These limits
are centralized in `rules/matching.py` for adjustment from representative
book and host measurements. A timeout or exceeded limit aborts planning; it
does not return a partial plan.

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
