"""Pure scope planning for atomic preview batch decisions."""

from dataclasses import dataclass

from core.preview import PreviewGroupKind, preview_group_kind


def _bucket(decision):
    if decision is None:
        return "undecided"
    value = getattr(decision, "value", str(decision)).lower()
    return "accepted" if value.startswith("accept") else "skipped"


@dataclass(frozen=True)
class BatchDecisionPlan:
    entries: tuple
    change_count: int
    group_count: int
    file_count: int
    hidden_count: int
    overwrite_count: int
    excluded_mixed_groups: int
    excluded_mixed_changes: int
    excluded_language_groups: int
    excluded_other_groups: int


def plan_batch_decision(
    entries,
    group_entries,
    group_file_ids,
    *,
    scope="filtered",
    visible_identities=(),
    visible_change_ids=(),
    file_id=None,
    accepted=True,
    undecided_only=True,
):
    """Expand a chosen range to complete atomic groups and count real changes.

    ``entries`` and group maps are the preview's existing frozen structures.
    The result holds references to existing entries and never copies text.
    """
    if scope not in {"filtered", "file", "all"}:
        raise ValueError("unknown batch scope")
    visible = set(visible_identities) if scope == "filtered" else set()
    visible_objects = set(visible_change_ids) if scope == "filtered" else set()
    target_bucket = "accepted" if accepted else "skipped"
    selected = []
    seen_groups = set()
    group_count = 0
    hidden_count = 0
    overwrite_count = 0
    excluded_mixed_groups = 0
    excluded_mixed_changes = 0
    excluded_language_groups = 0
    excluded_other_groups = 0
    files = set()

    def consider_unit(unit, group_id=None):
        nonlocal group_count, hidden_count, overwrite_count
        nonlocal excluded_mixed_groups, excluded_mixed_changes
        decisions = tuple(preview.decision(change.change_id)
                          for preview, change in unit)
        buckets = tuple(_bucket(decision) for decision in decisions)
        if undecided_only:
            if any(bucket != "undecided" for bucket in buckets):
                if any(bucket == "undecided" for bucket in buckets):
                    excluded_mixed_changes += sum(bucket == "undecided" for bucket in buckets)
                    excluded_mixed_groups += int(group_id is not None)
                return
        changes = tuple(
            entry for entry, bucket in zip(unit, buckets) if bucket != target_bucket
        )
        if not changes:
            return
        selected.extend(changes)
        group_count += int(group_id is not None)
        if scope == "filtered" and group_id is not None:
            hidden_count += sum(
                ((change.file_id, change.change_id) not in visible
                 and id(change) not in visible_objects)
                for _preview, change in unit
            )
        overwrite_count += sum(
            bucket in {"accepted", "skipped"} and bucket != target_bucket
            for bucket in buckets
        )
        files.update(change.file_id for _preview, change in changes)

    for preview, change in entries:
        group_id = change.group_id
        if group_id:
            if group_id in seen_groups:
                continue
            seen_groups.add(group_id)
            unit = group_entries.get(group_id, ((preview, change),))
            if scope == "filtered":
                if not any(((item.file_id, item.change_id) in visible
                            or id(item) in visible_objects)
                           for _session, item in unit):
                    continue
            elif scope == "file":
                unit_files = group_file_ids.get(group_id, frozenset())
                if file_id not in unit_files:
                    continue
                if (len(unit_files) != 1
                        or preview_group_kind(group_id) is PreviewGroupKind.LANGUAGE_METADATA):
                    if preview_group_kind(group_id) is PreviewGroupKind.LANGUAGE_METADATA:
                        excluded_language_groups += 1
                    else:
                        excluded_other_groups += 1
                    continue
            consider_unit(unit, group_id)
            continue

        if (scope == "filtered" and (change.file_id, change.change_id) not in visible
                and id(change) not in visible_objects):
            continue
        if scope == "file" and change.file_id != file_id:
            continue
        consider_unit(((preview, change),))

    return BatchDecisionPlan(
        tuple(selected), len(selected), group_count, len(files), hidden_count,
        overwrite_count, excluded_mixed_groups, excluded_mixed_changes,
        excluded_language_groups, excluded_other_groups,
    )
