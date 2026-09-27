from ui.run_summary import run_summary_data


def test_run_summary_counts_only_selected_xhtml_and_lists_whole_book_additions():
    summary = run_summary_data(
        ("one.xhtml", "two.xhtml", "nav.xhtml"), "nav.xhtml", "s2twp",
        {"include_nav": True, "include_ncx": True, "include_metadata": True,
         "force_pivot": True},
    )

    assert summary == {
        "file_count": 3,
        "config": "s2twp",
        "nav_available": True,
        "nav_requested": True,
        "nav_included": True,
        "additions": ("ncx", "metadata"),
        "risks": ("pivot", "metadata"),
    }


def test_run_summary_explains_unavailable_navigation_without_counting_it():
    summary = run_summary_data(
        ("one.xhtml", "two.xhtml"), "nav.xhtml", "s2t",
        {"include_nav": True},
    )

    assert summary["file_count"] == 2
    assert not summary["nav_available"]
    assert not summary["nav_included"]


def test_run_summary_preserves_an_effective_optional_backend_configuration():
    summary = run_summary_data(("one.xhtml",), None, "s2t_jieba", {})

    assert summary["config"] == "s2t_jieba"


def test_run_summary_keeps_but_marks_unavailable_risky_preferences():
    summary = run_summary_data(
        ("one.xhtml",), "nav.xhtml", "s2t_jieba",
        {"include_nav": True, "include_metadata": True,
         "metadata_available": False, "force_pivot": True},
    )

    assert summary["nav_requested"] and not summary["nav_available"]
    assert summary["risks"] == ("pivot_inactive", "metadata_inactive")
    assert summary["additions"] == ("metadata_unavailable",)
