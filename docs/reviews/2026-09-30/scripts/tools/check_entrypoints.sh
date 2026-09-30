#!/bin/sh
# FU-06: run the review tools that later commits broke; print one status line each.
# Run from the repository root. Output goes to $OUT (default: a new temp dir).
OUT=${OUT:-$(mktemp -d /tmp/opencc-fu06.XXXXXX)}
mkdir -p "$OUT"
QT="mise exec -- uv run --with PySide6==6.11.2 python"
PY="mise exec -- uv run python"
export QT_QPA_PLATFORM=offscreen

run() {
  name=$1; shift
  "$@" > "$OUT/$name.log" 2>&1
  code=$?
  last=$(grep -E 'Error|error:|FAILED|Traceback' "$OUT/$name.log" | tail -1 | cut -c1-110)
  echo "$name exit=$code ${last}"
}

run probe_ux_simplicity $QT docs/reviews/2026-09-28/scripts/ux/probe_ux_simplicity.py --output "$OUT/ux"
run benchmark_preview_ui_small $QT docs/reviews/2026-09-28/scripts/perf/benchmark_preview_ui.py \
  --files 20 --paragraphs 50 --repeats 3 --output "$OUT/bench.json"
run probe_followup $PY docs/reviews/2026-09-27/scripts/probe_followup.py --output "$OUT/followup.json"
run a10_export_roundtrip $PY docs/reviews/2026-09-24/scripts/round3/a10_export_roundtrip.py
run test_review_regressions $PY -m pytest docs/reviews/2026-09-26/scripts/test_review_regressions.py -q -p no:cacheprovider
run rule06_import_formats $PY docs/reviews/2026-09-28/scripts/rules/rule06_import_formats.py
run probe_edge_cases $PY docs/reviews/2026-09-28/scripts/rules/probe_edge_cases.py
run fix07_fix08_import_edges $PY docs/reviews/2026-09-29/scripts/rules/fix07_fix08_import_edges.py
echo "logs: $OUT"
