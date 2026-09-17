"""Scaffold smoke tests."""

from importlib.metadata import version

import tessera_x


def test_package_imports():
    assert tessera_x.__version__ == "0.1.0"
    assert tessera_x.__version__ == version("tessera-x")


def test_version_is_string():
    assert isinstance(tessera_x.__version__, str)
    assert len(tessera_x.__version__) > 0
