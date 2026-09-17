"""Scaffold smoke tests."""

import tessera_x


def test_package_imports():
    assert tessera_x is not None


def test_version_is_string():
    assert isinstance(tessera_x.__version__, str)
