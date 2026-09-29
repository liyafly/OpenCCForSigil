"""Test helpers for driving the Preview batch-decision dialog."""


def apply_batch_decision(
    monkeypatch,
    dialog,
    *,
    scope="all",
    action="accept",
    only_undecided=True,
    confirm=True,
):
    """Set the batch dialog controls and submit or cancel the decision."""
    from ui import preview_window

    result = {}

    def drive_batch(batch_dialog):
        children = batch_dialog._layout.children
        form = next(
            item for item in children if isinstance(item, dialog._qt.QFormLayout)
        )
        scope_combo = form.children[0][1]
        action_combo = form.children[1][1]
        only_check = next(
            item for item in children if isinstance(item, dialog._qt.QCheckBox)
        )
        scope_combo.setCurrentIndex(scope_combo.findData(scope))
        action_combo.setCurrentIndex(action_combo.findData(action))
        only_check.setChecked(only_undecided)
        result["summary"] = children[2].text()
        return 1 if confirm else 0

    monkeypatch.setattr(preview_window, "exec_dialog", drive_batch)
    dialog._open_batch_decision(initial_scope=scope)
    return result.get("summary", "")
