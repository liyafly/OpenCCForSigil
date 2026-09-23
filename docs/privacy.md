# Privacy defaults

Preferences, profiles, rule sets, JSONL logs, history, and exports are stored
under the plugin's user-data directory, never inside the EPUB or bundled data.
Conversion and self-tests run locally without runtime downloads.

Persisted history contains completed-session summaries, counts, file IDs,
source/result hashes, backend provenance, and the EPUB filename basename when
the host supplies a path. It does not store the full path, EPUB title metadata,
book bodies, or full diff. Cancelled/failed runs retain their structured
session log and status.

Markdown/JSON reports default to the same metadata. During Preview, the user
may explicitly check **Include full diff** and choose an export path; that
export can include source/target text from in-memory changes. Historical
records cannot reconstruct text that was never stored.

Retention cleanup is an explicit service operation, with defaults of 50
sessions / 30 days. It only removes corresponding plugin-owned history and
UUID session logs, skips symlinks, and never deletes profiles, rules, EPUBs,
or manually exported reports. Conversion never automatically runs cleanup.
