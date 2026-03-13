# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH)
esptool_datas, esptool_binaries, esptool_hiddenimports = collect_all("esptool")

analysis = Analysis(
    [str(project_root / "src" / "popup_controller" / "main.py")],
    pathex=[str(project_root), str(project_root / "src")],
    binaries=esptool_binaries,
    datas=esptool_datas,
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
    name="popup-controller",
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
)
