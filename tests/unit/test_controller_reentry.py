from app.controller import Controller
from app.session import SessionState


def test_controller_rejects_reentrant_run_while_current_run_is_active(tmp_path, monkeypatch):
    controller = Controller(object(), data_dir=tmp_path / "plugin-data")
    calls = []

    def run_once():
        calls.append("run-once")
        assert controller.run() == 1
        return 7

    monkeypatch.setattr(controller, "_run_once", run_once)

    assert controller.run() == 7
    assert calls == ["run-once"]


def test_controller_rejects_run_after_terminal_session(tmp_path, monkeypatch):
    controller = Controller(object(), data_dir=tmp_path / "plugin-data")
    controller.session.state = SessionState.COMPLETED
    monkeypatch.setattr(
        controller,
        "_run_once",
        lambda: (_ for _ in ()).throw(AssertionError("terminal session restarted")),
    )

    assert controller.run() == 1
