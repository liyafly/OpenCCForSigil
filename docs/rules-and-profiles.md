# Rules and profiles

Use the conversion settings toolbar to manage profiles, save the current
settings as a named profile, or open the rule manager. Profiles live in the
plugin user-data `profiles/` directory and reference separate `rules/` sets.
Loading a profile does not widen the XHTML selection confirmed earlier.

Rules separate action, match type, and stage. Legacy `exact` rules still mean
final wording: the full source match is written directly and bypasses OpenCC,
quotation, and punctuation changes. `protect` preserves the original match.
New rules may use plain text or the bundled `regex` VERSION1 engine. Pre-
replacements run on unlocked original text before OpenCC; post-replacements run
after OpenCC, quotation, and punctuation processing. A stage matches its input
once, so replacements do not cascade within that stage. Provenance is
`UserRule:<id>`.

Regular expressions only match one extracted text fragment or allowed
attribute value; they do not cross markup or operate on whole XHTML. The plugin
rejects zero-length matches and bounds pattern size, per-rule and total hits,
replacement output, and total matching time. A timeout or exceeded limit stops
the entire analysis before it can produce a partial writeback plan. The rule
manager includes templates for author-credit protection, marked text,
contextual replacement, and horizontal whitespace cleanup.

Rules have an explicit standard direction (all 16 are supported) or `*`, and
global, profile, or book scope. Jieba runs use the corresponding standard rule
direction. Book rules use a hashed metadata identifier, falling back to the
saved EPUB path; an unsaved book without an identifier cannot own book rules.
They are never embedded into the EPUB.

The `tw2sp` workflow includes narrow built-in protections for author-credit
markers `◎【著】`, `◎著`, `◎ 著`, and `◎　著`, also when Jieba segmentation is
enabled. This keeps the credit label intact without preventing ordinary text
such as `慰藉著` from becoming `慰藉着`. A bare `著` without a distinguishing
marker is ambiguous and is not protected globally. The rule manager displays a
short guide; the installable ZIP includes `OpenCCForSigil/resources/rule-guide.md`
with examples for adding and testing other exact/protect rules.

Protection wins first. V1 retains its book, global, profile ordering; V2 uses
book, current profile, global, then built-in scope. At the same precedence,
longer actual matches win before the advanced priority. Conflicting
same-source targets at the same precedence block planning; ambiguous dynamic
regex matches with different outputs stop at that text position. Owners of
separate profile/book scopes are independent.

Import/export supports TSV, CSV, JSON, and OpenCC TXT. TXT import requires an
explicit direction. Import diagnostics and conflicts are visible before
saving. The text-only sandbox displays rule and conversion stages. The
read-only inspector independently compares official configs on the original
input and labels the result as comparative classification, never as an
internal dictionary-hit trace.

Every plan freezes a rule hash, profile hash, backend provenance, and source
hash. Stage replacements map final changes back to original source offsets;
changes that depend on one replacement share a preview decision group. Editing
rule/profile storage after preview blocks commit and requires a new analysis.
Return to settings discards the old plan and preview decisions. Saved legacy
rules retain their prior semantics and are not migrated into replacements.
