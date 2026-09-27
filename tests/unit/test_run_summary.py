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
