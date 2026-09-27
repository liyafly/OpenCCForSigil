"""Pure display data for the scope and conversion settings summary."""


def run_summary_data(file_ids, nav_id, config, options):
    selected = tuple(file_ids)
    nav_available = bool(nav_id and nav_id in selected)
    active_options = dict(options or {})
    additions = []
    if active_options.get("include_ncx"):
        additions.append("ncx")
    if active_options.get("include_metadata"):
        additions.append("metadata")
    risks = []
    if active_options.get("force_pivot"):
        risks.append("pivot")
    if active_options.get("include_metadata"):
        risks.append("metadata")
    return {
        "file_count": len(selected),
        "config": str(config),
        "nav_available": nav_available,
        "nav_included": nav_available and bool(active_options.get("include_nav", True)),
        "additions": tuple(additions),
        "risks": tuple(risks),
    }
