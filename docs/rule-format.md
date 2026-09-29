# Rule format

Rules are directional overlays; bundled official OpenCC dictionaries remain
read-only. See [rules and profiles](rules-and-profiles.md) for stages,
precedence, scopes, immutable snapshots, and the manager/sandbox/inspector.

A rule carries `id`, `enabled`, `type`, `direction`, `source`, `target`, `scope`,
`priority`, and optional profile/book ownership. V2 rules also carry `action`,
`match_type`, and `stage`. Missing directions, malformed text, invalid IDs,
unsupported schemas, invalid regex syntax/templates, and patterns matching the
empty input are rejected. A zero-width match found in actual text is skipped;
analysis continues and reports only the rule ID and skip count. Existing V1
`exact` rules remain final wording and V1 `protect` rules remain source-preserving.

`action` is `protect`, `override`, or `replace`; `match_type` is `literal` or
`regex`; `stage` is `source`, `pre`, or `post`. Protect and override rules are
source-stage locks. Replace rules use the pre or post stage. Final patches are
mapped back to the original text and escaped for their XML text or attribute
context by the source-preserving planner.

Regex patterns use the bundled `regex` VERSION1 dialect. They match only one
extracted text fragment or an explicitly allowed attribute value. The
runtime skips each zero-length match and enforces a 512-character pattern cap,
512 applied hits per rule per text fragment and stage, and 100,000 applied hits
per analysis. Overlapping candidates do not count as applied hits; candidate
enumeration is separately capped at 20,000 per rule per text fragment to bound
memory. Per analysis, the selected replacement output cap and the combined
candidate expansion output cap are each 2,000,000 characters. Each regex call is limited to 50 ms, and
the total runtime allowance is 3 seconds plus 2 seconds per million characters
scanned. These limits are centralized in
`rules/matching.py`. A timeout or exceeded limit aborts planning; it does not
return a partial plan.

JSON preserves every field. TSV and CSV rows can contain `source<Tab>target`,
`source<Tab>target<Tab>comment`, or
`direction<Tab>source<Tab>target<Tab>comment`. The first two forms use the
direction selected in the import dialog. A header on the first row is skipped
only when it includes both a recognized source label and a recognized target
label. OpenCC TXT uses `source<Tab>target` and requires a selected direction.
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
