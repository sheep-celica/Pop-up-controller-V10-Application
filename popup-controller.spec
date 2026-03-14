# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import re

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH)
init_path = project_root / "src" / "popup_controller" / "__init__.py"
version_match = re.search(
    r'^__version__ = "(?P<version>\d+\.\d+\.\d+)"$',
    init_path.read_text(encoding="utf-8-sig"),
    re.MULTILINE,
)
if version_match is None:
    raise RuntimeError(f"Unable to determine package version from {init_path}")

app_version = version_match.group("version")
exe_name = f"popup-controller-v{app_version}"
icon_path = project_root / "src" / "popup_controller" / "assets" / "pop_up_icon.ico"
remote_mapping_reference_path = project_root / "src" / "popup_controller" / "assets" / "remote_mapping.png"
esptool_datas, esptool_binaries, esptool_hiddenimports = collect_all("esptool")
application_datas = [
    (str(icon_path), "popup_controller/assets"),
    (str(remote_mapping_reference_path), "popup_controller/assets"),
]

analysis = Analysis(
    [str(project_root / "src" / "popup_controller" / "main.py")],
    pathex=[str(project_root), str(project_root / "src")],
    binaries=esptool_binaries,
    datas=esptool_datas + application_datas,
    hiddenimports=esptool_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name=exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path),
)
