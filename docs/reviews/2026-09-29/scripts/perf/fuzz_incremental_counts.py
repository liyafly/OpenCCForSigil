# ruff: noqa: E401, E402, E701, E702, E731, F401, F811, F841
"""PERF-05 guard: incremental preview counts equal a full recomputation.

Run from the repository root. Read-only: uses temporary directories, never the user's data.
"""
import os
import sys
from pathlib import Path

REPO = Path(os.environ.get("OPENCC_SIGIL_REPO", Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(REPO / "plugin" / "OpenCCForSigil"))
sys.path.insert(0, str(REPO))

"""Random action sequences on the fake-Qt preview dialog; after each action compare
incremental counts/visible rows/model rows with a from-scratch recomputation."""
import random, sys
from types import SimpleNamespace
from core.models import ConversionPlan, SourceSpan, TokenChange
from core.preview import PreviewSession
from tests.support.fake_qt import make_with_table
from ui.i18n import Translator
from ui.preview_window import _PreviewDialog

def build(rng):
    files = [f"f{i}.xhtml" for i in range(rng.randint(1, 5))]
    planned, previews = [], []
    cross_group = "rules:cross"
    for fi, file_id in enumerate(files):
        changes = []
        for ci in range(rng.randint(1, 14)):
            r = rng.random()
            if r < 0.2: group = f"rules:g{fi}-{ci // 3}"
            elif r < 0.3: group = cross_group
            elif r < 0.38: group = "language_metadata"
            else: group = ""
            changes.append(TokenChange(
                source=rng.choice("甲乙丙"), target=rng.choice("丁戊"),
                span=SourceSpan(ci * 2, ci * 2 + 1),
                rule_source=rng.choice(("OpenCC:s2t", "UserRule:a")),
                change_id=f"{fi}-{ci}", file_id=file_id,
                category=rng.choice(("character", "phrase")), risk=rng.choice(("LOW", "HIGH")),
                group_id=group))
        p = PreviewSession(ConversionPlan(source_sha256="", file_id=file_id, changes=tuple(changes)))
        previews.append(p)
        planned.append(SimpleNamespace(source=SimpleNamespace(file_id=file_id, href=f"Text/{file_id}", document_kind="xhtml"), plan=p.plan))
    d = _PreviewDialog(make_with_table(), tuple(planned), tuple(previews), Translator("en"))
    d._confirm_filtered_group_expansion = lambda *a: True
    return d

def check(d, step, action):
    inc = (dict(d._totals), dict(d._file_filter_counts), dict(d._accepted_count_by_file))
    vis = d._visible_entries_cache
    model_rows = d.table_model.rows.entries
    d._recompute_counts()
    ref = (dict(d._totals), dict(d._file_filter_counts), dict(d._accepted_count_by_file))
    ids = lambda es: [(c.file_id, c.change_id) for _p, c in es]
    exp = d._visible_entries()
    problems = []
    if inc != ref: problems.append(f"counts {inc} != {ref}")
    if ids(vis) != ids(exp): problems.append(f"visible {ids(vis)} != {ids(exp)}")
    if ids(model_rows) != ids(vis): problems.append("model rows != visible cache")
    if problems:
        raise AssertionError(f"step {step} after {action}: " + "; ".join(problems))

ACTIONS = ["accept_this", "reject_this", "accept_file", "reject_file", "accept_group",
           "reject_group", "filtered_accept", "filtered_reject", "reset", "undo", "redo",
           "status", "file_filter", "move", "accept_all", "reject_all"]
failures = 0
for seed in range(int(sys.argv[1]) if len(sys.argv) > 1 else 400):
    rng = random.Random(seed)
    d = build(rng)
    try:
        for step in range(40):
            action = rng.choice(ACTIONS)
            if action == "accept_this": d._accept_this()
            elif action == "reject_this": d._reject_this()
            elif action == "accept_file": d._accept_file()
            elif action == "reject_file": d._reject_file()
            elif action == "accept_group": d._decide_current_file_groups(True)
            elif action == "reject_group": d._decide_current_file_groups(False)
            elif action == "filtered_accept": d._decide_filtered(True)
            elif action == "filtered_reject": d._decide_filtered(False)
            elif action == "reset": d._reset_current_to_undecided()
            elif action == "undo": d._undo_preview_action()
            elif action == "redo": d._redo_preview_action()
            elif action == "accept_all": d._accept_all()
            elif action == "reject_all": d._reject_all()
            elif action == "status":
                combo = d.status_filter
                combo.setCurrentIndex(rng.randrange(combo.count()))
            elif action == "file_filter":
                combo = d.file_filter
                combo.setCurrentIndex(rng.randrange(combo.count()))
            elif action == "move":
                n = len(d._visible_entries_cache)
                if n: d._set_current_row(rng.randrange(n))
            check(d, step, action)
    except AssertionError as exc:
        failures += 1
        if failures <= 5: print(f"seed {seed}: {exc}")
print(f"seeds={seed + 1} failures={failures}")
