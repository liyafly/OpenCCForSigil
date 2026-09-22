# Navigation, metadata, and language tags

The scope dialog freezes the selected XHTML files. The conversion settings
can exclude the EPUB navigation document from that selection, but never add
unselected XHTML files. NCX and OPF metadata are separate, opt-in targets.

NCX conversion includes `docTitle`, `docAuthor`, and `navLabel` text only.
Metadata conversion includes Dublin Core title, creator, contributor,
publisher, description, and subject, and author `file-as`/`alternate-script`
refinements. Identifiers, dates, URLs, namespace declarations, and other
attributes are preserved. Metadata changes are marked high risk.

Language settings default to Keep. Suggest and Force propose changes to
existing Chinese `lang`, `xml:lang`, and `dc:language` values. They preserve
other languages and explicit non-Han scripts. Generic traditional conversion
uses `zh-Hant` with the BCP 47 preset; Legacy requires an explicit Taiwan or
Hong Kong choice for Force and makes no proposal for an unspecified Suggest.
Japanese directions do not propose Chinese tags. Missing language values are
not synthesized. Every language change belongs to one indivisible preview
group across the selected documents and metadata.

XML parsing locates source spans; it never serializes the document. Comments,
processing instructions, CDATA delimiters, whitespace, and entity references
remain in their original form. Malformed XML or custom entity declarations
block the plan before any book write. External DTDs are not fetched.

All selected content, including the metadata fragment obtained through Sigil's
metadata API, is frozen and hashed. Preview, staging, verification, and a
second source hash check precede the sole write boundary. Controlled tests
cover these guards and group decisions; they do not constitute installation,
save, and reopen acceptance on every supported Sigil host.
