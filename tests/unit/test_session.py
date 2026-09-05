import pytest

from app.session import Session, SessionState


def test_session_uses_explicit_phase0_noop_path():
    session = Session()
    session.transition(SessionState.SCANNING)
    session.transition(SessionState.ANALYZING)
    session.transition(SessionState.PLANNED)
    session.complete_noop()
    assert session.state is SessionState.COMPLETED


def test_session_rejects_invalid_transition():
    session = Session()
    with pytest.raises(ValueError):
        session.transition(SessionState.COMMITTING)
