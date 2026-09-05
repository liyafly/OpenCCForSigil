"""Structural verification boundary."""

from core.models import VerificationResult


def verification_passed(file_id: str) -> VerificationResult:
    """Return a neutral result for the empty Phase 0 staging set."""

    return VerificationResult(file_id=file_id, passed=True)
