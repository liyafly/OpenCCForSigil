import pytest

from app.session import Session, SessionState


def test_session_rejects_invalid_transition():
    session = Session()
    with pytest.raises(ValueError):
        session.transition(SessionState.COMMITTING)
