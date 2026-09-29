from pathlib import Path

import app.controller as controller
from app.profiles import Profile
from tools.validate_artifact import _REQUIRED_MEMBERS


def test_controller_default_comes_from_profile_without_duplicate_resource():
    root = Path(__file__).resolve().parents[2]
    resource = root / "plugin/OpenCCForSigil/resources/defaults/conservative.json"
    package_member = "OpenCCForSigil/resources/defaults/conservative.json"

    assert Profile().conversion == "s2t"
    assert not hasattr(controller, "_load_conservative_profile")
    assert not resource.exists()
    assert package_member not in _REQUIRED_MEMBERS
