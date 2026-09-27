from ui.history_filters import filter_history_records
from ui.i18n import Translator


def _records():
    return tuple({
        "session_id": f"session-{index:04d}",
        "recorded_at": f"2026-09-{(index % 28) + 1:02d}T00:00:00+00:00",
        "summary": {
            "book_label": "中文 Book 7" if index % 17 == 7 else f"Book {index % 17}",
            "profile_id": "profile-read" if index % 3 else "profile-other",
            "config": ("s2t", "s2tw", "t2s", "s2t")[index % 4],
            "status": ("success", "failed", "unknown_state")[index % 3],
        },
        "provenance": {"message": "private prose is not searchable"},
    } for index in range(1000))


def test_thousand_history_rows_use_anded_metadata_filters_and_normal_text():
    records = _records()
    names = {"profile-read": "Taiwan Reading Profile", "profile-other": "Other"}
    tr = Translator("en")
    filtered = filter_history_records(
        records, query="  bOoK 7 ", status="success", direction="s2tw",
        profile_names=names, translator=tr)
    expected = [record for index, record in enumerate(records)
                if index % 17 == 7 and index % 3 == 0 and index % 4 == 1]

    assert filtered == expected
    assert len(filter_history_records(records, translator=tr)) == 1000
    assert filter_history_records(records, query="中文", translator=tr) == [
        record for record in records if "中文" in record["summary"]["book_label"]]
    assert filter_history_records(records, query="taiwan reading", profile_names=names,
                                   translator=tr) == [
        record for record in records if record["summary"]["profile_id"] == "profile-read"]
    assert filter_history_records(records, query="s2tw", translator=tr) == [
        record for record in records if record["summary"]["config"] == "s2tw"]
    assert filter_history_records(records, query="missing", translator=tr) == []
    assert filter_history_records(records, query="private prose", translator=tr) == []


def test_same_book_sessions_remain_distinct_by_session_id():
    records = (
        {"session_id": "first", "summary": {"book_label": "Same book"}},
        {"session_id": "second", "summary": {"book_label": "Same book"}},
    )

    assert [item["session_id"] for item in filter_history_records(
        records, query="same book")] == ["first", "second"]


def test_unknown_status_is_an_exact_filter_value():
    records = _records()

    assert len(filter_history_records(records, status="unknown_state")) == 333
