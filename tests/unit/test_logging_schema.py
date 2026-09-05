import json

from logging_ext.logger import SessionLogger


def test_logger_writes_jsonl_event_and_summary(tmp_path):
    logger = SessionLogger(tmp_path / "logs", plugin_version="0.0.1-beta", session_id="session-1")
    logger.event("state_transition", from_state="idle", to_state="scanning")
    logger.summary({"status": "success"})

    event = json.loads(logger.log_path.read_text(encoding="utf-8").splitlines()[0])
    summary = json.loads(logger.summary_path.read_text(encoding="utf-8"))
    assert event["session_id"] == "session-1"
    assert event["event"] == "state_transition"
    assert summary["schema_version"] == 1
    assert summary["status"] == "success"
