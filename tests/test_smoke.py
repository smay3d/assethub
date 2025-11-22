# tests/test_smoke.py

from assethub import __version__


def test_version_exists() -> None:
    assert isinstance(__version__, str)
    assert len(__version__) > 0
