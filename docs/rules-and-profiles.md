# Rules and profiles

Use the conversion settings toolbar to manage profiles, save the current
settings as a named profile, or open the rule manager. Profiles live in the
plugin user-data `profiles/` directory and reference separate `rules/` sets.
Loading a profile does not widen the XHTML selection confirmed earlier.

Exact rules replace literal text. Protect rules keep literal text unchanged.
Both lock their matched source spans before conversion; their output bypasses
OpenCC, quotation changes, and punctuation changes. The remaining segments
use the selected official config. Rule provenance is `UserRule:<id>`.

Rules have an explicit standard direction (all 16 are supported) or `*`, and
global, profile, or book scope. Jieba runs use the corresponding standard rule
direction. Book rules use a hashed metadata identifier, falling back to the
saved EPUB path; an unsaved book without an identifier cannot own book rules.
They are never embedded into the EPUB.

The `tw2sp` workflow includes a narrow built-in protection for the author
credit marker `◎【著】`, also when Jieba segmentation is enabled. This keeps
the credit label intact without preventing ordinary text such as `慰藉著`
from becoming `慰藉着`. The rule manager displays a short guide; the installable
ZIP includes `OpenCCForSigil/resources/rule-guide.md` with field-by-field
examples for adding and testing other exact/protect rules.

Protection wins first, followed by book, global, and profile scope; within a
tier, longest matches win, then priority and stable rule ID. Conflicting
same-source targets at the same precedence block planning. Owners of separate
profile/book scopes are independent.

Import/export supports TSV, CSV, JSON, and OpenCC TXT. TXT import requires an
explicit direction. Import diagnostics and conflicts are visible before
saving. The text-only sandbox displays rule and conversion stages. The
read-only inspector independently compares official configs on the original
input and labels the result as comparative classification, never as an
internal dictionary-hit trace.

Every plan freezes a rule hash, profile hash, backend provenance, and source
hash. Editing rule/profile storage after preview blocks commit and requires a
new analysis. Return to settings discards the old plan and preview decisions.
Regex rules and other V1.1 features are rejected instead of being silently
enabled.
