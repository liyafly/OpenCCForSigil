"""Pure display data for the scope and conversion settings summary."""


def run_summary_data(file_ids, nav_id, config, options):
    from core.transformation import FORCE_PIVOT_CHAINS

    selected = tuple(file_ids)
    nav_available = bool(nav_id and nav_id in selected)
    active_options = dict(options or {})
    additions = []
    if active_options.get("include_ncx"):
        additions.append("ncx")
    if active_options.get("include_metadata"):
        additions.append("metadata" if active_options.get("metadata_available", True)
                         else "metadata_unavailable")
    risks = []
    if active_options.get("force_pivot"):
        supported = any(chain[-1] == str(config) for chain in FORCE_PIVOT_CHAINS)
        risks.append("pivot" if supported else "pivot_inactive")
    if active_options.get("include_metadata"):
        risks.append("metadata" if active_options.get("metadata_available", True)
                     else "metadata_inactive")
    return {
        "file_count": len(selected),
        "config": str(config),
        "nav_available": nav_available,
        "nav_requested": bool(active_options.get("include_nav", True)),
        "nav_included": nav_available and bool(active_options.get("include_nav", True)),
        "additions": tuple(additions),
        "risks": tuple(risks),
    }
