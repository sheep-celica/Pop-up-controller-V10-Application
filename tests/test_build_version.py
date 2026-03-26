from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_build_version_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "build_version.py"
    spec = importlib.util.spec_from_file_location("build_version", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_version_reads_current_version_from_custom_file(tmp_path: Path) -> None:
    module = _load_build_version_module()
    version_file = tmp_path / "__init__.py"
    version_file.write_text('__version__ = "1.2.3"\n', encoding="utf-8")

    assert module.current_version(version_file) == "1.2.3"


def test_build_version_normalizes_versions_and_tags() -> None:
    module = _load_build_version_module()

    assert module.normalize_version("1.2.3") == "1.2.3"
    assert module.normalize_version("v1.2.3") == "1.2.3"
    assert module.version_from_tag("v2.4.6") == "2.4.6"


def test_build_version_updates_custom_file(tmp_path: Path) -> None:
    module = _load_build_version_module()
    version_file = tmp_path / "__init__.py"
    version_file.write_text('__version__ = "1.2.3"\n', encoding="utf-8")

    new_version = module.set_version("v1.2.4", version_file)

    assert new_version == "1.2.4"
    assert version_file.read_text(encoding="utf-8") == '__version__ = "1.2.4"\n'
